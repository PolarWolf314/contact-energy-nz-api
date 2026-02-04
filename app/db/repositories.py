"""Data access layer for usage data."""

from datetime import datetime, date, timedelta
from typing import Any

from app.db.database import get_database
from app.models import UsageData, MonthlyAggregate


class UsageRepository:
    """Repository for usage data operations."""

    def __init__(self):
        """Initialize repository with database instance."""
        self.db = get_database()

    async def upsert_usage(
        self,
        contract_id: str,
        date: datetime,
        interval: str,
        value: float,
        unit: str,
        dollar_value: float | None = None,
        offpeak_value: float | None = None,
        offpeak_dollar_value: float | None = None,
        uncharged_value: float | None = None,
    ) -> None:
        """Insert or update usage data."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO usage_data 
                    (contract_id, date, interval, value, unit, dollar_value, 
                     offpeak_value, offpeak_dollar_value, uncharged_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contract_id, date, interval) DO UPDATE SET
                    value = excluded.value,
                    unit = excluded.unit,
                    dollar_value = excluded.dollar_value,
                    offpeak_value = excluded.offpeak_value,
                    offpeak_dollar_value = excluded.offpeak_dollar_value,
                    uncharged_value = excluded.uncharged_value
                """,
                (
                    contract_id,
                    date.isoformat(),
                    interval,
                    value,
                    unit,
                    dollar_value,
                    offpeak_value,
                    offpeak_dollar_value,
                    uncharged_value,
                ),
            )
            await conn.commit()

    async def get_usage(
        self,
        contract_id: str,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> list[UsageData]:
        """Get usage data for a date range."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT date, value, unit, dollar_value, offpeak_value, 
                       offpeak_dollar_value, uncharged_value
                FROM usage_data
                WHERE contract_id = ? 
                  AND date >= ? 
                  AND date <= ?
                  AND interval = ?
                ORDER BY date ASC
                """,
                (contract_id, start_date.isoformat(), end_date.isoformat(), interval),
            )
            rows = await cursor.fetchall()

            return [
                UsageData(
                    date=datetime.fromisoformat(row["date"]),
                    value=row["value"],
                    unit=row["unit"],
                    dollar_value=row["dollar_value"],
                    offpeak_value=row["offpeak_value"],
                    offpeak_dollar_value=row["offpeak_dollar_value"],
                    uncharged_value=row["uncharged_value"],
                )
                for row in rows
            ]

    async def get_usage_for_date(
        self,
        contract_id: str,
        date: datetime,
        interval: str,
    ) -> UsageData | None:
        """Get usage data for a specific date."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT date, value, unit, dollar_value, offpeak_value, 
                       offpeak_dollar_value, uncharged_value
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (contract_id, f"{date.strftime('%Y-%m-%d')}%", interval),
            )
            row = await cursor.fetchone()

            if row is None:
                return None

            return UsageData(
                date=datetime.fromisoformat(row["date"]),
                value=row["value"],
                unit=row["unit"],
                dollar_value=row["dollar_value"],
                offpeak_value=row["offpeak_value"],
                offpeak_dollar_value=row["offpeak_dollar_value"],
                uncharged_value=row["uncharged_value"],
            )

    async def get_daily_total_from_db(
        self,
        contract_id: str,
        target_date: date,
    ) -> UsageData | None:
        """Get aggregated daily total from hourly data in the database.
        
        Sums all hourly records for the given date.
        """
        async with self.db.connection() as conn:
            # Get all hourly data for this date and aggregate
            date_prefix = target_date.strftime("%Y-%m-%d")
            cursor = await conn.execute(
                """
                SELECT 
                    MIN(date) as date,
                    SUM(value) as value,
                    MAX(unit) as unit,
                    SUM(dollar_value) as dollar_value,
                    SUM(offpeak_value) as offpeak_value,
                    SUM(offpeak_dollar_value) as offpeak_dollar_value,
                    SUM(uncharged_value) as uncharged_value,
                    COUNT(*) as hour_count
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = 'hourly'
                """,
                (contract_id, f"{date_prefix}%"),
            )
            row = await cursor.fetchone()

            if row is None or row["hour_count"] == 0 or row["value"] is None:
                return None

            return UsageData(
                date=datetime.fromisoformat(row["date"]),
                value=row["value"],
                unit=row["unit"] or "kWh",
                dollar_value=row["dollar_value"],
                offpeak_value=row["offpeak_value"],
                offpeak_dollar_value=row["offpeak_dollar_value"],
                uncharged_value=row["uncharged_value"],
            )

    async def get_hourly_data_for_date(
        self,
        contract_id: str,
        target_date: date,
    ) -> list[UsageData]:
        """Get all hourly data points for a specific date."""
        async with self.db.connection() as conn:
            date_prefix = target_date.strftime("%Y-%m-%d")
            cursor = await conn.execute(
                """
                SELECT date, value, unit, dollar_value, offpeak_value, 
                       offpeak_dollar_value, uncharged_value
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = 'hourly'
                ORDER BY date ASC
                """,
                (contract_id, f"{date_prefix}%"),
            )
            rows = await cursor.fetchall()

            return [
                UsageData(
                    date=datetime.fromisoformat(row["date"]),
                    value=row["value"],
                    unit=row["unit"],
                    dollar_value=row["dollar_value"],
                    offpeak_value=row["offpeak_value"],
                    offpeak_dollar_value=row["offpeak_dollar_value"],
                    uncharged_value=row["uncharged_value"],
                )
                for row in rows
            ]

    async def get_monthly_aggregate_from_db(
        self,
        contract_id: str,
        month: str,
    ) -> MonthlyAggregate | None:
        """Get monthly aggregate from daily data in the database.
        
        Uses the 'daily' interval data stored from the monthly API call.
        Args:
            contract_id: The contract ID
            month: Month in YYYY-MM format
        """
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT 
                    SUM(value) as total_value,
                    SUM(dollar_value) as total_dollar,
                    MAX(unit) as unit,
                    COUNT(*) as days_count
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = 'daily'
                """,
                (contract_id, f"{month}%"),
            )
            row = await cursor.fetchone()

            if row is None or row["days_count"] == 0 or row["total_value"] is None:
                return None

            total_value = row["total_value"]
            days = row["days_count"]

            return MonthlyAggregate(
                month=month,
                value=total_value,
                unit=row["unit"] or "kWh",
                dollar_value=row["total_dollar"],
                daily_average=total_value / days if days > 0 else 0,
                days_with_data=days,
            )

    async def get_latest_data_date(
        self,
        contract_id: str,
        interval: str = "hourly",
    ) -> date | None:
        """Get the date of the most recent data for a contract."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT MAX(date) as latest_date
                FROM usage_data
                WHERE contract_id = ? AND interval = ?
                """,
                (contract_id, interval),
            )
            row = await cursor.fetchone()

            if row is None or row["latest_date"] is None:
                return None

            return datetime.fromisoformat(row["latest_date"]).date()

    async def get_oldest_data_date(
        self,
        contract_id: str,
        interval: str = "hourly",
    ) -> date | None:
        """Get the date of the oldest data for a contract."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT MIN(date) as oldest_date
                FROM usage_data
                WHERE contract_id = ? AND interval = ?
                """,
                (contract_id, interval),
            )
            row = await cursor.fetchone()

            if row is None or row["oldest_date"] is None:
                return None

            return datetime.fromisoformat(row["oldest_date"]).date()

    async def has_data_for_date(
        self,
        contract_id: str,
        target_date: date,
        interval: str = "hourly",
    ) -> bool:
        """Check if we have data for a specific date."""
        async with self.db.connection() as conn:
            date_prefix = target_date.strftime("%Y-%m-%d")
            cursor = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = ?
                """,
                (contract_id, f"{date_prefix}%", interval),
            )
            row = await cursor.fetchone()
            return row is not None and row["count"] > 0

    async def has_data_for_month(
        self,
        contract_id: str,
        month: str,
    ) -> bool:
        """Check if we have daily data for a specific month."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = 'daily'
                """,
                (contract_id, f"{month}%"),
            )
            row = await cursor.fetchone()
            return row is not None and row["count"] > 0

    async def get_data_stats(
        self,
        contract_id: str,
    ) -> dict[str, Any]:
        """Get statistics about stored data for a contract."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT 
                    interval,
                    COUNT(*) as count,
                    MIN(date) as oldest,
                    MAX(date) as newest
                FROM usage_data
                WHERE contract_id = ?
                GROUP BY interval
                """,
                (contract_id,),
            )
            rows = await cursor.fetchall()

            stats = {}
            for row in rows:
                stats[row["interval"]] = {
                    "count": row["count"],
                    "oldest": row["oldest"],
                    "newest": row["newest"],
                }
            return stats

    async def upsert_daily_usage(
        self,
        contract_id: str,
        target_date: date,
        value: float,
        unit: str,
        dollar_value: float | None = None,
        offpeak_value: float | None = None,
        offpeak_dollar_value: float | None = None,
        uncharged_value: float | None = None,
    ) -> None:
        """Insert or update daily usage data (aggregated from hourly or from API)."""
        dt = datetime.combine(target_date, datetime.min.time())
        await self.upsert_usage(
            contract_id=contract_id,
            date=dt,
            interval="daily",
            value=value,
            unit=unit,
            dollar_value=dollar_value,
            offpeak_value=offpeak_value,
            offpeak_dollar_value=offpeak_dollar_value,
            uncharged_value=uncharged_value,
        )


class AccountRepository:
    """Repository for account and contract operations."""

    def __init__(self):
        """Initialize repository with database instance."""
        self.db = get_database()

    async def upsert_account(self, account_id: str) -> None:
        """Insert or update an account."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO accounts (account_id)
                VALUES (?)
                ON CONFLICT(account_id) DO NOTHING
                """,
                (account_id,),
            )
            await conn.commit()

    async def upsert_contract(self, contract_id: str, account_id: str) -> None:
        """Insert or update a contract."""
        async with self.db.connection() as conn:
            # Ensure account exists
            await conn.execute(
                """
                INSERT INTO accounts (account_id)
                VALUES (?)
                ON CONFLICT(account_id) DO NOTHING
                """,
                (account_id,),
            )

            await conn.execute(
                """
                INSERT INTO contracts (contract_id, account_id)
                VALUES (?, ?)
                ON CONFLICT(contract_id) DO UPDATE SET
                    account_id = excluded.account_id
                """,
                (contract_id, account_id),
            )
            await conn.commit()

    async def get_all_contracts(self) -> list[dict[str, Any]]:
        """Get all stored contracts with their accounts."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT contract_id, account_id
                FROM contracts
                ORDER BY account_id, contract_id
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def contract_exists(self, contract_id: str) -> bool:
        """Check if a contract exists."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM contracts WHERE contract_id = ?",
                (contract_id,),
            )
            row = await cursor.fetchone()
            return row is not None
