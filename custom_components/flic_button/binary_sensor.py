"""Binary sensor platform for Flic Button integration."""

from __future__ import annotations

from pyflic_ble import FlicState

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FlicButtonConfigEntry, FlicButtonData
from .const import BINARY_SENSOR_CONNECTED
from .entity import FlicButtonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Flic Button binary sensor entities."""
    async_add_entities([FlicConnectionBinarySensor(entry.runtime_data)])


class FlicConnectionBinarySensor(FlicButtonEntity, BinarySensorEntity):
    """Connection state for a Flic device from documented FlicState.connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = BINARY_SENSOR_CONNECTED

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the connection binary sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{BINARY_SENSOR_CONNECTED}"
        self._attr_suggested_object_id = BINARY_SENSOR_CONNECTED

    @property
    def is_on(self) -> bool:
        """Return True when the Flic is connected."""
        return self._client.state.connected

    async def async_added_to_hass(self) -> None:
        """Register state callbacks when entity is added."""
        await super().async_added_to_hass()

        @callback
        def _async_connection_changed() -> None:
            self.async_write_ha_state()

        self._data.state_callbacks.append(_async_connection_changed)
        self.async_on_remove(
            lambda: self._data.state_callbacks.remove(_async_connection_changed)
        )

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Handle state updates from the client."""
        self.async_write_ha_state()
