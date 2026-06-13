"""Sensor platform for Flic Button integration."""

from __future__ import annotations

from typing import Any

from pyflic_ble import FlicState, PushTwistMode

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_ADDRESS, PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfElectricPotential
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FlicButtonConfigEntry, FlicButtonData
from .const import (
    CONF_PUSH_TWIST_MODE,
    SENSOR_BATTERY,
    SENSOR_BATTERY_VOLTAGE,
    SENSOR_DIAL_BIG,
    SENSOR_DIAL_SMALL,
    SENSOR_SELECTOR,
    SENSOR_SIGNAL_STRENGTH,
    SENSOR_TWIST_POSITION,
)
from .entity import FlicButtonEntity
from .helpers import (
    get_battery_voltage,
    is_battery_low,
    notify_rssi_update,
    notify_twist_state_update,
    voltage_to_percentage,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Flic Button sensor entities."""
    data = entry.runtime_data
    capabilities = data.client.capabilities
    entities: list[SensorEntity] = [
        FlicBatterySensor(data),
        FlicBatteryVoltageSensor(data),
        FlicSignalStrengthSensor(hass, entry, data),
    ]

    if capabilities.has_rotation:
        entities.append(FlicTwistPositionSensor(data))
        push_twist_mode = PushTwistMode(
            entry.options.get(CONF_PUSH_TWIST_MODE, PushTwistMode.DEFAULT)
        )
        if capabilities.has_selector and push_twist_mode == PushTwistMode.SELECTOR:
            entities.append(FlicTwistSelectorSensor(data))

    if capabilities.button_count > 1:
        entities.append(FlicDuoDialSensor(data, button_index=0, translation_key=SENSOR_DIAL_BIG))
        entities.append(
            FlicDuoDialSensor(data, button_index=1, translation_key=SENSOR_DIAL_SMALL)
        )

    async_add_entities(entities)


class FlicSignalStrengthSensor(FlicButtonEntity, SensorEntity):
    """BLE signal strength (RSSI in dBm) from advertisement packets."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = SENSOR_SIGNAL_STRENGTH

    def __init__(
        self, hass: HomeAssistant, entry: FlicButtonConfigEntry, data: FlicButtonData
    ) -> None:
        """Initialize the signal strength sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{SENSOR_SIGNAL_STRENGTH}"
        self._attr_suggested_object_id = SENSOR_SIGNAL_STRENGTH
        if service_info := bluetooth.async_last_service_info(
            hass, entry.data[CONF_ADDRESS], connectable=True
        ):
            notify_rssi_update(data, service_info.rssi, service_info.source)

    @property
    def available(self) -> bool:
        """Return True after at least one advertisement was heard."""
        return self._data.last_rssi is not None

    @property
    def native_value(self) -> int | None:
        """Return the latest RSSI in dBm."""
        return self._data.last_rssi

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | None]:
        """Return which scanner heard the button and connection state."""
        return {
            "source": self._data.last_rssi_source,
            "connected": self._client.state.connected,
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks for RSSI updates."""
        await super().async_added_to_hass()

        @callback
        def _async_rssi_changed() -> None:
            self.async_write_ha_state()

        self._data.rssi_callbacks.append(_async_rssi_changed)
        self.async_on_remove(
            lambda: self._data.rssi_callbacks.remove(_async_rssi_changed)
        )


class FlicBatterySensor(FlicButtonEntity, SensorEntity):
    """Estimated battery level for a Flic device."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = SENSOR_BATTERY

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the battery sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{SENSOR_BATTERY}"
        self._attr_suggested_object_id = SENSOR_BATTERY

    @property
    def available(self) -> bool:
        """Return True when a battery reading has ever been available."""
        return get_battery_voltage(self._data) is not None

    @property
    def native_value(self) -> int | None:
        """Return the estimated battery percentage."""
        voltage = get_battery_voltage(self._data)
        if voltage is None:
            return None
        return voltage_to_percentage(voltage, self._client.device_type)

    @property
    def extra_state_attributes(self) -> dict[str, float | bool | None]:
        """Return documented battery and connection attributes."""
        voltage = get_battery_voltage(self._data)
        return {
            "voltage": voltage,
            "battery_low": is_battery_low(voltage, self._client.device_type)
            if voltage is not None
            else None,
            "connected": self._client.state.connected,
        }

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Handle state updates from the client."""
        self.async_write_ha_state()


class FlicBatteryVoltageSensor(FlicButtonEntity, SensorEntity):
    """Optional battery voltage sensor for a Flic device."""

    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_translation_key = SENSOR_BATTERY_VOLTAGE

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the battery voltage sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{SENSOR_BATTERY_VOLTAGE}"
        self._attr_suggested_object_id = SENSOR_BATTERY_VOLTAGE

    @property
    def available(self) -> bool:
        """Return True when a battery reading has ever been available."""
        return get_battery_voltage(self._data) is not None

    @property
    def native_value(self) -> float | None:
        """Return the battery voltage."""
        return get_battery_voltage(self._data)

    @callback
    def _handle_state_update(self, state: FlicState) -> None:
        """Handle state updates from the client."""
        self.async_write_ha_state()


class FlicTwistPositionSensor(FlicButtonEntity, SensorEntity):
    """Current Twist mode position (0-100%) from documented rotate events."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = SENSOR_TWIST_POSITION

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the Twist position sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{SENSOR_TWIST_POSITION}"
        self._attr_suggested_object_id = SENSOR_TWIST_POSITION

    @property
    def native_value(self) -> float | None:
        """Return the current mode percentage."""
        return self._data.mode_percentage

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        """Return documented Twist mode attributes."""
        return {
            "twist_mode_index": self._data.twist_mode_index,
            "selector_index": self._data.selector_index,
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks for Twist state updates."""
        await super().async_added_to_hass()

        @callback
        def _async_twist_state_changed() -> None:
            self.async_write_ha_state()

        self._data.twist_state_callbacks.append(_async_twist_state_changed)
        self.async_on_remove(
            lambda: self._data.twist_state_callbacks.remove(_async_twist_state_changed)
        )


class FlicTwistSelectorSensor(FlicButtonEntity, SensorEntity):
    """Current Twist selector slot (0-11) from documented selector events."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = SENSOR_SELECTOR

    def __init__(self, data: FlicButtonData) -> None:
        """Initialize the Twist selector sensor."""
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{self._client.address}-{SENSOR_SELECTOR}"
        self._attr_suggested_object_id = SENSOR_SELECTOR

    @property
    def native_value(self) -> int | None:
        """Return the current selector index."""
        return self._data.selector_index

    async def async_added_to_hass(self) -> None:
        """Register callbacks for selector updates."""
        await super().async_added_to_hass()

        @callback
        def _async_selector_changed() -> None:
            self.async_write_ha_state()

        self._data.twist_state_callbacks.append(_async_selector_changed)
        self.async_on_remove(
            lambda: self._data.twist_state_callbacks.remove(_async_selector_changed)
        )


class FlicDuoDialSensor(FlicButtonEntity, SensorEntity):
    """Duo dial position (0-100%) from documented dial_percentage rotate events."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, data: FlicButtonData, button_index: int, translation_key: str
    ) -> None:
        """Initialize a Duo dial position sensor."""
        super().__init__(data)
        self._data = data
        self._button_index = button_index
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{self._client.address}-{translation_key}"
        self._attr_suggested_object_id = translation_key

    @property
    def native_value(self) -> float | None:
        """Return the dial percentage for this button."""
        return self._data.dial_percentage.get(self._button_index)

    async def async_added_to_hass(self) -> None:
        """Register callbacks for dial state updates."""
        await super().async_added_to_hass()

        @callback
        def _async_dial_changed() -> None:
            self.async_write_ha_state()

        self._data.dial_state_callbacks.append(_async_dial_changed)
        self.async_on_remove(
            lambda: self._data.dial_state_callbacks.remove(_async_dial_changed)
        )
