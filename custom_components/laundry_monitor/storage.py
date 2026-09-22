"""Persistent runtime snapshots for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LaundryCycleState

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.runtime"


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Persisted runtime state for one config entry."""

    cycle_state: LaundryCycleState
    last_transition_reason: str
    last_state_change: datetime
    cycle_started_at: datetime | None
    laundry_present: bool
    last_unloaded_at: datetime | None = None
    cycle_energy_start: float | None = None
    cycle_energy_unit: str | None = None
    last_cycle_duration: float | None = None
    last_cycle_energy: float | None = None
    last_cycle_energy_unit: str | None = None
    final_spin_detected: bool = False
    heating_detected: bool = False
    heating_detected_at: datetime | None = None
    heating_not_seen: bool = False
    heating_detector_version: int | None = None
    heating_power_threshold_w: float | None = None
    heating_confirmation_seconds: int | None = None
    heating_observation_seconds: int | None = None
    heating_max_source_age_seconds: int | None = None
    spin_evidence_timestamps: tuple[datetime, ...] = ()

    def as_storage_dict(self) -> dict[str, Any]:
        """Serialize the snapshot."""
        return {
            "cycle_state": self.cycle_state.value,
            "last_transition_reason": self.last_transition_reason,
            "last_state_change": self.last_state_change.isoformat(),
            "cycle_started_at": (
                self.cycle_started_at.isoformat()
                if self.cycle_started_at is not None
                else None
            ),
            "laundry_present": self.laundry_present,
            "last_unloaded_at": (
                self.last_unloaded_at.isoformat()
                if self.last_unloaded_at is not None
                else None
            ),
            "cycle_energy_start": self.cycle_energy_start,
            "cycle_energy_unit": self.cycle_energy_unit,
            "last_cycle_duration": self.last_cycle_duration,
            "last_cycle_energy": self.last_cycle_energy,
            "last_cycle_energy_unit": self.last_cycle_energy_unit,
            "final_spin_detected": self.final_spin_detected,
            "heating_detected": self.heating_detected,
            "heating_detected_at": (
                self.heating_detected_at.isoformat()
                if self.heating_detected_at is not None
                else None
            ),
            "heating_not_seen": self.heating_not_seen,
            "heating_detector_version": self.heating_detector_version,
            "heating_power_threshold_w": self.heating_power_threshold_w,
            "heating_confirmation_seconds": self.heating_confirmation_seconds,
            "heating_observation_seconds": self.heating_observation_seconds,
            "heating_max_source_age_seconds": (
                self.heating_max_source_age_seconds
            ),
            "spin_evidence_timestamps": [
                timestamp.isoformat()
                for timestamp in self.spin_evidence_timestamps
            ],
        }

    @classmethod
    def from_storage_dict(
        cls,
        data: dict[str, Any],
    ) -> RuntimeSnapshot | None:
        """Deserialize and validate stored data."""
        try:
            cycle_state = LaundryCycleState(data["cycle_state"])
            last_state_change = dt_util.parse_datetime(
                data["last_state_change"]
            )
            cycle_started_at = (
                dt_util.parse_datetime(data["cycle_started_at"])
                if data.get("cycle_started_at")
                else None
            )
            reason = str(data["last_transition_reason"])
            laundry_present = bool(data["laundry_present"])
            last_unloaded_at = (
                dt_util.parse_datetime(data["last_unloaded_at"])
                if data.get("last_unloaded_at")
                else None
            )
            cycle_energy_start = _optional_finite_float(
                data.get("cycle_energy_start")
            )
            cycle_energy_unit = _optional_string(
                data.get("cycle_energy_unit")
            )
            last_cycle_duration = _optional_finite_float(
                data.get("last_cycle_duration")
            )
            last_cycle_energy = _optional_finite_float(
                data.get("last_cycle_energy")
            )
            last_cycle_energy_unit = _optional_string(
                data.get("last_cycle_energy_unit")
            )
            final_spin_detected = bool(
                data.get("final_spin_detected", False)
            )
            heating_detected = bool(data.get("heating_detected", False))
            heating_detected_at = (
                dt_util.parse_datetime(data["heating_detected_at"])
                if data.get("heating_detected_at")
                else None
            )
            heating_not_seen = bool(data.get("heating_not_seen", False))
            heating_detector_version = _optional_positive_int(
                data.get("heating_detector_version")
            )
            heating_power_threshold_w = _optional_finite_float(
                data.get("heating_power_threshold_w")
            )
            heating_confirmation_seconds = _optional_positive_int(
                data.get("heating_confirmation_seconds")
            )
            heating_observation_seconds = _optional_positive_int(
                data.get("heating_observation_seconds")
            )
            heating_max_source_age_seconds = _optional_positive_int(
                data.get("heating_max_source_age_seconds")
            )
            spin_evidence_timestamps = _datetime_tuple(
                data.get("spin_evidence_timestamps")
            )
        except (KeyError, TypeError, ValueError):
            return None

        if last_state_change is None:
            return None
        if data.get("last_unloaded_at") and last_unloaded_at is None:
            return None
        if data.get("heating_detected_at") and heating_detected_at is None:
            return None
        if heating_detected and heating_not_seen:
            return None
        if heating_not_seen and any(
            value is None
            for value in (
                heating_detector_version,
                heating_power_threshold_w,
                heating_confirmation_seconds,
                heating_observation_seconds,
                heating_max_source_age_seconds,
            )
        ):
            # Keep the rest of a valid legacy/corrupt snapshot recoverable,
            # but never grant persisted NOT_SEEN privileges without the
            # complete detector fingerprint.
            heating_not_seen = False 
        return cls(
            cycle_state=cycle_state,
            last_transition_reason=reason,
            last_state_change=last_state_change,
            cycle_started_at=cycle_started_at,
            laundry_present=laundry_present,
            last_unloaded_at=last_unloaded_at,
            cycle_energy_start=cycle_energy_start,
            cycle_energy_unit=cycle_energy_unit,
            last_cycle_duration=last_cycle_duration,
            last_cycle_energy=last_cycle_energy,
            last_cycle_energy_unit=last_cycle_energy_unit,
            final_spin_detected=final_spin_detected,
            heating_detected=heating_detected,
            heating_detected_at=heating_detected_at,
            heating_not_seen=heating_not_seen,
            heating_detector_version=heating_detector_version,
            heating_power_threshold_w=heating_power_threshold_w,
            heating_confirmation_seconds=heating_confirmation_seconds,
            heating_observation_seconds=heating_observation_seconds,
            heating_max_source_age_seconds=heating_max_source_age_seconds,
            spin_evidence_timestamps=spin_evidence_timestamps,
        )


