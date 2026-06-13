"""Shared helpers for the Flic Button integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyflic_ble import DeviceType, FlicClient

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_process_advertisements,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import FlicButtonData

from .const import (
    BATTERY_FULL_VOLTAGE,
    BATTERY_LOW_VOLTAGE,
    CONF_PAIRING_ID,
    CONF_PAIRING_KEY,
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

    for cb in data.twist_state_callbacks:
        cb()
