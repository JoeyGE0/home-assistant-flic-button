"""Binary sensor platform for Flic Button integration."""

from __future__ import annotations

from pyflic_ble import FlicState

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FlicButtonConfigEntry, FlicButtonData
from .const import BATTERY_LOW_VOLTAGE, BINARY_SENSOR_BATTERY_LOW
from .entity import FlicButtonEntity
from .helpers import get_battery_voltage

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Flic Button binary sensor entities."""
    async_add_entities([FlicBatteryLowBinarySensor(entry.runtime_data)])


class FlicBatteryLowBinarySensor(FlicButtonEntity, BinarySensorEntity):
    """Low-battery indicator for a Flic device."""

    _attr_translation_key = BINARY_SENSOR_BATTERY_LOW

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the low-battery binary sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{BINARY_SENSOR_BATTERY_LOW}"

    @property
    def available(self) -> bool:
        """Return True when a battery reading is available."""
        return get_battery_voltage(self._data) is not None

    @property
    def is_on(self) -> bool:
        """Return True when the battery voltage is below the device threshold."""
        voltage = get_battery_voltage(self._data)
        if voltage is None:
            return False
        threshold = BATTERY_LOW_VOLTAGE[self._client.device_type]
        return voltage < threshold

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Handle state updates from the client."""
        self.async_write_ha_state()