def _optional_finite_float(value: Any) -> float | None:
    """Return an optional finite float or raise for invalid storage."""
    if value is None:
        return None
    number = float(value)
    if not isfinite(number):
        raise ValueError
    return number


def _optional_string(value: Any) -> str | None:
    """Return an optional non-empty string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def _optional_positive_int(value: Any) -> int | None:
    """Return an optional positive integer or raise for invalid storage."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError
    number = int(value)
    if number <= 0 or str(number) != str(value).strip():
        raise ValueError
    return number


def _datetime_tuple(value: Any) -> tuple[datetime, ...]:
    """Return validated aware timestamps from persisted storage."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError
    timestamps: list[datetime] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError
        timestamp = dt_util.parse_datetime(item)
        if timestamp is None or timestamp.tzinfo is None:
            raise ValueError
        timestamps.append(timestamp)
    return tuple(timestamps)


class LaundryStateStore:
    """Store snapshots for all Laundry Monitor config entries."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, dict[str, Any]]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._data: dict[str, dict[str, Any]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load storage once."""
        if self._loaded:
            return

        stored = await self._store.async_load()
        self._data = stored if isinstance(stored, dict) else {}
        self._loaded = True

    async def async_get(self, entry_id: str) -> RuntimeSnapshot | None:
        """Return a validated snapshot."""
        await self.async_load()
        raw = self._data.get(entry_id)
        return (
            RuntimeSnapshot.from_storage_dict(raw)
            if isinstance(raw, dict)
            else None
        )

    async def async_save(
        self,
        entry_id: str,
        snapshot: RuntimeSnapshot,
    ) -> None:
        """Persist one snapshot."""
        await self.async_load()
        self._data[entry_id] = snapshot.as_storage_dict()
        await self._store.async_save(self._data)

    async def async_remove(self, entry_id: str) -> None:
        """Remove one snapshot."""
        await self.async_load()
        if self._data.pop(entry_id, None) is not None:
            await self._store.async_save(self._data)


def select_recovery_state(
    snapshot: RuntimeSnapshot,
    *,
    door_open: bool | None,
    activity_detected: bool,
    vibration_active: bool | None,
    now: datetime | None = None,
    tracking_enabled: bool = True,
    arming_timeout_seconds: int | None = None,
    finished_retention_seconds: int | None = None,
    max_active_snapshot_age_seconds: int | None = None,
    power_available: bool = False,
    require_final_spin_context: bool = False,
) -> LaundryCycleState:
    """Select a conservative state after restart.

    Optional policy arguments default to the legacy recovery behavior so the
    function remains useful in unit tests and migrations. Runtime setup passes
    the configured lifecycle policy explicitly.
    """
    timestamp = now or dt_util.utcnow()
    age = max(timestamp - snapshot.last_state_change, timedelta())
    state = snapshot.cycle_state

    if state is LaundryCycleState.ARMED:
        if door_open is not False:
            return LaundryCycleState.IDLE
        if (
            arming_timeout_seconds is not None
            and age >= timedelta(seconds=arming_timeout_seconds)
        ):
            return LaundryCycleState.IDLE
        return LaundryCycleState.ARMED

    if state in {
        LaundryCycleState.RUNNING,
        LaundryCycleState.FINAL_SPIN,
    }:
        if (
            max_active_snapshot_age_seconds is not None
            and age
            >= timedelta(seconds=max_active_snapshot_age_seconds)
        ):
            return LaundryCycleState.IDLE

        if (
            state is LaundryCycleState.FINAL_SPIN
            and require_final_spin_context
            and vibration_active is not True
        ):
            return LaundryCycleState.RUNNING

        return state

    if state is LaundryCycleState.FINISHED:
        if tracking_enabled or finished_retention_seconds is None:
            return LaundryCycleState.FINISHED
        if age < timedelta(seconds=finished_retention_seconds):
            return LaundryCycleState.FINISHED
        return LaundryCycleState.IDLE

    if state is LaundryCycleState.ERROR:
        return (
            LaundryCycleState.IDLE
            if power_available
            else LaundryCycleState.ERROR
        )

    return LaundryCycleState.IDLE
