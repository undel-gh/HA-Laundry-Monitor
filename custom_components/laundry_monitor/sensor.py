"""Sensor entities for Laundry Monitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaundryMonitorConfigEntry
from .const import LaundryCycleState
from .entity import LaundryMonitorEntity
from .runtime import LaundryMonitorRuntime


@dataclass(frozen=True, kw_only=True)
class LaundryMonitorSensorDescription(SensorEntityDescription):
    """Describe a Laundry Monitor sensor."""

    value_fn: Callable[[LaundryMonitorRuntime], Any]


SENSOR_DESCRIPTIONS: tuple[LaundryMonitorSensorDescription, ...] = (
    LaundryMonitorSensorDescription(
        key="cycle_state",
        translation_key="cycle_state",
        device_class=SensorDeviceClass.ENUM,
        options=[state.value for state in LaundryCycleState],
        value_fn=lambda runtime: runtime.cycle_state.value,
    ),
    LaundryMonitorSensorDescription(
        key="last_transition_reason",
        translation_key="last_transition_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_transition_reason,
    ),
    LaundryMonitorSensorDescription(
        key="last_state_change",
        translation_key="last_state_change",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_state_change,
    ),     
    LaundryMonitorSensorDescription(
        key="current_power",
        translation_key="current_power",
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        state_class="measurement",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.power,
    ),
    LaundryMonitorSensorDescription(
        key="last_activity",
        translation_key="last_activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_activity,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Laundry Monitor sensor entities."""
    async_add_entities(
        LaundryMonitorSensor(entry.runtime_data, description)
        for description in SENSOR_DESCRIPTIONS
    )


class LaundryMonitorSensor(LaundryMonitorEntity, SensorEntity):
    """Representation of a Laundry Monitor sensor."""

    entity_description: LaundryMonitorSensorDescription

    def __init__(
        self,
        runtime: LaundryMonitorRuntime,
        description: LaundryMonitorSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | datetime | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.runtime)
