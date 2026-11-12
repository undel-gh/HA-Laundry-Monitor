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
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaundryMonitorConfigEntry
from .const import (
    CONF_CURRENT_SENSOR,
    CONF_ENERGY_SENSOR,
    LaundryCycleState,
)
from .entity import LaundryMonitorEntity
from .heating import HeatingState
from .runtime import LaundryMonitorRuntime


# UnitOfRatio was introduced in Core 2026.7; HACS supports Core 2026.6+.
# Preserve the enum on newer Core and use the equivalent legacy constant
# on the minimum supported release.
try:
    from homeassistant.const import UnitOfRatio
except ImportError:
    _PERCENTAGE_UNIT = PERCENTAGE
else:
    _PERCENTAGE_UNIT = UnitOfRatio.PERCENTAGE


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
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.power,
    ),
    LaundryMonitorSensorDescription(
        key="cycle_started_at",
        translation_key="cycle_started_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda runtime: (
            runtime.cycle_started_at
            if runtime.cycle_state
            in (LaundryCycleState.RUNNING, LaundryCycleState.FINAL_SPIN)
            else None
        ),
    ),
    LaundryMonitorSensorDescription(
        key="current_cycle_duration",
        translation_key="current_cycle_duration",
        # Compatibility-only value: never refreshed just because time passes.
        # Use cycle_started_at and UI-local time for a live timer instead.
        entity_registry_enabled_default=False,
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
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_activity,
    ),
    LaundryMonitorSensorDescription(
        key="last_power_activity",
        translation_key="last_power_activity",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_power_activity,
    ),
    LaundryMonitorSensorDescription(
        key="final_spin_confidence",
        translation_key="final_spin_confidence",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=_PERCENTAGE_UNIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: round(
            runtime.final_spin_confidence * 100,
        ),
    ),
    LaundryMonitorSensorDescription(
        key="final_spin_evidence_count",
        translation_key="final_spin_evidence_count",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.final_spin_evidence_count,
    ),
    LaundryMonitorSensorDescription(
        key="final_spin_confirmation_path",
        translation_key="final_spin_confirmation_path",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda runtime: runtime.final_spin_confirmation_path,
    ),
    LaundryMonitorSensorDescription(
        key="heating_state",
        translation_key="heating_state",
        device_class=SensorDeviceClass.ENUM,
        options=[state.value for state in HeatingState],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda runtime: runtime.heating_state.value,
    ),
    LaundryMonitorSensorDescription(
        key="spin_power_rolling_median",
        translation_key="spin_power_rolling_median",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda runtime: runtime.spin_power_rolling_median,
    ),
    LaundryMonitorSensorDescription(
        key="spin_electrical_candidate_since",
        translation_key="spin_electrical_candidate_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda runtime: runtime.spin_electrical_candidate_since,
    ),
    LaundryMonitorSensorDescription(
        key="finish_quiet_since", translation_key="finish_quiet_since",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.finish_quiet_since,
    ),
    LaundryMonitorSensorDescription(
        key="finish_deadline", translation_key="finish_deadline",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.finish_deadline,
    ),
    LaundryMonitorSensorDescription(
        key="finish_remaining", translation_key="finish_remaining",
        entity_registry_enabled_default=False,
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

CURRENT_SENSOR_DESCRIPTIONS: tuple[
    LaundryMonitorSensorDescription, ...
] = (
    LaundryMonitorSensorDescription(
        key="current",
        translation_key="current",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.current,
    ),
    LaundryMonitorSensorDescription(
        key="last_current_activity",
        translation_key="last_current_activity",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda runtime: runtime.last_current_activity,
    ),
    LaundryMonitorSensorDescription(
        key="spin_current_rolling_median",
        translation_key="spin_current_rolling_median",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda runtime: runtime.spin_current_rolling_median,
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
    if entry.data.get(CONF_CURRENT_SENSOR):
        descriptions += CURRENT_SENSOR_DESCRIPTIONS
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

    def _runtime_state_signature(self) -> object:
        """Identify changes without publishing every transient derived value."""
        value = self.native_value
        if self.entity_description.key == "current_cycle_duration":
            # Legacy sensor: provide a point-in-time duration on lifecycle
            # changes only, without creating any periodic Recorder states.
            # The timestamp sensor is the authoritative live UI input.
            return (
                self.available,
                self.runtime.cycle_state,
                self.runtime.cycle_started_at,
                self.native_unit_of_measurement,
            )
        # Last-cycle energy can change its unit without changing its value.
        return (self.available, value, self.native_unit_of_measurement)
