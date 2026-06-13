"""Config flow for Flic Button integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from bleak import BleakError
from pyflic_ble import (
    DeviceType,
    FlicAuthenticationError,
    FlicClient,
    FlicPairingError,
    FlicProtocolError,
    PushTwistMode,
)
from pyflic_ble.const import FLIC_SERVICE_UUID, PAIRING_TIMEOUT, TWIST_SERVICE_UUID
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_process_advertisements,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_BATTERY_LEVEL,
    CONF_DEVICE_TYPE,
    CONF_PAIRING_ID,
    CONF_PAIRING_KEY,
    CONF_PUSH_TWIST_MODE,
    CONF_SERIAL_NUMBER,
    CONF_SIG_BITS,
    DEVICE_TYPE_MODEL_NAMES,
    DOMAIN,
)
from .helpers import (
    ADVERTISEMENT_WAIT_SECONDS,
    PAIR_CONNECT_ATTEMPTS,
)

if TYPE_CHECKING:
    from . import FlicButtonConfigEntry

_LOGGER = logging.getLogger(__name__)


class FlicButtonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flic Button."""

    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._device_type: DeviceType = DeviceType.FLIC2
        self._discovery_task: asyncio.Task[BluetoothServiceInfoBleak] | None = None
        self._pair_task: asyncio.Task[dict[str, Any]] | None = None
        self._pair_error: str | None = None

    @callback
    def async_remove(self) -> None:
        """Clean up discovery task when the flow is removed."""
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
        if self._pair_task and not self._pair_task.done():
            self._pair_task.cancel()

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: FlicButtonConfigEntry) -> bool:
        """Only show options for Twist devices."""
        return config_entry.data.get(CONF_DEVICE_TYPE) == DeviceType.TWIST.value

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: FlicButtonConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return FlicButtonOptionsFlowHandler()

    def _is_unconfigured_flic_device(
        self, service_info: BluetoothServiceInfoBleak
    ) -> bool:
        """Check if a discovered BLE device is a Flic button not yet configured."""
        service_uuids = [str(uuid).lower() for uuid in service_info.service_uuids]
        if (
            FLIC_SERVICE_UUID.lower() not in service_uuids
            and TWIST_SERVICE_UUID.lower() not in service_uuids
        ):
            return False
        return service_info.address not in self._async_current_ids(include_ignore=False)

    def _set_device_type_from_discovery(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> None:
        """Detect Flic device type from advertisement service UUIDs."""
        service_uuids = [str(uuid).lower() for uuid in discovery_info.service_uuids]
        if TWIST_SERVICE_UUID.lower() in service_uuids:
            self._device_type = DeviceType.TWIST
        else:
            self._device_type = DeviceType.FLIC2

    def _pairing_description_placeholders(self) -> dict[str, str]:
        """Shared placeholders for pairing instructions."""
        return {"timeout": str(int(PAIRING_TIMEOUT))}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated setup."""
        if self._discovery_task:
            if not self._discovery_task.done():
                return self.async_show_progress(
                    step_id="user",
                    progress_action="wait_for_discovery",
                    progress_task=self._discovery_task,
                    description_placeholders=self._pairing_description_placeholders(),
                )

            try:
                self._discovery_info = self._discovery_task.result()
            except TimeoutError:
                self._discovery_task = None
                return self.async_abort(reason="no_devices_found")
            finally:
                self._discovery_task = None

            return self.async_show_progress_done(next_step_id="discovery_done")

        if self._discovery_info is not None:
            return await self.async_step_pair(None)

        if user_input is None:
            self._set_confirm_only()
            return self.async_show_form(
                step_id="user",
                description_placeholders=self._pairing_description_placeholders(),
            )

        self._discovery_task = self.hass.async_create_task(
            self._async_wait_for_flic_device(), eager_start=False
        )

        return self.async_show_progress(
            step_id="user",
            progress_action="wait_for_discovery",
            progress_task=self._discovery_task,
            description_placeholders=self._pairing_description_placeholders(),
        )

    async def async_step_discovery_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle transition after discovery progress completes."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_devices_found")
        return await self.async_step_pair(None)

    async def _async_wait_for_flic_device(self) -> BluetoothServiceInfoBleak:
        """Wait for a Flic device to appear via Bluetooth advertisements."""
        return await async_process_advertisements(
            self.hass,
            self._is_unconfigured_flic_device,
            {"connectable": True},
            BluetoothScanningMode.ACTIVE,
            PAIRING_TIMEOUT,
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._set_device_type_from_discovery(discovery_info)
        _LOGGER.debug(
            "Discovered Bluetooth device during config flow: %s, service_uuids=%s, connectable: %s",
            discovery_info.address,
            discovery_info.service_uuids,
            discovery_info.connectable,
        )

        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle bluetooth confirmation step."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_devices_found")

        self._abort_if_unique_id_configured()

        if user_input is None:
            self._set_confirm_only()
            name = self._discovery_info.name or self._discovery_info.address
            placeholders = {
                "name": name,
                **self._pairing_description_placeholders(),
            }
            return self.async_show_form(
                step_id="bluetooth_confirm",
                description_placeholders=placeholders,
            )

        return await self.async_step_pair(None)

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle pairing step."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_devices_found")

        if self._pair_task is not None:
            if not self._pair_task.done():
                return self.async_show_progress(
                    step_id="pair",
                    progress_action="pairing",
                    progress_task=self._pair_task,
                    description_placeholders=self._pairing_description_placeholders(),
                )
            return self.async_show_progress_done(next_step_id="pair_done")

        errors: dict[str, str] = {}
        if self._pair_error:
            errors["base"] = self._pair_error
            self._pair_error = None

        if user_input is not None and not errors:
            self._pair_task = self.hass.async_create_task(
                self._async_pair_device(),
                name=f"{DOMAIN}_pair_{self._discovery_info.address}",
            )
            return self.async_show_progress(
                step_id="pair",
                progress_action="pairing",
                progress_task=self._pair_task,
                description_placeholders=self._pairing_description_placeholders(),
            )

        name = self._discovery_info.name or self._discovery_info.address
        return self.async_show_form(
            step_id="pair",
            errors=errors,
            description_placeholders={
                "name": name,
                **self._pairing_description_placeholders(),
            },
        )

    async def async_step_pair_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish pairing after the progress task completes."""
        if self._discovery_info is None or self._pair_task is None:
            return self.async_abort(reason="no_devices_found")

        try:
            entry_data = self._pair_task.result()
        except (TimeoutError, BleakError, FlicProtocolError):
            self._pair_error = "cannot_connect"
        except FlicPairingError:
            self._pair_error = "pairing_failed"
        except FlicAuthenticationError:
            self._pair_error = "invalid_signature"
        except Exception:
            _LOGGER.exception("Unexpected exception during pairing")
            self._pair_error = "unknown"
        else:
            final_device_type = DeviceType(entry_data[CONF_DEVICE_TYPE])
            model_name = DEVICE_TYPE_MODEL_NAMES[final_device_type]
            serial_number = entry_data[CONF_SERIAL_NUMBER]
            return self.async_create_entry(
                title=f"{model_name} ({serial_number})",
                data=entry_data,
                description="default",
            )
        finally:
            self._pair_task = None

        return await self.async_step_pair(None)

    async def _async_pair_device(self) -> dict[str, Any]:
        """Pair with retries while the button is held near a Bluetooth proxy."""
        if self._discovery_info is None:
            raise FlicPairingError("Discovery info missing")

        address = self._discovery_info.address
        last_error: Exception | None = None

        for attempt in range(1, PAIR_CONNECT_ATTEMPTS + 1):
            _LOGGER.info(
                "Pairing attempt %s/%s for %s via Bluetooth proxy",
                attempt,
                PAIR_CONNECT_ATTEMPTS,
                address,
            )

            def _matches(info: BluetoothServiceInfoBleak) -> bool:
                return info.address.upper() == address.upper() and info.connectable

            try:
                discovery = await async_process_advertisements(
                    self.hass,
                    _matches,
                    {"connectable": True},
                    BluetoothScanningMode.ACTIVE,
                    ADVERTISEMENT_WAIT_SECONDS,
                )
            except TimeoutError as err:
                last_error = err
                _LOGGER.warning(
                    "Attempt %s: Flic %s not advertising; keep holding the button",
                    attempt,
                    address,
                )
                continue

            client = FlicClient(
                address=address,
                ble_device=discovery.device,
                device_type=self._device_type,
            )
            try:
                await client.connect()
                (
                    pairing_id,
                    pairing_key,
                    serial_number,
                    battery_level,
                    sig_bits,
                    _,
                    _,
                ) = await asyncio.wait_for(
                    client.full_verify_pairing(),
                    timeout=PAIRING_TIMEOUT,
                )
            except (
                TimeoutError,
                BleakError,
                FlicProtocolError,
                FlicPairingError,
                FlicAuthenticationError,
            ) as err:
                last_error = err
                _LOGGER.warning(
                    "Attempt %s: pairing failed for %s: %s",
                    attempt,
                    address,
                    err,
                )
            else:
                final_device_type = (
                    DeviceType.TWIST
                    if self._device_type == DeviceType.TWIST
                    else DeviceType.from_serial_number(serial_number)
                )
                return {
                    CONF_ADDRESS: address,
                    CONF_PAIRING_ID: int(pairing_id),
                    CONF_PAIRING_KEY: pairing_key.hex(),
                    CONF_SERIAL_NUMBER: serial_number,
                    CONF_BATTERY_LEVEL: battery_level,
                    CONF_DEVICE_TYPE: final_device_type.value,
                    CONF_SIG_BITS: int(sig_bits),
                }
            finally:
                await client.stop()

            if attempt < PAIR_CONNECT_ATTEMPTS:
                await asyncio.sleep(2)

        if isinstance(last_error, FlicAuthenticationError):
            raise last_error
        if isinstance(last_error, FlicPairingError):
            raise last_error
        if isinstance(last_error, (TimeoutError, BleakError, FlicProtocolError)):
            raise last_error
        raise FlicPairingError("Pairing failed after multiple attempts")


class FlicButtonOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Flic Button integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_mode = self.config_entry.options.get(
            CONF_PUSH_TWIST_MODE, PushTwistMode.DEFAULT
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PUSH_TWIST_MODE, default=current_mode
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                PushTwistMode.DEFAULT.value,
                                PushTwistMode.CONTINUOUS.value,
                                PushTwistMode.SELECTOR.value,
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_PUSH_TWIST_MODE,
                        )
                    ),
                }
            ),
        )
