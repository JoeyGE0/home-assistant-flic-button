"""Event platform for Flic Button integration."""

from __future__ import annotations

from typing import Any

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

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FlicButtonConfigEntry, FlicButtonData
from .const import CONF_PUSH_TWIST_MODE, EVENT_CLASS_BUTTON, EVENT_CLASS_DIAL
from .entity import FlicButtonEntity
from .helpers import notify_twist_state_update

PARALLEL_UPDATES = 0

# Semantic button events only (no raw up/down press-release lifecycle).
CORE_BUTTON_EVENT_TYPES: list[str] = [
    EVENT_TYPE_CLICK,
    EVENT_TYPE_DOUBLE_CLICK,
    EVENT_TYPE_HOLD,
]

DUO_GESTURE_EVENT_TYPES: list[str] = [
    EVENT_TYPE_SWIPE_LEFT,
    EVENT_TYPE_SWIPE_RIGHT,
    EVENT_TYPE_SWIPE_UP,
    EVENT_TYPE_SWIPE_DOWN,
]

DUO_DIAL_EVENT_TYPES: list[str] = [
    EVENT_TYPE_ROTATE_CLOCKWISE,
    EVENT_TYPE_ROTATE_COUNTER_CLOCKWISE,
]

FLIC2_BUTTON_DESCRIPTION = EventEntityDescription(
    key=EVENT_CLASS_BUTTON,
    translation_key=EVENT_CLASS_BUTTON,
    event_types=CORE_BUTTON_EVENT_TYPES,
    device_class=EventDeviceClass.BUTTON,
)

TWIST_SELECTOR_BUTTON_DESCRIPTION = EventEntityDescription(
    key=f"{EVENT_CLASS_BUTTON}_twist",
    translation_key="button_twist",
    event_types=[
        *CORE_BUTTON_EVENT_TYPES,
        EVENT_TYPE_ROTATE_CLOCKWISE,
        EVENT_TYPE_ROTATE_COUNTER_CLOCKWISE,
        EVENT_TYPE_SELECTOR_CHANGED,
    ],
    device_class=EventDeviceClass.BUTTON,
)

TWIST_DEFAULT_BUTTON_DESCRIPTION = EventEntityDescription(
    key=f"{EVENT_CLASS_BUTTON}_twist",
    translation_key="button_twist_default",
    event_types=[
        *CORE_BUTTON_EVENT_TYPES,
        EVENT_TYPE_TWIST_INCREMENT,
        EVENT_TYPE_TWIST_DECREMENT,
        EVENT_TYPE_PUSH_TWIST_INCREMENT,
        EVENT_TYPE_PUSH_TWIST_DECREMENT,
    ],
    device_class=EventDeviceClass.BUTTON,
)


def _duo_button_event_types(capabilities) -> list[str]:
    """Build Duo button event types using documented capabilities."""
    event_types = list(CORE_BUTTON_EVENT_TYPES)
    if capabilities.has_gestures:
        event_types.extend(DUO_GESTURE_EVENT_TYPES)
    return event_types


def _duo_button_description(key: str, translation_key: str, event_types: list[str]):
    """Create a Duo button event entity description."""
    return EventEntityDescription(
        key=key,
        translation_key=translation_key,
        event_types=event_types,
        device_class=EventDeviceClass.BUTTON,
    )


