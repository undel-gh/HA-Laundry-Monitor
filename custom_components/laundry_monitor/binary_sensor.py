"""Binary sensor entities for Laundry Monitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaundryMonitorConfigEntry
from .const import CONF_LEAK_SENSOR, LaundryCycleState
from .entity import LaundryMonitorEntity
from .runtime import LaundryMonitorRuntime


@dataclass(frozen=True, kw_only=True)
class LaundryMonitorBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Laundry Monitor binary sensor."""

    value_fn: Callable[[LaundryMonitorRuntime], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[
    LaundryMonitorBinarySensorDescription, ...
] = (
    LaundryMonitorBinarySensorDescription(
        key="running",
        translation_key="running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda runtime: runtime.cycle_state
        in (LaundryCycleState.RUNNING, LaundryCycleState.FINAL_SPIN),
    ),
    LaundryMonitorBinarySensorDescription(
        key="finished",
        translation_key="finished",
        value_fn=lambda runtime: runtime.cycle_state
        is LaundryCycleState.FINISHED,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Laundry Monitor binary sensor entities."""
    runtime = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        LaundryMonitorBinarySensor(runtime, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]

    if entry.data.get(CONF_LEAK_SENSOR):
        entities.append(LaundryMonitorLeakBinarySensor(runtime))

    if runtime.tracking_enabled:
        entities.append(LaundryMonitorLaundryPresentBinarySensor(runtime))

    async_add_entities(entities)


class LaundryMonitorBinarySensor(
    LaundryMonitorEntity,
    BinarySensorEntity,
):
    """Representation of a Laundry Monitor binary sensor."""

    entity_description: LaundryMonitorBinarySensorDescription

    def __init__(
        self,
        runtime: LaundryMonitorRuntime,
        description: LaundryMonitorBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the binary sensor state."""
        return self.entity_description.value_fn(self.runtime)


class LaundryMonitorLeakBinarySensor(
    LaundryMonitorEntity,
    BinarySensorEntity,
):
    """Expose the configured leak sensor through Laundry Monitor."""

    _attr_translation_key = "leak"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: LaundryMonitorRuntime) -> None:
        """Initialize the leak binary sensor."""
        super().__init__(runtime, "leak")

    @property
    def is_on(self) -> bool:
        """Return whether a leak is detected."""
        return self.runtime.leak_detected


class LaundryMonitorLaundryPresentBinarySensor(
    LaundryMonitorEntity,
    BinarySensorEntity,
):
    """Expose whether laundry is believed to remain in the machine."""

    _attr_translation_key = "laundry_present"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, runtime: LaundryMonitorRuntime) -> None:
        """Initialize the laundry-presence sensor."""
        super().__init__(runtime, "laundry_present")

    @property
    def is_on(self) -> bool:
        """Return whether laundry is present."""
        return self.runtime.laundry_present
