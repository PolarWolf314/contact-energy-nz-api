"""Wrapper around the contact-energy-nz package."""

import logging
from typing import Any

import aiohttp
from contact_energy_nz import ContactEnergyApi, AuthException, UsageDatum
from contact_energy_nz.consts import API_BASE_URL, API_KEY

from app.config import get_settings
from app.db.repositories import AccountRepository
from app.models import Account, Contract, UsageData

_LOGGER = logging.getLogger(__name__)


class ContactApiWrapper:
    """Wrapper around ContactEnergyApi for our application."""

    def __init__(self):
        """Initialize wrapper."""
        self._api: ContactEnergyApi | None = None
        self._account_repo = AccountRepository()
        self._all_accounts_cache: list[Account] | None = None

    async def _get_api(self) -> ContactEnergyApi:
        """Get or create authenticated API instance."""
        if self._api is None:
            settings = get_settings()
            _LOGGER.info("Authenticating with Contact Energy API")
            self._api = await ContactEnergyApi.from_credentials(
                settings.username, settings.password
            )
            await self._api.account_summary()
            _LOGGER.info(
                "Authenticated. Account ID: %s, Contract ID: %s",
                self._api.account_id,
                self._api.contract_id,
            )
        return self._api

    async def _fetch_all_accounts_from_api(self) -> list[Account]:
        """Fetch ALL accounts directly from Contact Energy API.
        
        The contact-energy-nz library only returns the first account/contract,
        so we need to call the API directly to get all accounts (including gas).
        """
        api = await self._get_api()
        
        headers = {
            "x-api-key": API_KEY,
            "session": api.token,
            "authorization": api.token,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE_URL}/accounts/v2?ba=", headers=headers
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch accounts: %s", response.status)
                    return []
                
                data = await response.json()
                accounts_summary = data.get("accountsSummary", [])
                
                accounts: list[Account] = []
                for account_data in accounts_summary:
                    account_id = account_data.get("id", "")
                    if not account_id:
                        continue
                    
                    contracts: list[Contract] = []
                    for contract_data in account_data.get("contracts", []):
                        contract_id = contract_data.get("contractId", "")
                        if contract_id:
                            contracts.append(Contract(
                                contract_id=contract_id,
                                account_id=account_id
                            ))
                            # Store in database for future reference
                            await self._account_repo.upsert_contract(
                                contract_id, account_id
                            )
                    
                    accounts.append(Account(
                        account_id=account_id,
                        contracts=contracts
                    ))
                
                _LOGGER.info(
                    "Discovered %d accounts with %d total contracts",
                    len(accounts),
                    sum(len(a.contracts) for a in accounts)
                )
                return accounts

    async def get_accounts(self) -> list[Account]:
        """Get all accounts and contracts.
        
        Fetches ALL accounts from Contact Energy API, including gas accounts.
        """
        # Fetch fresh from API (could add caching here if needed)
        accounts = await self._fetch_all_accounts_from_api()
        
        if accounts:
            self._all_accounts_cache = accounts
            return accounts
        
        # Fallback to cached/stored data if API call fails
        if self._all_accounts_cache:
            return self._all_accounts_cache
        
        # Last resort: build from database
        stored_contracts = await self._account_repo.get_all_contracts()
        accounts_dict: dict[str, Account] = {}
        
        for contract_data in stored_contracts:
            account_id = contract_data["account_id"]
            contract_id = contract_data["contract_id"]

            if account_id not in accounts_dict:
                accounts_dict[account_id] = Account(account_id=account_id, contracts=[])

            accounts_dict[account_id].contracts.append(
                Contract(contract_id=contract_id, account_id=account_id)
            )

        return list(accounts_dict.values())

    async def set_contract(self, contract_id: str, account_id: str) -> None:
        """Set the active contract for API queries.

        This is needed because the underlying library stores contract_id
        as instance state.
        """
        api = await self._get_api()
        api.contract_id = contract_id
        api.account_id = account_id

    async def get_hourly_usage(self, date: Any) -> list[UsageData]:
        """Get hourly usage for a specific date."""
        api = await self._get_api()
        _LOGGER.debug("Fetching hourly usage for %s", date)

        try:
            usage_data = await api.get_hourly_usage(date)
        except TypeError as e:
            # Library throws TypeError when API returns unexpected data format
            # (e.g., string instead of list of dicts - common for gas contracts)
            _LOGGER.debug("API returned unexpected data format for %s: %s", date, e)
            return []
        except Exception as e:
            _LOGGER.warning("Error fetching hourly usage for %s: %s", date, e)
            return []
        
        # Handle case where API returns empty or unexpected data
        if not usage_data:
            return []
        
        # If it's a string (error message), return empty list
        if isinstance(usage_data, str):
            _LOGGER.warning("API returned string instead of usage data: %s", usage_data[:100])
            return []
        
        # Ensure it's iterable
        if not hasattr(usage_data, '__iter__'):
            _LOGGER.warning("API returned non-iterable: %s", type(usage_data))
            return []
        
        result = []
        for datum in usage_data:
            # Skip if datum is a string (sometimes API returns error strings in list)
            if isinstance(datum, str):
                _LOGGER.warning("Skipping string datum in usage data: %s", datum[:50] if len(datum) > 50 else datum)
                continue
            try:
                result.append(self._convert_usage_datum(datum))
            except Exception as e:
                _LOGGER.warning("Failed to convert usage datum: %s - %s", type(datum), e)
                continue
        
        return result

    async def get_monthly_usage(
        self, start_date: Any, end_date: Any
    ) -> list[UsageData]:
        """Get monthly usage for a date range."""
        api = await self._get_api()
        _LOGGER.debug("Fetching monthly usage from %s to %s", start_date, end_date)

        try:
            usage_data = await api.get_usage(start_date, end_date)
        except TypeError as e:
            # Library throws TypeError when API returns unexpected data format
            _LOGGER.debug("API returned unexpected data format for monthly usage: %s", e)
            return []
        except Exception as e:
            _LOGGER.warning("Error fetching monthly usage: %s", e)
            return []
        
        # Handle case where API returns empty or unexpected data
        if not usage_data:
            return []
        
        # If it's a string (error message), return empty list
        if isinstance(usage_data, str):
            _LOGGER.warning("API returned string instead of usage data: %s", usage_data[:100])
            return []
        
        # Ensure it's iterable
        if not hasattr(usage_data, '__iter__'):
            _LOGGER.warning("API returned non-iterable: %s", type(usage_data))
            return []
        
        result = []
        for datum in usage_data:
            # Skip if datum is a string (sometimes API returns error strings in list)
            if isinstance(datum, str):
                _LOGGER.warning("Skipping string datum in usage data: %s", datum[:50] if len(datum) > 50 else datum)
                continue
            try:
                result.append(self._convert_usage_datum(datum))
            except Exception as e:
                _LOGGER.warning("Failed to convert usage datum: %s - %s", type(datum), e)
                continue
        
        return result

    async def get_latest_usage(self) -> UsageData | None:
        """Get the latest available usage data."""
        api = await self._get_api()
        _LOGGER.debug("Fetching latest usage")

        try:
            usage_data = await api.get_latest_usage()
            if usage_data and len(usage_data) > 0:
                return self._convert_usage_datum(usage_data[0])
            return None
        except TypeError as e:
            # Library throws TypeError when API returns unexpected data format
            _LOGGER.debug("API returned unexpected data format for latest usage: %s", e)
            return None
        except Exception as e:
            _LOGGER.warning("Failed to get latest usage: %s", e)
            return None

    def _convert_usage_datum(self, datum: UsageDatum) -> UsageData:
        """Convert library UsageDatum to our UsageData model."""
        return UsageData(
            date=datum.date,
            value=datum.value,
            unit=datum.unit,
            dollar_value=datum.dollar_value,
            offpeak_value=datum.offpeak_value,
            offpeak_dollar_value=datum.offpeak_dollar_value,
            uncharged_value=datum.uncharged_value,
        )


# Global API wrapper instance
_api_wrapper: ContactApiWrapper | None = None


def get_contact_api() -> ContactApiWrapper:
    """Get the global API wrapper instance."""
    global _api_wrapper
    if _api_wrapper is None:
        _api_wrapper = ContactApiWrapper()
    return _api_wrapper
