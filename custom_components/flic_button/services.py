"""Services for the Flic Button integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol
from pyflic_ble import FlicProtocolError

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, SERVICE_SET_NAME, SERVICE_SET_TWIST_POSITION
from .helpers import normalize_address

if TYPE_CHECKING:
    from . import FlicButtonConfigEntry

_LOGGER = logging.getLogger(__name__)

SET_TWIST_POSITION_SCHEMA = vol.Schema(
    {
        vol.Required("mode_index"): vol.All(vol.Coerce(int), vol.Range(min=0, max=12)),
        vol.Required("percentage"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)

SET_NAME_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
    }
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_TWIST_POSITION):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TWIST_POSITION,
        async_set_twist_position,
        schema=SET_TWIST_POSITION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_NAME,
        async_set_name,
        schema=SET_NAME_SCHEMA,
    )


def _get_client_for_device(hass: HomeAssistant, device_id: str):
    """Return the Flic client for a configured device."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Device {device_id} not found")

    address: str | None = None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            address = identifier
            break

    if address is None:
        raise HomeAssistantError("Device is not a Flic Button device")

    for entry in hass.config_entries.async_entries(DOMAIN):
        if normalize_address(entry.data.get(CONF_ADDRESS, "")) == normalize_address(
            address
        ):
            return entry.runtime_data.client, entry

    raise HomeAssistantError("No Flic Button config entry found for device")


async def async_set_twist_position(call: ServiceCall) -> None:
    """Set Twist position using documented pyflic-ble API."""
    device_ids: list[str] = call.data.get("device_id", [])
    if not device_ids:
        raise HomeAssistantError("Service requires a Flic Twist device target")

    client, entry = _get_client_for_device(call.hass, device_ids[0])
    if not client.capabilities.has_rotation:
        raise HomeAssistantError(
            "set_twist_position only works on devices with rotation (Twist)"
        )
    if not client.capabilities.has_selector:
        raise HomeAssistantError(
            "set_twist_position only works on Flic Twist devices"
        )

    mode_index: int = call.data["mode_index"]
    percentage: float = call.data["percentage"]

    try:
        await client.async_send_update_twist_position(mode_index, percentage)
    except FlicProtocolError as err:
        raise HomeAssistantError(str(err)) from err

    runtime_data = entry.runtime_data
    runtime_data.twist_mode_index = mode_index
    runtime_data.mode_percentage = percentage
    for cb in runtime_data.twist_state_callbacks:
        cb()


async def async_set_name(call: ServiceCall) -> None:
    """Set device name using documented pyflic-ble API."""
    device_ids: list[str] = call.data.get("device_id", [])
    if not device_ids:
        raise HomeAssistantError("Service requires a Flic Button device target")

    client, entry = _get_client_for_device(call.hass, device_ids[0])
    name: str = call.data["name"]

    try:
        new_name, _timestamp = await client.set_name(name)
    except FlicProtocolError as err:
        raise HomeAssistantError(str(err)) from err

    for cb in entry.runtime_data.state_callbacks:
        cb()
