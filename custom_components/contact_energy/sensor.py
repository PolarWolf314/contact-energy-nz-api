"""Sensor platform for Contact Energy integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_CONTRACT_ID, ATTR_DATA_AS_OF, ATTR_LAST_UPDATED, DOMAIN
from .coordinator import ContactEnergyCoordinator

_LOGGER = logging.getLogger(__name__)


# Sensor descriptions for electricity
ELECTRICITY_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="today_energy",
        name="Today Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:flash",
    ),
    SensorEntityDescription(
        key="today_cost",
        name="Today Cost",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-usd",
    ),
    SensorEntityDescription(
        key="yesterday_energy",
        name="Yesterday Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
    ),
    SensorEntityDescription(
        key="this_month_energy",
        name="This Month Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:flash",
    ),
    SensorEntityDescription(
        key="this_month_cost",
        name="This Month Cost",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-usd",
    ),
    SensorEntityDescription(
        key="daily_average",
        name="Daily Average",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
    ),
    SensorEntityDescription(
        key="vs_yesterday",
        name="vs Yesterday",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
    ),
    SensorEntityDescription(
        key="vs_last_month",
        name="vs Last Month",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
    ),
)

# Sensor descriptions for gas
GAS_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="this_month_gas",
        name="This Month Gas",
        native_unit_of_measurement="units",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:fire",
    ),
    SensorEntityDescription(
        key="this_month_gas_cost",
        name="This Month Gas Cost",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-usd",
    ),
    SensorEntityDescription(
        key="last_month_gas",
        name="Last Month Gas",
        native_unit_of_measurement="units",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Contact Energy sensors from a config entry."""
    coordinator: ContactEnergyCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities: list[SensorEntity] = []
    
    for contract in coordinator.contracts:
        contract_id = contract["contract_id"]
        
        # Determine if this is electricity or gas based on data
        contract_data = coordinator.data.get("contracts", {}).get(contract_id, {})
        
        # Check if this contract has hourly data (electricity) or only monthly (gas)
        has_hourly = contract_data.get("today") is not None
        
        if has_hourly:
            # Electricity contract - add all electricity sensors
            for description in ELECTRICITY_SENSORS:
                entities.append(
                    ContactEnergySensor(
                        coordinator=coordinator,
                        description=description,
                        contract_id=contract_id,
                        fuel_type="electricity",
                    )
                )
        else:
            # Gas contract - add gas sensors
            for description in GAS_SENSORS:
                entities.append(
                    ContactEnergySensor(
                        coordinator=coordinator,
                        description=description,
                        contract_id=contract_id,
                        fuel_type="gas",
                    )
                )
    
    async_add_entities(entities)


class ContactEnergySensor(CoordinatorEntity[ContactEnergyCoordinator], SensorEntity):
    """Representation of a Contact Energy sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ContactEnergyCoordinator,
        description: SensorEntityDescription,
        contract_id: str,
        fuel_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._contract_id = contract_id
        self._fuel_type = fuel_type
        
        # Create unique ID
        self._attr_unique_id = f"{contract_id}_{description.key}"
        
        # Set device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, contract_id)},
            "name": f"Contact Energy {fuel_type.title()} ({contract_id})",
            "manufacturer": "Contact Energy",
            "model": f"{fuel_type.title()} Meter",
        }

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        
        contract_data = self.coordinator.data.get("contracts", {}).get(
            self._contract_id, {}
        )
        
        if not contract_data:
            return None
        
        key = self.entity_description.key
        
        # Map sensor keys to API response fields
        if key == "today_energy":
            today = contract_data.get("today") or contract_data.get("latest_day")
            return today.get("value") if today else None
        
        elif key == "today_cost":
            today = contract_data.get("today") or contract_data.get("latest_day")
            return today.get("dollar_value") if today else None
        
        elif key == "yesterday_energy":
            yesterday = contract_data.get("yesterday") or contract_data.get("previous_day")
            return yesterday.get("value") if yesterday else None
        
        elif key == "this_month_energy":
            this_month = contract_data.get("this_month")
            return this_month.get("value") if this_month else None
        
        elif key == "this_month_cost":
            this_month = contract_data.get("this_month")
            return this_month.get("dollar_value") if this_month else None
        
        elif key == "daily_average":
            this_month = contract_data.get("this_month")
            return this_month.get("daily_average") if this_month else None
        
        elif key == "vs_yesterday":
            comparisons = contract_data.get("comparisons", {})
            return comparisons.get("vs_yesterday")
        
        elif key == "vs_last_month":
            comparisons = contract_data.get("comparisons", {})
            return comparisons.get("vs_last_month")
        
        # Gas sensors
        elif key == "this_month_gas":
            this_month = contract_data.get("this_month")
            return this_month.get("value") if this_month else None
        
        elif key == "this_month_gas_cost":
            this_month = contract_data.get("this_month")
            return this_month.get("dollar_value") if this_month else None
        
        elif key == "last_month_gas":
            last_month = contract_data.get("last_month")
            return last_month.get("value") if last_month else None
        
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}
        
        contract_data = self.coordinator.data.get("contracts", {}).get(
            self._contract_id, {}
        )
        
        attrs = {
            ATTR_CONTRACT_ID: self._contract_id,
        }
        
        if contract_data:
            if "data_as_of" in contract_data:
                attrs[ATTR_DATA_AS_OF] = contract_data["data_as_of"]
            if "last_updated" in contract_data:
                attrs[ATTR_LAST_UPDATED] = contract_data["last_updated"]
        
        return attrs
