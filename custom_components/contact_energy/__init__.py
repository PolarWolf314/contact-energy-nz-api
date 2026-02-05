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
            daily_stats = stats.get("daily", {})
            
            # Check if this is a gas contract (no hourly data, but has daily data)
            hourly_count = hourly_stats.get("count", 0)
            daily_count = daily_stats.get("count", 0)
            
            if hourly_count == 0 and daily_count > 0:
                # This is a gas contract - use monthly data
                _LOGGER.info(
                    "Contract %s appears to be gas (no hourly data, %d daily records)",
                    contract_id,
                    daily_count,
                )
                await _async_import_gas_statistics(hass, coordinator, contract_id, daily_stats)
                continue
            
            oldest_date = hourly_stats.get("oldest")
            newest_date = hourly_stats.get("newest")
            
            if not oldest_date or not newest_date:
                _LOGGER.warning("No date range for contract %s", contract_id)
                continue
            
            # Parse dates
            oldest = datetime.fromisoformat(oldest_date.split("T")[0])
            newest = datetime.fromisoformat(newest_date.split("T")[0])
            
            _LOGGER.info(
                "Importing electricity statistics for contract %s from %s to %s",
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
                "Imported %d electricity data points for contract %s",
                len(historical_data),
                contract_id,
            )
            
        except Exception as err:
            _LOGGER.error(
                "Error importing statistics for contract %s: %s",
                contract_id,
                err,
            )


async def _async_import_gas_statistics(
    hass: HomeAssistant,
    coordinator: ContactEnergyCoordinator,
    contract_id: str,
    daily_stats: dict[str, Any],
) -> None:
    """Import gas usage as monthly statistics.
    
    Gas data from Contact Energy is only available as daily totals (or monthly aggregates).
    Since gas billing is monthly, we import monthly data points into HA statistics.
    Each statistic entry represents the total gas usage for that month.
    """
    oldest_date = daily_stats.get("oldest")
    newest_date = daily_stats.get("newest")
    
    if not oldest_date or not newest_date:
        _LOGGER.warning("No date range for gas contract %s", contract_id)
        return
    
    # Parse the date range
    oldest = datetime.fromisoformat(oldest_date.split("T")[0])
    newest = datetime.fromisoformat(newest_date.split("T")[0])
    
    # Convert to YYYY-MM format for monthly API
    start_month = oldest.strftime("%Y-%m")
    end_month = newest.strftime("%Y-%m")
    
    _LOGGER.info(
        "Importing gas statistics for contract %s from %s to %s",
        contract_id,
        start_month,
        end_month,
    )
    
    # Fetch monthly data
    monthly_data = await coordinator.async_get_monthly_data(
        contract_id,
        start_month,
        end_month,
    )
    
    if not monthly_data:
        _LOGGER.warning("No monthly gas data for contract %s", contract_id)
        return
    
    # Create gas statistics
    await _async_insert_gas_statistics(
        hass,
        contract_id,
        monthly_data,
    )
    
    _LOGGER.info(
        "Imported %d monthly gas data points for contract %s",
        len(monthly_data),
        contract_id,
    )


