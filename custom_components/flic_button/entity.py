"""Base entity for Flic Button integration."""

from __future__ import annotations

from pyflic_ble import FlicState

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from . import FlicButtonData
from .const import DEVICE_TYPE_MODEL_NAMES, DOMAIN


class FlicButtonEntity(Entity):
    """Base entity for Flic Button integration."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the Flic button entity."""
        client = data.client
        serial = data.serial_number
        model_name = DEVICE_TYPE_MODEL_NAMES[client.device_type]

        fw = client.state.firmware_version
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data.address)},
            connections={(CONNECTION_BLUETOOTH, data.address)},
            manufacturer="Shortcut Labs",
            model=model_name,
            serial_number=serial,
            sw_version=str(fw) if fw is not None else None,
        )
        self._client = client
        self._data = data

    def _entity_unique_id(self, suffix: str) -> str:
        """Build a stable entity unique_id from the config entry address."""
        return f"{self._data.address}-{suffix}"

    @property
    def available(self) -> bool:
        """Entities stay available after pairing."""
        return True

    async def async_added_to_hass(self) -> None:
        """Register state callback when entity is added."""
        await super().async_added_to_hass()

        self.async_on_remove(
            self._client.register_state_callback(self._handle_state_update)
        )

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Refresh firmware version from documented FlicState fields."""
        fw = state.firmware_version
        if fw is not None and self._attr_device_info.get("sw_version") != str(fw):
            info = dict(self._attr_device_info)
            info["sw_version"] = str(fw)
            self._attr_device_info = DeviceInfo(**info)
        self.async_write_ha_state()
