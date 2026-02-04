"""Business logic for usage data and calculations."""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from app.db.repositories import UsageRepository, AccountRepository
from app.models import (
    Account,
    Comparisons,
    HourlyUsageData,
    MonthlyAggregate,
    UsageData,
    UsageSummary,
)
from app.services.cache import get_cache
from app.services.contact_api import get_contact_api

_LOGGER = logging.getLogger(__name__)


class UsageService:
    """Service for fetching and calculating usage data.
    
    This service uses a database-first approach:
    1. Check database for cached data
    2. If not found or stale, fetch from API
    3. Store fetched data in database for future use
    4. Calculate aggregates from database
    """

    def __init__(self):
        """Initialize the usage service."""
        self._api = get_contact_api()
        self._cache = get_cache()
        self._usage_repo = UsageRepository()
        self._account_repo = AccountRepository()

    async def get_accounts(self) -> list[Account]:
        """Get all accounts and contracts."""
        cache_key = "accounts"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        accounts = await self._api.get_accounts()
        
        # Store accounts in database
        for account in accounts:
            for contract in account.contracts:
                await self._account_repo.upsert_contract(
                    contract.contract_id, account.account_id
                )
        
        self._cache.set(cache_key, accounts)
        return accounts

    async def get_hourly_usage(
        self, contract_id: str, target_date: date
    ) -> HourlyUsageData:
        """Get hourly usage for a specific date.
        
        Uses database-first approach:
        1. Check if we have hourly data in the database
        2. If not, fetch from API and store
        """
        cache_key = f"hourly:{contract_id}:{target_date.isoformat()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Check database first
        hours = await self._usage_repo.get_hourly_data_for_date(contract_id, target_date)
        
        if not hours:
            # Not in database, fetch from API
            hours = await self._fetch_hourly_from_api(contract_id, target_date)

        # Calculate totals
        total_value = sum(h.value for h in hours)
        total_dollar = sum(h.dollar_value or 0 for h in hours) or None

        result = HourlyUsageData(
            date=datetime.combine(target_date, datetime.min.time()),
            hours=hours,
            total_value=total_value,
            total_dollar_value=total_dollar,
        )

        self._cache.set(cache_key, result)
        return result

    async def _fetch_hourly_from_api(
        self, contract_id: str, target_date: date
    ) -> list[UsageData]:
        """Fetch hourly data from API and store in database."""
        # Ensure we have the right contract set
        accounts = await self.get_accounts()
        account_id = await self._find_account_for_contract(contract_id, accounts)
        if account_id:
            await self._api.set_contract(contract_id, account_id)

        # Fetch from API
        hours = await self._api.get_hourly_usage(target_date)

        # Store in database
        for hour_data in hours:
            await self._usage_repo.upsert_usage(
                contract_id=contract_id,
                date=hour_data.date,
                interval="hourly",
                value=hour_data.value,
                unit=hour_data.unit,
                dollar_value=hour_data.dollar_value,
                offpeak_value=hour_data.offpeak_value,
                offpeak_dollar_value=hour_data.offpeak_dollar_value,
                uncharged_value=hour_data.uncharged_value,
            )

        return hours

    async def get_monthly_usage(
        self, contract_id: str, start_month: str, end_month: str
    ) -> list[MonthlyAggregate]:
        """Get monthly usage for a date range.
        
        Uses database-first approach for each month.
        """
        cache_key = f"monthly:{contract_id}:{start_month}:{end_month}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        result = []
        
        # Parse month range
        current = datetime.strptime(start_month, "%Y-%m").date()
        end = datetime.strptime(end_month, "%Y-%m").date()
        
        while current <= end:
            month_str = current.strftime("%Y-%m")
            
            # Try database first
            aggregate = await self._usage_repo.get_monthly_aggregate_from_db(
                contract_id, month_str
            )
            
            if aggregate is None:
                # Not in database, fetch from API
                aggregate = await self._fetch_month_from_api(contract_id, month_str)
            
            if aggregate:
                result.append(aggregate)
            
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        self._cache.set(cache_key, result)
        return result

    async def _fetch_month_from_api(
        self, contract_id: str, month: str
    ) -> MonthlyAggregate | None:
        """Fetch daily data for a month from API and store in database."""
        # Parse month to get date range
        start_date = datetime.strptime(month, "%Y-%m").date()
        if start_date.month == 12:
            next_month = start_date.replace(year=start_date.year + 1, month=1)
        else:
            next_month = start_date.replace(month=start_date.month + 1)
        end_date = next_month - timedelta(days=1)

        # Ensure we have the right contract set
        accounts = await self.get_accounts()
        account_id = await self._find_account_for_contract(contract_id, accounts)
        if account_id:
            await self._api.set_contract(contract_id, account_id)

        # Fetch from API
        usage_data = await self._api.get_monthly_usage(start_date, end_date)

        if not usage_data:
            return None

        # Store daily data in database
        for data in usage_data:
            await self._usage_repo.upsert_usage(
                contract_id=contract_id,
                date=data.date,
                interval="daily",
                value=data.value,
                unit=data.unit,
                dollar_value=data.dollar_value,
                offpeak_value=data.offpeak_value,
                offpeak_dollar_value=data.offpeak_dollar_value,
                uncharged_value=data.uncharged_value,
            )

        # Calculate aggregate
        total_value = sum(d.value for d in usage_data)
        total_dollar = sum(d.dollar_value or 0 for d in usage_data) or None
        days = len(usage_data)
        unit = usage_data[0].unit if usage_data else "kWh"

        return MonthlyAggregate(
            month=month,
            value=total_value,
            unit=unit,
            dollar_value=total_dollar,
            daily_average=total_value / days if days > 0 else 0,
            days_with_data=days,
        )

    async def get_summary(self, contract_id: str) -> UsageSummary:
        """Get complete usage summary with comparisons.
        
        Uses database-first approach for all data.
        """
        cache_key = f"summary:{contract_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        today = date.today()
        yesterday = today - timedelta(days=1)
        last_week_same_day = today - timedelta(days=7)

        # Get today's data (from DB or API)
        today_data = await self._get_daily_total(contract_id, today)

        # Get yesterday's data
        yesterday_data = await self._get_daily_total(contract_id, yesterday)

        # Get this month's data
        this_month_str = today.strftime("%Y-%m")
        this_month_data = await self._get_month_aggregate(contract_id, this_month_str)

        # Get last month's data
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        last_month_str = last_month.strftime("%Y-%m")
        last_month_data = await self._get_month_aggregate(contract_id, last_month_str)

        # Get same day last week for comparison
        last_week_data = await self._get_daily_total(contract_id, last_week_same_day)

        # Find most recent available data (for when today/yesterday are null)
        latest_day, previous_day, data_as_of = await self._find_latest_available_data(
            contract_id, today
        )

        # Calculate comparisons - use latest available data if today is null
        comparisons = Comparisons()
        comparison_today = today_data or latest_day
        comparison_yesterday = yesterday_data or previous_day

        if (
            comparison_today
            and comparison_yesterday
            and comparison_yesterday.value > 0
        ):
            comparisons.vs_yesterday = round(
                (
                    (comparison_today.value - comparison_yesterday.value)
                    / comparison_yesterday.value
                )
                * 100,
                1,
            )

        if this_month_data and last_month_data and last_month_data.value > 0:
            # Compare daily averages for fair comparison
            this_avg = this_month_data.daily_average
            last_avg = last_month_data.daily_average
            if last_avg > 0:
                comparisons.vs_last_month = round(
                    ((this_avg - last_avg) / last_avg) * 100, 1
                )

        if comparison_today and last_week_data and last_week_data.value > 0:
            comparisons.vs_same_day_last_week = round(
                ((comparison_today.value - last_week_data.value) / last_week_data.value)
                * 100,
                1,
            )

        result = UsageSummary(
            contract_id=contract_id,
            today=today_data,
            yesterday=yesterday_data,
            this_month=this_month_data,
            last_month=last_month_data,
            comparisons=comparisons,
            latest_day=latest_day,
            previous_day=previous_day,
            data_as_of=data_as_of,
        )

        self._cache.set(cache_key, result)
        return result

    async def _find_latest_available_data(
        self, contract_id: str, start_date: date
    ) -> tuple[UsageData | None, UsageData | None, str | None]:
        """Find the most recent day with available data.
        
        First checks database, then searches backwards from start_date.
        Returns (latest_day, previous_day, data_as_of_date_string).
        """
        latest_day: UsageData | None = None
        previous_day: UsageData | None = None
        data_as_of: str | None = None

        # First, try to get latest from database
        latest_date = await self._usage_repo.get_latest_data_date(contract_id, "hourly")
        
        if latest_date:
            latest_day = await self._usage_repo.get_daily_total_from_db(
                contract_id, latest_date
            )
            if latest_day and latest_day.value > 0:
                data_as_of = latest_date.isoformat()
                # Get previous day
                prev_date = latest_date - timedelta(days=1)
                previous_day = await self._usage_repo.get_daily_total_from_db(
                    contract_id, prev_date
                )
                if previous_day:
                    return latest_day, previous_day, data_as_of

        # Fallback: Search backwards up to 7 days via API
        for days_back in range(0, 8):
            check_date = start_date - timedelta(days=days_back)
            data = await self._get_daily_total(contract_id, check_date)

            if data and data.value > 0:
                if latest_day is None:
                    latest_day = data
                    data_as_of = check_date.isoformat()
                elif previous_day is None:
                    previous_day = data
                    break  # We have both, exit early

        return latest_day, previous_day, data_as_of

    async def get_current_usage(
        self, contract_id: str
    ) -> tuple[MonthlyAggregate | None, UsageData | None]:
        """Get current month's usage and today's data."""
        today = date.today()
        this_month = today.strftime("%Y-%m")

        monthly = await self._get_month_aggregate(contract_id, this_month)
        today_data = await self._get_daily_total(contract_id, today)

        return monthly, today_data

    async def _get_daily_total(
        self, contract_id: str, target_date: date
    ) -> UsageData | None:
        """Get total usage for a specific day.
        
        Database-first approach:
        1. Check database for aggregated hourly data
        2. If not found, fetch from API
        """
        try:
            # First try database
            data = await self._usage_repo.get_daily_total_from_db(contract_id, target_date)
            if data:
                return data

            # Not in database, fetch via hourly API
            hourly = await self.get_hourly_usage(contract_id, target_date)
            if not hourly.hours:
                return None

            # Sum up the hourly data
            total_value = sum(h.value for h in hourly.hours)
            total_dollar = sum(h.dollar_value or 0 for h in hourly.hours) or None
            total_offpeak = sum(h.offpeak_value or 0 for h in hourly.hours) or None
            total_offpeak_dollar = (
                sum(h.offpeak_dollar_value or 0 for h in hourly.hours) or None
            )
            total_uncharged = (
                sum(h.uncharged_value or 0 for h in hourly.hours) or None
            )

            unit = hourly.hours[0].unit if hourly.hours else "kWh"

            return UsageData(
                date=datetime.combine(target_date, datetime.min.time()),
                value=total_value,
                unit=unit,
                dollar_value=total_dollar,
                offpeak_value=total_offpeak,
                offpeak_dollar_value=total_offpeak_dollar,
                uncharged_value=total_uncharged,
            )
        except Exception as e:
            _LOGGER.warning("Failed to get daily total for %s: %s", target_date, e)
            return None

    async def _get_month_aggregate(
        self, contract_id: str, month: str
    ) -> MonthlyAggregate | None:
        """Get aggregate data for a specific month.
        
        Database-first approach.
        """
        try:
            # First try database
            aggregate = await self._usage_repo.get_monthly_aggregate_from_db(
                contract_id, month
            )
            if aggregate:
                return aggregate

            # Not in database, fetch from API
            return await self._fetch_month_from_api(contract_id, month)
        except Exception as e:
            _LOGGER.warning("Failed to get month aggregate for %s: %s", month, e)
            return None

    async def _find_account_for_contract(
        self, contract_id: str, accounts: list[Account]
    ) -> str | None:
        """Find the account ID for a given contract ID."""
        for account in accounts:
            for contract in account.contracts:
                if contract.contract_id == contract_id:
                    return account.account_id
        return None

    # =========================================================================
    # Sync methods for background data fetching
    # =========================================================================

    async def sync_contract_data(
        self,
        contract_id: str,
        days_back: int = 7,
        include_months: int = 2,
    ) -> dict[str, Any]:
        """Sync data for a contract from the API.
        
        Fetches recent hourly data and monthly data, storing in database.
        
        Args:
            contract_id: The contract to sync
            days_back: Number of days of hourly data to fetch
            include_months: Number of months of daily data to fetch
            
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            "contract_id": contract_id,
            "hourly_days_synced": 0,
            "months_synced": 0,
            "errors": [],
        }

        today = date.today()

        # Sync hourly data for recent days
        for days_ago in range(days_back):
            target_date = today - timedelta(days=days_ago)
            try:
                # Force fetch from API by clearing cache
                cache_key = f"hourly:{contract_id}:{target_date.isoformat()}"
                self._cache.delete(cache_key)
                
                hours = await self._fetch_hourly_from_api(contract_id, target_date)
                if hours:
                    stats["hourly_days_synced"] += 1
            except Exception as e:
                stats["errors"].append(f"Hourly {target_date}: {str(e)}")

        # Sync monthly data
        for months_ago in range(include_months):
            if months_ago == 0:
                month_date = today
            else:
                # Go back months
                month_date = today.replace(day=1)
                for _ in range(months_ago):
                    month_date = month_date - timedelta(days=1)
                    month_date = month_date.replace(day=1)
            
            month_str = month_date.strftime("%Y-%m")
            try:
                # Force fetch from API by clearing cache
                cache_key = f"monthly:{contract_id}:{month_str}:{month_str}"
                self._cache.delete(cache_key)
                
                aggregate = await self._fetch_month_from_api(contract_id, month_str)
                if aggregate:
                    stats["months_synced"] += 1
            except Exception as e:
                stats["errors"].append(f"Monthly {month_str}: {str(e)}")

        return stats

    async def sync_all_contracts(
        self,
        days_back: int = 7,
        include_months: int = 2,
    ) -> list[dict[str, Any]]:
        """Sync data for all known contracts."""
        results = []
        
        # Get all accounts/contracts
        accounts = await self.get_accounts()
        
        for account in accounts:
            for contract in account.contracts:
                stats = await self.sync_contract_data(
                    contract.contract_id,
                    days_back=days_back,
                    include_months=include_months,
                )
                results.append(stats)
        
        return results

    async def get_data_stats(self, contract_id: str) -> dict[str, Any]:
        """Get statistics about stored data for a contract."""
        return await self._usage_repo.get_data_stats(contract_id)


# Global service instance
_usage_service: UsageService | None = None


def get_usage_service() -> UsageService:
    """Get the global usage service instance."""
    global _usage_service
    if _usage_service is None:
        _usage_service = UsageService()
    return _usage_service
