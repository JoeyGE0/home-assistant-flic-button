"""Shared helpers for the Flic Button integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyflic_ble import DeviceType, FlicClient

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_process_advertisements,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

if TYPE_CHECKING:
    from . import FlicButtonConfigEntry, FlicButtonData

from .const import (
    BATTERY_FULL_VOLTAGE,
    BATTERY_LOW_VOLTAGE,
    CONF_PAIRING_ID,
    CONF_PAIRING_KEY,
    DOMAIN,
)

PAIR_CONNECT_ATTEMPTS = 3
ADVERTISEMENT_WAIT_SECONDS = 20


async def async_wait_for_flic_advertisement(
    hass: HomeAssistant,
    address: str,
    timeout: float = ADVERTISEMENT_WAIT_SECONDS,
) -> bool:
    """Return True when the Flic is actively advertising (usually while pressed)."""

    def _matches(info) -> bool:
        return info.address.upper() == address.upper() and info.connectable

    try:
        await async_process_advertisements(
            hass,
            _matches,
            {"connectable": True},
            BluetoothScanningMode.ACTIVE,
            timeout,
        )
    except TimeoutError:
        return False
    return True


def validate_pairing_credentials(entry_data: dict[str, Any]) -> tuple[int, bytes] | None:
    """Return (pairing_id, pairing_key) when valid, else None."""
    if CONF_PAIRING_ID not in entry_data or CONF_PAIRING_KEY not in entry_data:
        return None

    try:
        pairing_id = int(entry_data[CONF_PAIRING_ID])
    except (TypeError, ValueError):
        return None

    try:
        pairing_key = bytes.fromhex(str(entry_data[CONF_PAIRING_KEY]))
    except ValueError:
        return None

    if not pairing_key:
        return None

    return pairing_id, pairing_key


def get_battery_voltage(data: FlicButtonData) -> float | None:
    """Return the best-known battery voltage for a Flic device."""
    client = data.client
    if client.state.battery_voltage is not None:
        data.last_voltage = client.state.battery_voltage
        return data.last_voltage
    if data.last_voltage is not None:
        return data.last_voltage
    if data.battery_level is not None:
        voltage = FlicClient.battery_raw_to_voltage(
            int(data.battery_level), client.device_type
        )
        data.last_voltage = voltage
        return voltage
    return None


def voltage_to_percentage(voltage: float, device_type: DeviceType) -> int:
    """Estimate battery percentage from voltage using documented thresholds."""
    low = BATTERY_LOW_VOLTAGE[device_type]
    full = BATTERY_FULL_VOLTAGE[device_type]
    if voltage >= full:
        return 100
    if voltage <= low:
        return 0
    return round((voltage - low) / (full - low) * 100)


def is_battery_low(voltage: float, device_type: DeviceType) -> bool:
    """Return True when voltage is below the documented replacement threshold."""
    return voltage < BATTERY_LOW_VOLTAGE[device_type]


def _notify_callbacks(callbacks: list) -> None:
    """Invoke registered entity callbacks."""
    for cb in callbacks:
        cb()


def notify_twist_state_update(
    data: FlicButtonData, event_type: str, event_data: dict[str, Any]
) -> None:
    """Update cached Twist state from documented event fields."""
    from pyflic_ble.const import EVENT_TYPE_SELECTOR_CHANGED

    if event_type == EVENT_TYPE_SELECTOR_CHANGED:
        if (selector_index := event_data.get("selector_index")) is not None:
            data.selector_index = int(selector_index)
    if (twist_mode_index := event_data.get("twist_mode_index")) is not None:
        data.twist_mode_index = int(twist_mode_index)
    if (mode_percentage := event_data.get("mode_percentage")) is not None:
        data.mode_percentage = float(mode_percentage)
    if (selector_index := event_data.get("selector_index")) is not None:
        data.selector_index = int(selector_index)

    _notify_callbacks(data.twist_state_callbacks)


def notify_dial_state_update(data: FlicButtonData, event_data: dict[str, Any]) -> None:
    """Update cached Duo dial percentage from documented rotate event fields."""
    button_index = event_data.get("button_index")
    dial_percentage = event_data.get("dial_percentage")
    if button_index is None or dial_percentage is None:
        return
    data.dial_percentage[int(button_index)] = float(dial_percentage)
    _notify_callbacks(data.dial_state_callbacks)


def notify_last_event(
    data: FlicButtonData, event_type: str, event_data: dict[str, Any]
) -> None:
    """Store the most recent event for the last-event sensor."""
    data.last_event_type = event_type
    data.last_event_data = dict(event_data)
    _notify_callbacks(data.last_event_callbacks)


@callback
def sync_ha_device_from_state(
    hass: HomeAssistant, entry: FlicButtonConfigEntry
) -> None:
    """Sync HA device registry from documented FlicState fields."""
    data = entry.runtime_data
    client = data.client
    state = client.state

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, client.address)})
    if device is None:
        return

    updates: dict[str, str] = {}
    if state.firmware_version is not None:
        updates["sw_version"] = str(state.firmware_version)
    if state.device_name and device.name_by_user is None:
        updates["name"] = state.device_name

    if updates:
        device_registry.async_update_device(device.id, **updates)

