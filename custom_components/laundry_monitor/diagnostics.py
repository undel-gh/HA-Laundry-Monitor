"""Diagnostics support for Laundry Monitor."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_LEAK_SENSOR,
    CONF_PLUG_SWITCH,
    CONF_POWER_SENSOR,
    CONF_VIBRATION_SENSOR,
)
from .runtime import LaundryMonitorRuntime

type LaundryMonitorConfigEntry = ConfigEntry[LaundryMonitorRuntime]

_SOURCE_DEFINITIONS: tuple[tuple[str, bool, bool], ...] = (
    (CONF_POWER_SENSOR, True, True),
    (CONF_DOOR_SENSOR, False, False),
    (CONF_VIBRATION_SENSOR, False, False),
    (CONF_LEAK_SENSOR, False, False),
    (CONF_ENERGY_SENSOR, False, True),
    (CONF_PLUG_SWITCH, False, False),
)

_STATE_ATTRIBUTE_KEYS = (
    "device_class",
    "state_class",
    "unit_of_measurement",
)


def _serialize_datetime(value: datetime | None) -> str | None:
    """Serialize an optional datetime."""
    return value.isoformat() if value is not None else None


def _source_diagnostics(
    hass: HomeAssistant,
    entity_id: str | None,
    *,
    required: bool,
    numeric: bool,
) -> dict[str, Any]:
    """Return diagnostics for one configured source entity."""
    if not entity_id:
        return {
            "configured": False,
            "required": required,
            "entity_id": None,
            "available": False,
            "state": None,
            "last_changed": None,
            "last_updated": None,
            "attributes": {},
        }

    state: State | None = hass.states.get(entity_id)

    if state is None:
        return {
            "configured": True,
            "required": required,
            "entity_id": entity_id,
            "available": False,
            "state": None,
            "last_changed": None,
            "last_updated": None,
            "attributes": {},
        }

    valid_state = state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    if numeric and valid_state:
        valid_state = _is_numeric_state(state.state)

    return {
        "configured": True,
        "required": required,
        "entity_id": entity_id,
        "available": valid_state,
        "state": state.state,
        "last_changed": state.last_changed.isoformat(),
        "last_updated": state.last_updated.isoformat(),
        "attributes": {
            key: state.attributes[key]
            for key in _STATE_ATTRIBUTE_KEYS
            if key in state.attributes
        },
    }


def _is_numeric_state(value: str) -> bool:
    """Return whether a sensor state is a finite number."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


async def _async_build_diagnostics(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
) -> dict[str, Any]:
    """Build diagnostics shared by config-entry and device exports."""
    runtime = entry.runtime_data

    sources = {
        source_key: _source_diagnostics(
            hass,
            entry.data.get(source_key),
            required=required,
            numeric=numeric,
        )
        for source_key, required, numeric in _SOURCE_DEFINITIONS
    }

    snapshot = await runtime.state_store.async_get(entry.entry_id)

    return {
        "config_entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "sources": sources,
        "required_sources_unavailable": [
            source_key
            for source_key, required, _numeric in _SOURCE_DEFINITIONS
            if required and not sources[source_key]["available"]
        ],
        "runtime": {
            "cycle_state": runtime.cycle_state.value,
            "state_machine_state": runtime.state_machine.state.value,
            "last_transition_reason": runtime.last_transition_reason,
            "last_state_change": _serialize_datetime(
                runtime.last_state_change
            ),
            "cycle_started_at": _serialize_datetime(
                runtime.cycle_started_at
            ),
            "laundry_present": runtime.laundry_present,
            "last_unloaded_at": _serialize_datetime(
                runtime.last_unloaded_at
            ),
            "tracking_enabled": runtime.tracking_enabled,
            "power": runtime.power,
            "door_open": runtime.door_open,
            "vibration_active": runtime.vibration_active,
            "leak_detected": runtime.leak_detected,
            "energy": runtime.energy,
            "energy_unit": runtime.energy_unit,
            "rejected_transition_count": (
                runtime.rejected_transition_count
            ),
            "last_rejected_transition": (
                runtime.last_rejected_transition
            ),
            "statistics": {
                "current_cycle_duration": (
                    runtime.current_cycle_duration
                ),
                "last_cycle_duration": runtime.last_cycle_duration,
                "cycle_energy_start": runtime.cycle_energy_start,
                "cycle_energy_unit": runtime.cycle_energy_unit,
                "last_cycle_energy": runtime.last_cycle_energy,
                "last_cycle_energy_unit": (
                    runtime.last_cycle_energy_unit
                ),
                "final_spin_detected": runtime.final_spin_detected,
            },
        },
        "detectors": {
            "activity": {
                "start_threshold": (
                    runtime.activity_detector.start_threshold
                ),
                "activity_threshold": (
                    runtime.activity_detector.activity_threshold
                ),
                "start_confirmation_seconds": (
                    runtime.start_confirmation_seconds
                ),
                "activity_detected": runtime.activity_detected,
                "start_candidate": (
                    runtime.activity_detector.start_candidate
                ),
                "last_activity": _serialize_datetime(
                    runtime.last_activity
                ),
            },
            "spin": {
                "required_events": (
                    runtime.spin_detector.required_events
                ),
                "window_seconds": (
                    runtime.spin_detector.window_seconds
                ),
                "min_cycle_seconds": (
                    runtime.spin_detector.min_cycle_seconds
                ),
                "activity_max_age_seconds": (
                    runtime.spin_detector.activity_max_age_seconds
                ),
                "confidence": runtime.final_spin_confidence,
                "evidence_count": (
                    runtime.final_spin_evidence_count
                ),
            },
            "finish": {
                "confirmation_seconds": (
                    runtime.finish_detector.confirmation_seconds
                ),
                "final_spin_confirmation_seconds": (
                    runtime.finish_detector.confirmation_seconds
                ),
                "running_fallback_confirmation_seconds": (
                    runtime.running_finish_detector.confirmation_seconds
                ),
                "quiet_since": _serialize_datetime(
                    runtime.finish_quiet_since
                ),
                "deadline": _serialize_datetime(
                    runtime.finish_deadline
                ),
                "remaining_seconds": (
                    runtime.finish_remaining_seconds
                ),
            },
            "lifecycle": {
                "arming_timeout_seconds": runtime.arming_timeout_seconds,
                "finished_retention_seconds": (
                    runtime.finished_retention_seconds
                ),
                "power_unavailable_grace_seconds": (
                    runtime.power_unavailable_grace_seconds
                ),
                "snapshot_max_age_seconds": (
                    runtime.snapshot_max_age_seconds
                ),
            },
        },
        "storage_snapshot": (
            snapshot.as_storage_dict()
            if snapshot is not None
            else None
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Laundry Monitor config entry."""
    return await _async_build_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
    device: dr.DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Laundry Monitor device."""
    diagnostics = await _async_build_diagnostics(hass, entry)
    diagnostics["device"] = {
        "name": device.name,
        "name_by_user": device.name_by_user,
        "manufacturer": device.manufacturer,
        "model": device.model,
    }
    return diagnostics
