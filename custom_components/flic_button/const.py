"""Constants for the Flic Button integration."""

from __future__ import annotations

from typing import Final

from pyflic_ble import DeviceType

DOMAIN: Final = "flic_button"

DEVICE_TYPE_MODEL_NAMES: Final = {
    DeviceType.FLIC2: "Flic 2",
    DeviceType.DUO: "Flic Duo",
    DeviceType.TWIST: "Flic Twist",
}

# Config entry data keys
CONF_PAIRING_ID: Final = "pairing_id"
CONF_PAIRING_KEY: Final = "pairing_key"
CONF_SERIAL_NUMBER: Final = "serial_number"
CONF_BATTERY_LEVEL: Final = "battery_level"
CONF_DEVICE_TYPE: Final = "device_type"
CONF_SIG_BITS: Final = (
    "sig_bits"  # Ed25519 signature variant (0-3) for Twist quick verify
)

# Event classes
EVENT_CLASS_BUTTON: Final = "button"
EVENT_CLASS_DIAL: Final = "dial"

# Flic event domain
FLIC_BUTTON_EVENT: Final = f"{DOMAIN}_event"

# Device automation
CONF_SUBTYPE: Final = "subtype"
SUBTYPE_BUTTON: Final = "button"
SUBTYPE_BIG: Final = "big"
SUBTYPE_SMALL: Final = "small"

# Options constants
CONF_PUSH_TWIST_MODE: Final = "push_twist_mode"

# Entity keys
SENSOR_BATTERY: Final = "battery"
SENSOR_BATTERY_VOLTAGE: Final = "battery_voltage"
SENSOR_SIGNAL_STRENGTH: Final = "signal_strength"
SENSOR_TWIST_POSITION: Final = "twist_position"
SENSOR_SELECTOR: Final = "selector"
SENSOR_DIAL_BIG: Final = "dial_position_big"
SENSOR_DIAL_SMALL: Final = "dial_position_small"
SENSOR_LAST_EVENT: Final = "last_event"
BINARY_SENSOR_CONNECTED: Final = "connected"
TEXT_DEVICE_NAME: Final = "device_name"

# Service names
SERVICE_SET_TWIST_POSITION: Final = "set_twist_position"
SERVICE_SET_NAME: Final = "set_name"

# Low-battery thresholds (volts). Flic 2 guidance: replace below 2.65 V.
BATTERY_LOW_VOLTAGE: Final = {
    DeviceType.FLIC2: 2.65,
    DeviceType.DUO: 2.65,
    DeviceType.TWIST: 2.4,
}

# Approximate full-battery voltage used for percentage estimation.
BATTERY_FULL_VOLTAGE: Final = {
    DeviceType.FLIC2: 3.0,
    DeviceType.DUO: 3.0,
    DeviceType.TWIST: 3.0,
}
