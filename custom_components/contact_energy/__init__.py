"""The Contact Energy integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData

from .const import DOMAIN, PLATFORMS, SERVICE_BACKFILL, SERVICE_SYNC
from .coordinator import ContactEnergyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Contact Energy from a config entry."""
    coordinator = ContactEnergyCoordinator(hass, entry)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await _async_setup_services(hass, coordinator)
    
    # Schedule historical data import
    entry.async_create_background_task(
        hass,
        _async_import_historical_statistics(hass, coordinator),
        "contact_energy_import_statistics",
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def _async_setup_services(
    hass: HomeAssistant,
    coordinator: ContactEnergyCoordinator,
) -> None:
    """Set up services for the integration."""
    
    async def handle_sync(call: ServiceCall) -> None:
        """Handle the sync service call."""
        _LOGGER.info("Sync service called")
        try:
            result = await coordinator.async_trigger_sync()
            _LOGGER.info("Sync completed: %s", result)
            await coordinator.async_refresh()
        except Exception as err:
            _LOGGER.error("Sync failed: %s", err)
    
    async def handle_backfill(call: ServiceCall) -> None:
        """Handle the backfill service call."""
        _LOGGER.info("Backfill service called")
        try:
            result = await coordinator.async_trigger_backfill()
            _LOGGER.info("Backfill completed: %s", result)
            
            # After backfill, import the new statistics
            await _async_import_historical_statistics(hass, coordinator)
            
            await coordinator.async_refresh()
        except Exception as err:
            _LOGGER.error("Backfill failed: %s", err)
    
    async def handle_import_statistics(call: ServiceCall) -> None:
        """Handle the import statistics service call."""
        _LOGGER.info("Import statistics service called")
        await _async_import_historical_statistics(hass, coordinator)
    
    hass.services.async_register(DOMAIN, SERVICE_SYNC, handle_sync)
    hass.services.async_register(DOMAIN, SERVICE_BACKFILL, handle_backfill)
    hass.services.async_register(DOMAIN, "import_statistics", handle_import_statistics)


async def _async_import_historical_statistics(
    hass: HomeAssistant,
    coordinator: ContactEnergyCoordinator,
) -> None:
    """Import historical data into Home Assistant long-term statistics.
    
    This allows historical energy data to appear in the Energy Dashboard
    and be available for charting.
    """
    _LOGGER.info("Starting historical statistics import")
    
    for contract in coordinator.contracts:
        contract_id = contract["contract_id"]
        
        try:
            # Get the data range from the API
            stats = await coordinator.async_get_contract_stats(contract_id)
            
            if not stats:
                _LOGGER.warning("No stats available for contract %s", contract_id)
                continue
            
            hourly_stats = stats.get("hourly", {})
            oldest_date = hourly_stats.get("oldest")
            newest_date = hourly_stats.get("newest")
            
            if not oldest_date or not newest_date:
                _LOGGER.warning("No date range for contract %s", contract_id)
                continue
            
            # Parse dates
            oldest = datetime.fromisoformat(oldest_date.split("T")[0])
            newest = datetime.fromisoformat(newest_date.split("T")[0])
            
            _LOGGER.info(
                "Importing statistics for contract %s from %s to %s",
                contract_id,
                oldest.date(),
                newest.date(),
            )
            
            # Fetch historical data from API
            historical_data = await coordinator.async_get_historical_data(
                contract_id,
                oldest.strftime("%Y-%m-%d"),
                newest.strftime("%Y-%m-%d"),
            )
            
            if not historical_data:
                _LOGGER.warning("No historical data for contract %s", contract_id)
                continue
            
            # Create statistics
            await _async_insert_statistics(
                hass,
                contract_id,
                historical_data,
            )
            
            _LOGGER.info(
                "Imported %d data points for contract %s",
                len(historical_data),
                contract_id,
            )
            
        except Exception as err:
            _LOGGER.error(
                "Error importing statistics for contract %s: %s",
                contract_id,
                err,
            )


async def _async_insert_statistics(
    hass: HomeAssistant,
    contract_id: str,
    historical_data: list[dict[str, Any]],
) -> None:
    """Insert historical data as external statistics.
    
    This creates statistics entries that appear in Home Assistant's
    long-term statistics database, enabling historical charting.
    """
    if not historical_data:
        return
    
    statistic_id = f"{DOMAIN}:energy_{contract_id}"
    
    # Create metadata for the statistic
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"Contact Energy {contract_id}",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement="kWh",
    )
    
    # Group data by hour and calculate cumulative sum
    statistics: list[StatisticData] = []
    cumulative_sum = 0.0
    
    # Sort by date
    sorted_data = sorted(historical_data, key=lambda x: x.get("date", ""))
    
    for record in sorted_data:
        date_str = record.get("date")
        if not date_str:
            continue
        
        try:
            # Parse the datetime
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            
            # Ensure UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            value = record.get("value", 0) or 0
            cumulative_sum += value
            
            # Create statistic entry
            stat = StatisticData(
                start=dt,
                state=value,
                sum=cumulative_sum,
            )
            statistics.append(stat)
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Error parsing date %s: %s", date_str, err)
            continue
    
    if not statistics:
        _LOGGER.warning("No valid statistics to insert for %s", contract_id)
        return
    
    # Insert the statistics
    try:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(
            "Inserted %d statistics for %s (cumulative: %.2f kWh)",
            len(statistics),
            statistic_id,
            cumulative_sum,
        )
    except Exception as err:
        _LOGGER.error("Error inserting statistics: %s", err)
