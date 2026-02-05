"""DataUpdateCoordinator for Contact Energy integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_API_URL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ContactEnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for fetching Contact Energy data from the API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api_url = config_entry.data[CONF_API_URL]
        self._contracts: list[dict[str, Any]] = []
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_setup(self) -> None:
        """Set up the coordinator - fetch accounts/contracts."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/accounts",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Failed to fetch accounts: {response.status}")
                    
                    data = await response.json()
                    accounts = data.get("accounts", [])
                    
                    # Flatten contracts from all accounts
                    self._contracts = []
                    for account in accounts:
                        for contract in account.get("contracts", []):
                            self._contracts.append({
                                "contract_id": contract.get("contract_id"),
                                "account_id": account.get("account_id"),
                            })
                    
                    _LOGGER.info(
                        "Discovered %d contracts from Contact Energy API",
                        len(self._contracts),
                    )
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error connecting to API: {err}") from err

    @property
    def contracts(self) -> list[dict[str, Any]]:
        """Return the list of discovered contracts."""
        return self._contracts

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API for all contracts."""
        data: dict[str, Any] = {"contracts": {}}
        
        try:
            async with aiohttp.ClientSession() as session:
                for contract in self._contracts:
                    contract_id = contract["contract_id"]
                    
                    try:
                        async with session.get(
                            f"{self.api_url}/contracts/{contract_id}/summary",
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as response:
                            if response.status == 200:
                                contract_data = await response.json()
                                data["contracts"][contract_id] = contract_data
                            else:
                                _LOGGER.warning(
                                    "Failed to fetch summary for contract %s: %s",
                                    contract_id,
                                    response.status,
                                )
                    except aiohttp.ClientError as err:
                        _LOGGER.warning(
                            "Error fetching data for contract %s: %s",
                            contract_id,
                            err,
                        )
                        
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        
        return data

    async def async_trigger_sync(self) -> dict[str, Any]:
        """Trigger a sync on the API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/sync",
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise UpdateFailed(f"Sync failed: {response.status}")
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error triggering sync: {err}") from err

    async def async_trigger_backfill(self) -> dict[str, Any]:
        """Trigger an adaptive backfill on the API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/sync/backfill/adaptive",
                    timeout=aiohttp.ClientTimeout(total=3600),  # 1 hour timeout for backfill
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise UpdateFailed(f"Backfill failed: {response.status}")
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error triggering backfill: {err}") from err

    async def async_get_historical_data(
        self,
        contract_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch historical hourly data for a contract.
        
        Args:
            contract_id: The contract ID to fetch data for
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of hourly usage records
        """
        historical_data: list[dict[str, Any]] = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch data day by day
                from datetime import datetime, timedelta as td
                
                current = datetime.strptime(start_date, "%Y-%m-%d").date()
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                
                while current <= end:
                    date_str = current.strftime("%Y-%m-%d")
                    
                    try:
                        async with session.get(
                            f"{self.api_url}/contracts/{contract_id}/usage/hourly",
                            params={"date": date_str},
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                hours = data.get("hours", [])
                                
                                # Add each hour's data
                                for hour in hours:
                                    historical_data.append({
                                        "date": hour.get("date"),
                                        "value": hour.get("value", 0),
                                        "dollar_value": hour.get("dollar_value"),
                                    })
                    except aiohttp.ClientError as err:
                        _LOGGER.warning(
                            "Error fetching hourly data for %s on %s: %s",
                            contract_id,
                            date_str,
                            err,
                        )
                    
                    current += td(days=1)
                    
        except Exception as err:
            _LOGGER.error("Error fetching historical data: %s", err)
        
        return historical_data

    async def async_get_contract_stats(self, contract_id: str) -> dict[str, Any]:
        """Get statistics about stored data for a contract."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/contracts/{contract_id}/stats",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {}
        except aiohttp.ClientError as err:
            _LOGGER.warning("Error fetching stats for %s: %s", contract_id, err)
            return {}
