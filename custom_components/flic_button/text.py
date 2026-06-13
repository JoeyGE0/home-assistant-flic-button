"""Text platform for Flic Button integration."""

from __future__ import annotations

import logging

from pyflic_ble import FlicProtocolError, FlicState

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FlicButtonConfigEntry, FlicButtonData
from .const import DOMAIN, TEXT_DEVICE_NAME
from .entity import FlicButtonEntity
from .helpers import sync_ha_device_from_state

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
MAX_NAME_BYTES = 23


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Flic Button text entities."""
    async_add_entities([FlicDeviceNameText(entry.runtime_data, entry)])


class FlicDeviceNameText(FlicButtonEntity, TextEntity):
    """On-device Flic name from documented get_name / set_name API."""

    _attr_entity_registry_enabled_default = False
    _attr_translation_key = TEXT_DEVICE_NAME
    _attr_native_max = MAX_NAME_BYTES
    _attr_mode = "text"

    def __init__(self, data: FlicButtonData, entry: FlicButtonConfigEntry) -> None:
        """Initialize the device name text entity."""
        super().__init__(data)
        self._entry = entry
        self._last_device_name: str | None = data.client.state.device_name
        self._attr_unique_id = f"{self._client.address}-{TEXT_DEVICE_NAME}"

    @property
    def native_value(self) -> str:
        """Return the on-device Flic name (not the HA device label)."""
        return self._client.state.device_name or ""

    async def async_set_value(self, value: str) -> None:
        """Set the Flic device name using documented pyflic-ble API."""
        if not self._client.state.connected:
            raise HomeAssistantError(
                "Flic is not connected. Press the button near your Bluetooth proxy."
            )

        try:
            new_name, _timestamp = await self._client.set_name(value)
        except FlicProtocolError as err:
            raise HomeAssistantError(str(err)) from err

        self._last_device_name = new_name
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self._client.address)}
        )
        if device is not None:
            device_registry.async_update_device(device.id, name_by_user=new_name)

        sync_ha_device_from_state(self.hass, self._entry)
        self.async_write_ha_state()

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Refresh when the on-device name is fetched or changed."""
        if not self.enabled:
            return
        if state.device_name != self._last_device_name:
            self._last_device_name = state.device_name
            self.async_write_ha_state()
