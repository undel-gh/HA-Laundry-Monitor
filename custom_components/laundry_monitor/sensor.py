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
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfPower,
    UnitOfRatio,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaundryMonitorConfigEntry
from .const import CONF_ENERGY_SENSOR, LaundryCycleState
from .entity import LaundryMonitorEntity
from .runtime import LaundryMonitorRuntime


@dataclass(frozen=True, kw_only=True)
class LaundryMonitorSensorDescription(SensorEntityDescription):
    """Describe a Laundry Monitor sensor."""

    value_fn: Callable[[LaundryMonitorRuntime], Any]
    unit_fn: Callable[[LaundryMonitorRuntime], str | None] | None = None


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
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.power,
    ),
    LaundryMonitorSensorDescription(
        key="current_cycle_duration",
        translation_key="current_cycle_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda runtime: runtime.current_cycle_duration,
    ),
    LaundryMonitorSensorDescription(
        key="last_cycle_duration",
        translation_key="last_cycle_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda runtime: runtime.last_cycle_duration,
    ),
    LaundryMonitorSensorDescription(
        key="last_activity",
        translation_key="last_activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_activity,
    ),
    LaundryMonitorSensorDescription(
        key="final_spin_confidence",
        translation_key="final_spin_confidence",
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: round(
            runtime.final_spin_confidence * 100,
        ),
    ),
    LaundryMonitorSensorDescription(
        key="final_spin_evidence_count",
        translation_key="final_spin_evidence_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.final_spin_evidence_count,
    ),
    LaundryMonitorSensorDescription(
        key="finish_quiet_since", translation_key="finish_quiet_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.finish_quiet_since,
    ),
    LaundryMonitorSensorDescription(
        key="finish_deadline", translation_key="finish_deadline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.finish_deadline,
    ),
    LaundryMonitorSensorDescription(
        key="finish_remaining", translation_key="finish_remaining",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.finish_remaining_seconds,
    ),
    LaundryMonitorSensorDescription(
        key="rejected_transition_count",
        translation_key="rejected_transition_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.rejected_transition_count,
    ),
    LaundryMonitorSensorDescription(
        key="last_rejected_transition",
        translation_key="last_rejected_transition",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_rejected_transition,
    ),
)

ENERGY_SENSOR_DESCRIPTIONS: tuple[
    LaundryMonitorSensorDescription, ...
] = (
    LaundryMonitorSensorDescription(
        key="last_cycle_energy",
        translation_key="last_cycle_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda runtime: runtime.last_cycle_energy,
        unit_fn=lambda runtime: runtime.last_cycle_energy_unit,
    ),
)

TRACKING_SENSOR_DESCRIPTIONS: tuple[
    LaundryMonitorSensorDescription, ...
] = (
    LaundryMonitorSensorDescription(
        key="last_unloaded_at",
        translation_key="last_unloaded_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda runtime: runtime.last_unloaded_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Laundry Monitor sensor entities."""
    runtime = entry.runtime_data
    descriptions = SENSOR_DESCRIPTIONS
    if entry.data.get(CONF_ENERGY_SENSOR):
        descriptions += ENERGY_SENSOR_DESCRIPTIONS
    if runtime.tracking_enabled:
        descriptions += TRACKING_SENSOR_DESCRIPTIONS

    async_add_entities(
        LaundryMonitorSensor(runtime, description)
        for description in descriptions
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
    def native_unit_of_measurement(self) -> str | None:
        """Return a dynamic source-compatible unit when configured."""
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self.runtime)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.runtime)
