"""Device automations for Flic Button (Shelly/ZHA event-bus pattern)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from pyflic_ble import PushTwistMode
from pyflic_ble.const import (
    EVENT_TYPE_CLICK,
    EVENT_TYPE_DOUBLE_CLICK,
    EVENT_TYPE_HOLD,
    EVENT_TYPE_PUSH_TWIST_DECREMENT,
    EVENT_TYPE_PUSH_TWIST_INCREMENT,
    EVENT_TYPE_ROTATE_CLOCKWISE,
    EVENT_TYPE_ROTATE_COUNTER_CLOCKWISE,
    EVENT_TYPE_SELECTOR_CHANGED,
    EVENT_TYPE_SWIPE_DOWN,
    EVENT_TYPE_SWIPE_LEFT,
    EVENT_TYPE_SWIPE_RIGHT,
    EVENT_TYPE_SWIPE_UP,
    EVENT_TYPE_TWIST_DECREMENT,
    EVENT_TYPE_TWIST_INCREMENT,
)

from homeassistant.components.device_automation import (
    DEVICE_TRIGGER_BASE_SCHEMA,
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_PUSH_TWIST_MODE,
    CONF_SUBTYPE,
    DOMAIN,
    FLIC_BUTTON_EVENT,
    SUBTYPE_BIG,
    SUBTYPE_BUTTON,
    SUBTYPE_SMALL,
)
from .helpers import get_config_entry_for_device

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): str,
        vol.Required(CONF_SUBTYPE): vol.In({SUBTYPE_BUTTON, SUBTYPE_BIG, SUBTYPE_SMALL}),
    }
)

CORE_BUTTON_EVENTS: tuple[str, ...] = (
    EVENT_TYPE_CLICK,
    EVENT_TYPE_DOUBLE_CLICK,
    EVENT_TYPE_HOLD,
)

GESTURE_EVENTS: tuple[str, ...] = (
    EVENT_TYPE_SWIPE_LEFT,
    EVENT_TYPE_SWIPE_RIGHT,
    EVENT_TYPE_SWIPE_UP,
    EVENT_TYPE_SWIPE_DOWN,
)

ROTATE_EVENTS: tuple[str, ...] = (
    EVENT_TYPE_ROTATE_CLOCKWISE,
    EVENT_TYPE_ROTATE_COUNTER_CLOCKWISE,
)

TWIST_DEFAULT_EVENTS: tuple[str, ...] = (
    EVENT_TYPE_TWIST_INCREMENT,
    EVENT_TYPE_TWIST_DECREMENT,
    EVENT_TYPE_PUSH_TWIST_INCREMENT,
    EVENT_TYPE_PUSH_TWIST_DECREMENT,
)


def _device_subtypes(capabilities: Any) -> tuple[str, ...]:
    """Return device automation subtypes for the device capabilities."""
    if capabilities.button_count > 1:
        return (SUBTYPE_BIG, SUBTYPE_SMALL)
    return (SUBTYPE_BUTTON,)


def _supported_triggers(
    capabilities: Any, push_twist_mode: PushTwistMode
) -> set[tuple[str, str]]:
    """Return supported (event_type, subtype) pairs for device automations."""
    triggers: set[tuple[str, str]] = set()

    for subtype in _device_subtypes(capabilities):
        for event_type in CORE_BUTTON_EVENTS:
            triggers.add((event_type, subtype))
        if capabilities.has_gestures:
            for event_type in GESTURE_EVENTS:
                triggers.add((event_type, subtype))

    if capabilities.has_rotation:
        if capabilities.has_selector:
            if push_twist_mode == PushTwistMode.SELECTOR:
                for event_type in (
                    *ROTATE_EVENTS,
                    EVENT_TYPE_SELECTOR_CHANGED,
                    *CORE_BUTTON_EVENTS,
                ):
                    triggers.add((event_type, SUBTYPE_BUTTON))
            else:
                for event_type in (*TWIST_DEFAULT_EVENTS, *CORE_BUTTON_EVENTS):
                    triggers.add((event_type, SUBTYPE_BUTTON))
        elif capabilities.button_count > 1:
            for subtype in (SUBTYPE_BIG, SUBTYPE_SMALL):
                for event_type in ROTATE_EVENTS:
                    triggers.add((event_type, subtype))

    return triggers


async def async_validate_trigger_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate a device automation trigger config."""
    config = TRIGGER_SCHEMA(config)
    entry = get_config_entry_for_device(hass, config[CONF_DEVICE_ID])
    if entry is None:
        return config

    client = entry.runtime_data.client
    push_twist_mode = PushTwistMode(
        entry.options.get(CONF_PUSH_TWIST_MODE, PushTwistMode.DEFAULT)
    )
    trigger = (config[CONF_TYPE], config[CONF_SUBTYPE])
    if trigger not in _supported_triggers(client.capabilities, push_twist_mode):
        raise InvalidDeviceAutomationConfig(
            translation_domain=DOMAIN,
            translation_key="invalid_trigger",
            translation_placeholders={"trigger": str(trigger)},
        )
    return config


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device automation triggers for a Flic device."""
    entry = get_config_entry_for_device(hass, device_id)
    if entry is None:
        raise InvalidDeviceAutomationConfig(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device": device_id},
        )

    client = entry.runtime_data.client
    push_twist_mode = PushTwistMode(
        entry.options.get(CONF_PUSH_TWIST_MODE, PushTwistMode.DEFAULT)
    )

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: event_type,
            CONF_SUBTYPE: subtype,
        }
        for event_type, subtype in sorted(_supported_triggers(
            client.capabilities, push_twist_mode
        ))
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device automation trigger (fires on every matching bus event)."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: FLIC_BUTTON_EVENT,
            event_trigger.CONF_EVENT_DATA: {
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
                CONF_TYPE: config[CONF_TYPE],
                CONF_SUBTYPE: config[CONF_SUBTYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
