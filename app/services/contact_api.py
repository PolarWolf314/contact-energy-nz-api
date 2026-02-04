"""Wrapper around the contact-energy-nz package."""

import logging
from typing import Any

from contact_energy_nz import ContactEnergyApi, AuthException, UsageDatum

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

    async def get_accounts(self) -> list[Account]:
        """Get all accounts and contracts.

        Note: The contact-energy-nz library currently only exposes the first
        account/contract. We store discovered contracts for future queries.
        """
        api = await self._get_api()

        # Store the discovered contract
        if api.account_id and api.contract_id:
            await self._account_repo.upsert_contract(api.contract_id, api.account_id)

        # Build response from what we know
        # The library only exposes one account/contract at a time
        accounts: dict[str, Account] = {}

        if api.account_id:
            account = Account(account_id=api.account_id, contracts=[])
            if api.contract_id:
                account.contracts.append(
                    Contract(contract_id=api.contract_id, account_id=api.account_id)
                )
            accounts[api.account_id] = account

        # Also include any previously stored contracts
        stored_contracts = await self._account_repo.get_all_contracts()
        for contract_data in stored_contracts:
            account_id = contract_data["account_id"]
            contract_id = contract_data["contract_id"]

            if account_id not in accounts:
                accounts[account_id] = Account(account_id=account_id, contracts=[])

            # Check if contract already in list
            existing_ids = [c.contract_id for c in accounts[account_id].contracts]
            if contract_id not in existing_ids:
                accounts[account_id].contracts.append(
                    Contract(contract_id=contract_id, account_id=account_id)
                )

        return list(accounts.values())

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

        usage_data = await api.get_hourly_usage(date)
        return [self._convert_usage_datum(datum) for datum in usage_data]

    async def get_monthly_usage(
        self, start_date: Any, end_date: Any
    ) -> list[UsageData]:
        """Get monthly usage for a date range."""
        api = await self._get_api()
        _LOGGER.debug("Fetching monthly usage from %s to %s", start_date, end_date)

        usage_data = await api.get_usage(start_date, end_date)
        return [self._convert_usage_datum(datum) for datum in usage_data]

    async def get_latest_usage(self) -> UsageData | None:
        """Get the latest available usage data."""
        api = await self._get_api()
        _LOGGER.debug("Fetching latest usage")

        try:
            usage_data = await api.get_latest_usage()
            if isinstance(usage_data, list) and len(usage_data) > 0:
                return self._convert_usage_datum(usage_data[0])
            elif hasattr(usage_data, "date"):
                return self._convert_usage_datum(usage_data)
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
