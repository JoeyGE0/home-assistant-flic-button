"""The Flic Button integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bleak import BleakError
from pyflic_ble import (
    DeviceType,
    FlicAuthenticationError,
    FlicClient,
    FlicPairingError,
    FlicProtocolError,
    PushTwistMode,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_BATTERY_LEVEL,
    CONF_DEVICE_TYPE,
    CONF_PUSH_TWIST_MODE,
    CONF_SERIAL_NUMBER,
    CONF_SIG_BITS,
)
from .helpers import validate_pairing_credentials

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.SENSOR,
]


@dataclass
class FlicButtonData:
    """Runtime data for a Flic Button config entry."""

    client: FlicClient
    serial_number: str | None
    battery_level: int | None


type FlicButtonConfigEntry = ConfigEntry[FlicButtonData]


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

    @callback
    def _async_bluetooth_callback(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle Bluetooth updates for connection/reconnection."""
        client.set_ble_device(service_info.device)

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