def _duo_dial_description(key: str, translation_key: str):
    """Create a Duo dial event entity description."""
    return EventEntityDescription(
        key=key,
        translation_key=translation_key,
        event_types=DUO_DIAL_EVENT_TYPES,
        device_class=EventDeviceClass.BUTTON,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlicButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Flic Button event entity."""
    data = entry.runtime_data
    capabilities = data.client.capabilities
    entities: list[FlicButtonEventEntity | FlicButtonDialEventEntity] = []

    push_twist_mode = PushTwistMode(
        entry.options.get(CONF_PUSH_TWIST_MODE, PushTwistMode.DEFAULT)
    )

    if capabilities.has_selector and push_twist_mode == PushTwistMode.SELECTOR:
        entities.append(
            FlicButtonEventEntity(
                data, TWIST_SELECTOR_BUTTON_DESCRIPTION, is_twist=True
            )
        )
    elif capabilities.has_selector:
        entities.append(
            FlicButtonEventEntity(data, TWIST_DEFAULT_BUTTON_DESCRIPTION, is_twist=True)
        )
    elif capabilities.button_count == 1:
        entities.append(FlicButtonEventEntity(data, FLIC2_BUTTON_DESCRIPTION))
    else:
        duo_button_types = _duo_button_event_types(capabilities)
        entities.append(
            FlicButtonEventEntity(
                data,
                _duo_button_description(
                    f"{EVENT_CLASS_BUTTON}_big", "button_big", duo_button_types
                ),
                button_index=0,
            )
        )
        entities.append(
            FlicButtonEventEntity(
                data,
                _duo_button_description(
                    f"{EVENT_CLASS_BUTTON}_small", "button_small", duo_button_types
                ),
                button_index=1,
            )
        )
        if capabilities.has_rotation:
            entities.append(
                FlicButtonDialEventEntity(
                    data,
                    _duo_dial_description(f"{EVENT_CLASS_DIAL}_big", "dial_big"),
                    button_index=0,
                )
            )
            entities.append(
                FlicButtonDialEventEntity(
                    data,
                    _duo_dial_description(f"{EVENT_CLASS_DIAL}_small", "dial_small"),
                    button_index=1,
                )
            )

    async_add_entities(entities)


class FlicButtonEventEntity(FlicButtonEntity, EventEntity):
    """Representation of a Flic button event entity."""

    def __init__(
        self,
        data: FlicButtonData,
        description: EventEntityDescription,
        button_index: int | None = None,
        is_twist: bool = False,
    ) -> None:
        """Initialize the event entity."""
        super().__init__(data)
        self.entity_description = description
        self._data = data
        self._button_index = button_index
        self._is_twist = is_twist
        self._attr_unique_id = f"{self._client.address}-{description.key}"

    async def async_added_to_hass(self) -> None:
        """Register event callbacks when entity is added."""
        await super().async_added_to_hass()

        self.async_on_remove(
            self._client.register_button_event_callback(
                self._async_handle_event,
            )
        )

        if self._client.capabilities.has_rotation and self._is_twist:
            self.async_on_remove(
                self._client.register_rotate_event_callback(
                    self._async_handle_rotate_event,
                )
            )

    @callback
    def _async_handle_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Handle button event from client."""
        if (
            self.entity_description.event_types is not None
            and event_type not in self.entity_description.event_types
        ):
            return

        if self._button_index is not None:
            event_button_index = event_data.get("button_index")
            if event_button_index != self._button_index:
                return

        if self._is_twist:
            notify_twist_state_update(self._data, event_type, event_data)

        self._trigger_event(event_type, event_data)
        self.async_write_ha_state()

    @callback
    def _async_handle_rotate_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> None:
        """Handle rotate event from client."""
        if (
            self.entity_description.event_types is not None
            and event_type not in self.entity_description.event_types
        ):
            return

        notify_twist_state_update(self._data, event_type, event_data)
        self._trigger_event(event_type, event_data)
        self.async_write_ha_state()


class FlicButtonDialEventEntity(FlicButtonEntity, EventEntity):
    """Representation of a Flic Duo dial rotation event entity."""

    def __init__(
        self,
        data: FlicButtonData,
        description: EventEntityDescription,
        button_index: int,
    ) -> None:
        """Initialize the dial event entity."""
        super().__init__(data)
        self.entity_description = description
        self._button_index = button_index
        self._attr_unique_id = f"{self._client.address}-{description.key}"

    async def async_added_to_hass(self) -> None:
        """Register rotate callbacks when entity is added."""
        await super().async_added_to_hass()

        self.async_on_remove(
            self._client.register_rotate_event_callback(
                self._async_handle_rotate_event,
            )
        )

    @callback
    def _async_handle_rotate_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> None:
        """Handle rotate event from client."""
        if (
            self.entity_description.event_types is not None
            and event_type not in self.entity_description.event_types
        ):
            return

        event_button_index = event_data.get("button_index")
        if event_button_index != self._button_index:
            return

        self._trigger_event(event_type, event_data)
        self.async_write_ha_state()
