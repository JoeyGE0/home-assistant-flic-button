"""Shared helpers for the Flic Button integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyflic_ble import DeviceType, FlicClient

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_process_advertisements,
)
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, CONF_TYPE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

if TYPE_CHECKING:
    from . import FlicButtonConfigEntry, FlicButtonData

from .const import (
    BATTERY_FULL_VOLTAGE,
    BATTERY_LOW_VOLTAGE,
    CONF_PAIRING_ID,
    CONF_PAIRING_KEY,
    CONF_SUBTYPE,
    DOMAIN,
    FLIC_BUTTON_EVENT,
    SUBTYPE_BIG,
    SUBTYPE_BUTTON,
    SUBTYPE_SMALL,
    TEXT_DEVICE_NAME,
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
def is_device_rename_enabled(hass: HomeAssistant, entry: FlicButtonConfigEntry) -> bool:
    """Return True when the optional on-device rename entity is enabled."""
    entity_registry = er.async_get(hass)
    unique_id = f"{entry.data[CONF_ADDRESS]}-{TEXT_DEVICE_NAME}"
    entity_id = entity_registry.async_get_entity_id("text", DOMAIN, unique_id)
    if entity_id is None:
        return False
    if (reg_entry := entity_registry.async_get(entity_id)) is None:
        return False
    return not reg_entry.disabled


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

    if (
        state.device_name
        and device.name_by_user is None
        and (
            is_device_rename_enabled(hass, entry)
            or not data.initial_name_synced
        )
    ):
        updates["name"] = state.device_name
        data.initial_name_synced = True

    if updates:
        device_registry.async_update_device(device.id, **updates)


def get_config_entry_for_device(
    hass: HomeAssistant, device_id: str
) -> FlicButtonConfigEntry | None:
    """Return the config entry for a Flic device_id."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None:
        return None

    address: str | None = None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            address = identifier
            break

    if address is None:
        return None

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_ADDRESS) == address:
            return entry

    return None


def subtype_for_button_index(button_index: int | None) -> str:
    """Map documented Duo button_index to a device automation subtype."""
    if button_index == 0:
        return SUBTYPE_BIG
    if button_index == 1:
        return SUBTYPE_SMALL
    return SUBTYPE_BUTTON


@callback
def fire_device_automation_event(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    event_type: str,
    event_data: dict[str, Any],
) -> None:
    """Fire a device automation event (Shelly/ZHA pattern) for every press."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.data[CONF_ADDRESS])}
    )
    if device is None:
        return

    button_index = event_data.get("button_index")
    subtype = subtype_for_button_index(
        int(button_index) if button_index is not None else None
    )

    hass.bus.async_fire(
        FLIC_BUTTON_EVENT,
        {
            CONF_DEVICE_ID: device.id,
            CONF_TYPE: event_type,
            CONF_SUBTYPE: subtype,
            **event_data,
        },
    )

