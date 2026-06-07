"""Sensor platform for Flic Button integration."""

from __future__ import annotations

from pyflic_ble import FlicState

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfElectricPotential
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FlicButtonConfigEntry, FlicButtonData
from .const import SENSOR_BATTERY
from .entity import FlicButtonEntity
from .helpers import get_battery_voltage

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Flic Button sensor entities."""
    async_add_entities([FlicBatterySensor(entry.runtime_data)])


class FlicBatterySensor(FlicButtonEntity, SensorEntity):
    """Battery voltage sensor for a Flic device."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_translation_key = SENSOR_BATTERY

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the battery sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{SENSOR_BATTERY}"

    @property
    def available(self) -> bool:
        """Return True when a battery reading is available."""
        return get_battery_voltage(self._data) is not None

    @property
    def native_value(self) -> float | None:
        """Return the battery voltage."""
        return get_battery_voltage(self._data)

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Handle state updates from the client."""
        self.async_write_ha_state()
