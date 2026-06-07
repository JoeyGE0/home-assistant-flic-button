"""Shared helpers for the Flic Button integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_process_advertisements,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import CONF_PAIRING_ID, CONF_PAIRING_KEY

PAIR_CONNECT_ATTEMPTS = 3
ADVERTISEMENT_WAIT_SECONDS = 20


async def async_wait_for_flic_advertisement(
    hass: HomeAssistant,
    address: str,
    timeout: float = ADVERTISEMENT_WAIT_SECONDS,
) -> bool:
    """Return True when the Flic is actively advertising (usually while pressed)."""

    def _matches(info) -> bool:
        return (
            info.address.upper() == address.upper()
            and info.connectable
        )

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