async def _async_insert_gas_statistics(
    hass: HomeAssistant,
    contract_id: str,
    monthly_data: list[dict[str, Any]],
) -> None:
    """Insert monthly gas data as external statistics.
    
    Creates statistics entries for gas usage and cost. Each entry represents
    the total usage/cost for that month, timestamped at the 1st of the month.
    
    The 'state' value uses daily_average for meaningful month-over-month
    comparisons in the Energy Dashboard, while 'sum' tracks cumulative totals.
    """
    if not monthly_data:
        return
    
    # Sort by month once for both statistics
    sorted_data = sorted(monthly_data, key=lambda x: x.get("month", ""))
    
    # === Gas Usage Statistics (kWh) ===
    gas_statistic_id = f"{DOMAIN}:gas_{contract_id}"
    gas_metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"Contact Energy Gas {contract_id}",
        source=DOMAIN,
        statistic_id=gas_statistic_id,
        unit_of_measurement="kWh",  # Gas is reported in kWh (thermal equivalent)
    )
    
    # === Gas Cost Statistics (NZD) ===
    cost_statistic_id = f"{DOMAIN}:gas_cost_{contract_id}"
    cost_metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"Contact Energy Gas Cost {contract_id}",
        source=DOMAIN,
        statistic_id=cost_statistic_id,
        unit_of_measurement="NZD",
    )
    
    gas_statistics: list[StatisticData] = []
    cost_statistics: list[StatisticData] = []
    gas_cumulative = 0.0
    cost_cumulative = 0.0
    
    for record in sorted_data:
        month_str = record.get("month")
        if not month_str:
            continue
        
        try:
            # Parse the month (YYYY-MM format) and set to 1st of month at midnight UTC
            year, month = map(int, month_str.split("-"))
            dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
            
            # Gas usage: use daily_average for state (for meaningful comparisons),
            # but keep cumulative sum of totals for the 'sum' field
            gas_total = record.get("value", 0) or 0
            gas_daily_avg = record.get("daily_average", 0) or 0
            gas_cumulative += gas_total
            
            gas_stat = StatisticData(
                start=dt,
                state=gas_daily_avg,  # Daily average for month-over-month comparison
                sum=gas_cumulative,   # Cumulative total for Energy Dashboard
            )
            gas_statistics.append(gas_stat)
            
            # Gas cost: use daily average for state as well
            cost_total = record.get("dollar_value", 0) or 0
            days_with_data = record.get("days_with_data", 0) or 1
            cost_daily_avg = cost_total / days_with_data if days_with_data > 0 else 0
            cost_cumulative += cost_total
            
            cost_stat = StatisticData(
                start=dt,
                state=cost_daily_avg,  # Daily average cost
                sum=cost_cumulative,   # Cumulative total cost
            )
            cost_statistics.append(cost_stat)
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Error parsing month %s: %s", month_str, err)
            continue
    
    # Insert gas usage statistics
    if gas_statistics:
        try:
            async_add_external_statistics(hass, gas_metadata, gas_statistics)
            _LOGGER.info(
                "Inserted %d gas statistics for %s (cumulative: %.2f kWh)",
                len(gas_statistics),
                gas_statistic_id,
                gas_cumulative,
            )
        except Exception as err:
            _LOGGER.error("Error inserting gas statistics: %s", err)
    else:
        _LOGGER.warning("No valid gas statistics to insert for %s", contract_id)
    
    # Insert gas cost statistics
    if cost_statistics and cost_cumulative > 0:
        try:
            async_add_external_statistics(hass, cost_metadata, cost_statistics)
            _LOGGER.info(
                "Inserted %d gas cost statistics for %s (cumulative: $%.2f NZD)",
                len(cost_statistics),
                cost_statistic_id,
                cost_cumulative,
            )
        except Exception as err:
            _LOGGER.error("Error inserting gas cost statistics: %s", err)
    else:
        _LOGGER.debug("No gas cost data available for contract %s", contract_id)


async def _async_insert_statistics(
    hass: HomeAssistant,
    contract_id: str,
    historical_data: list[dict[str, Any]],
) -> None:
    """Insert historical data as external statistics.
    
    This creates statistics entries that appear in Home Assistant's
    long-term statistics database, enabling historical charting.
    Creates both energy (kWh) and cost (NZD) statistics.
    """
    if not historical_data:
        return
    
    # Sort by date once for both statistics
    sorted_data = sorted(historical_data, key=lambda x: x.get("date", ""))
    
    # === Energy Statistics (kWh) ===
    energy_statistic_id = f"{DOMAIN}:energy_{contract_id}"
    energy_metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"Contact Energy {contract_id}",
        source=DOMAIN,
        statistic_id=energy_statistic_id,
        unit_of_measurement="kWh",
    )
    
    # === Cost Statistics (NZD) ===
    cost_statistic_id = f"{DOMAIN}:cost_{contract_id}"
    cost_metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"Contact Energy Cost {contract_id}",
        source=DOMAIN,
        statistic_id=cost_statistic_id,
        unit_of_measurement="NZD",
    )
    
    energy_statistics: list[StatisticData] = []
    cost_statistics: list[StatisticData] = []
    energy_cumulative = 0.0
    cost_cumulative = 0.0
    
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
            
            # Energy value
            energy_value = record.get("value", 0) or 0
            energy_cumulative += energy_value
            
            energy_stat = StatisticData(
                start=dt,
                state=energy_value,
                sum=energy_cumulative,
            )
            energy_statistics.append(energy_stat)
            
            # Cost value (may be None for some records)
            cost_value = record.get("dollar_value", 0) or 0
            cost_cumulative += cost_value
            
            cost_stat = StatisticData(
                start=dt,
                state=cost_value,
                sum=cost_cumulative,
            )
            cost_statistics.append(cost_stat)
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Error parsing date %s: %s", date_str, err)
            continue
    
    # Insert energy statistics
    if energy_statistics:
        try:
            async_add_external_statistics(hass, energy_metadata, energy_statistics)
            _LOGGER.info(
                "Inserted %d energy statistics for %s (cumulative: %.2f kWh)",
                len(energy_statistics),
                energy_statistic_id,
                energy_cumulative,
            )
        except Exception as err:
            _LOGGER.error("Error inserting energy statistics: %s", err)
    else:
        _LOGGER.warning("No valid energy statistics to insert for %s", contract_id)
    
    # Insert cost statistics
    if cost_statistics and cost_cumulative > 0:
        try:
            async_add_external_statistics(hass, cost_metadata, cost_statistics)
            _LOGGER.info(
                "Inserted %d cost statistics for %s (cumulative: $%.2f NZD)",
                len(cost_statistics),
                cost_statistic_id,
                cost_cumulative,
            )
        except Exception as err:
            _LOGGER.error("Error inserting cost statistics: %s", err)
    else:
        _LOGGER.debug("No cost data available for contract %s", contract_id)
