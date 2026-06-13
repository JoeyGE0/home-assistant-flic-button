"""The Flic Button integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bleak import BleakError
from pyflic_ble import (
    DeviceType,
    FlicAuthenticationError,
    FlicClient,
    FlicPairingError,
    FlicProtocolError,
    FlicState,
    PushTwistMode,
)
from pyflic_ble.const import EVENT_TYPE_SELECTOR_CHANGED

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_BATTERY_LEVEL,
    CONF_DEVICE_TYPE,
    CONF_PUSH_TWIST_MODE,
    CONF_SERIAL_NUMBER,
    CONF_SIG_BITS,
    DOMAIN,
)
from .helpers import (
    fire_device_automation_event,
    notify_dial_state_update,
    notify_last_event,
    notify_rssi_update,
    notify_twist_state_update,
    sync_ha_device_from_state,
    validate_pairing_credentials,
)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.TEXT,
]


@dataclass
class FlicButtonData:
    """Runtime data for a Flic Button config entry."""

    client: FlicClient
    serial_number: str | None
    battery_level: int | None
    last_voltage: float | None = None
    selector_index: int | None = None
    mode_percentage: float | None = None
    twist_mode_index: int | None = None
    dial_percentage: dict[int, float | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    last_event_type: str | None = None
    last_event_data: dict[str, Any] | None = None
    twist_state_callbacks: list = field(default_factory=list)
    dial_state_callbacks: list = field(default_factory=list)
    last_event_callbacks: list = field(default_factory=list)
    state_callbacks: list = field(default_factory=list)
    rssi_callbacks: list = field(default_factory=list)
    was_connected: bool = False
    initial_name_synced: bool = False
    last_rssi: int | None = None
    last_rssi_source: str | None = None


type FlicButtonConfigEntry = ConfigEntry[FlicButtonData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Flic Button integration."""
    hass.data.setdefault(DOMAIN, {})
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FlicButtonConfigEntry) -> bool:
    """Set up Flic Button from a config entry."""

    address: str = entry.data[CONF_ADDRESS]
    credentials = validate_pairing_credentials(entry.data)
    if credentials is None:
        _LOGGER.error(
            "Config entry for %s has invalid pairing credentials; remove it and pair again",
            address,
        )
        return False

    pairing_id, pairing_key = credentials
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable=True
    )
    serial_number = entry.data.get(CONF_SERIAL_NUMBER)
    battery_level = entry.data.get(CONF_BATTERY_LEVEL)
    device_type = DeviceType(entry.data[CONF_DEVICE_TYPE])
    sig_bits = int(entry.data.get(CONF_SIG_BITS, 0))
    push_twist_mode = PushTwistMode(
        entry.options.get(CONF_PUSH_TWIST_MODE, PushTwistMode.DEFAULT)
    )

    client = FlicClient(
        address=address,
        ble_device=ble_device,
        pairing_id=pairing_id,
        pairing_key=pairing_key,
        serial_number=serial_number,
        device_type=device_type,
        sig_bits=sig_bits,
        push_twist_mode=push_twist_mode,
    )

    entry.runtime_data = FlicButtonData(
        client=client,
        serial_number=serial_number,
        battery_level=battery_level,
    )
    data = entry.runtime_data

    def _on_disconnect() -> None:
        _LOGGER.info(
            "Flic %s disconnected; pyflic-ble will reconnect automatically",
            address,
        )

    client.on_disconnect = _on_disconnect

    @callback
    def _async_on_client_state(state: FlicState) -> None:
        """Sync HA device info and notify connection entities on state changes."""
        if state.connected and not data.was_connected:
            _LOGGER.info("Flic %s connected", address)
        sync_ha_device_from_state(hass, entry)
        data.was_connected = state.connected
        for cb in data.state_callbacks:
            cb()

    @callback
    def _async_track_button_event(event_type: str, event_data: dict[str, Any]) -> None:
        """Track button events for last-event and Twist state sensors."""
        notify_last_event(data, event_type, event_data)
        notify_twist_state_update(data, event_type, event_data)
        fire_device_automation_event(hass, entry, event_type, event_data)

    @callback
    def _async_track_rotate_event(event_type: str, event_data: dict[str, Any]) -> None:
        """Track rotate events for last-event, Twist, and Duo dial sensors."""
        notify_last_event(data, event_type, event_data)
        notify_twist_state_update(data, event_type, event_data)
        notify_dial_state_update(data, event_data)
        fire_device_automation_event(hass, entry, event_type, event_data)

    def _on_selector_change(selector_index: int, extra_data: dict[str, Any]) -> None:
        """Handle documented Twist selector change callback."""
        data.selector_index = selector_index
        event_data = {"selector_index": selector_index, **extra_data}
        notify_last_event(data, EVENT_TYPE_SELECTOR_CHANGED, event_data)
        notify_twist_state_update(data, EVENT_TYPE_SELECTOR_CHANGED, event_data)
        fire_device_automation_event(hass, entry, EVENT_TYPE_SELECTOR_CHANGED, event_data)

    client.on_selector_change = _on_selector_change

    entry.async_on_unload(client.register_state_callback(_async_on_client_state))
    entry.async_on_unload(
        client.register_button_event_callback(_async_track_button_event)
    )
    entry.async_on_unload(
        client.register_rotate_event_callback(_async_track_rotate_event)
    )

    @callback
    def _async_bluetooth_callback(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle Bluetooth updates for connection/reconnection."""
        client.set_ble_device(service_info.device)
        notify_rssi_update(data, service_info.rssi, service_info.source)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_bluetooth_callback,
            BluetoothCallbackMatcher({CONF_ADDRESS: address}),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if ble_device:
        try:
            await client.start()
            sync_ha_device_from_state(hass, entry)
            data.was_connected = client.state.connected
        except (
            TimeoutError,
            BleakError,
            FlicProtocolError,
            FlicAuthenticationError,
            FlicPairingError,
        ) as err:
            # Flic buttons only advertise while pressed. Finish setup and let
            # pyflic-ble reconnect when the button is pressed again.
            _LOGGER.warning(
                "Could not connect to %s during setup (%s); "
                "press the button near your Bluetooth proxy to connect",
                address,
                err,
            )
    elif not client.is_connected:
        _LOGGER.info(
            "Flic %s is out of range; press the button near your Bluetooth proxy to connect",
            address,
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: FlicButtonConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FlicButtonConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.stop()

    return unload_ok
