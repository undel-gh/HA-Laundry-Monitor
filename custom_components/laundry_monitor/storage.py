"""Persistent runtime snapshots for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
        except (KeyError, TypeError, ValueError):
            return None

        if last_state_change is None:
            return None

        return cls(
            cycle_state=cycle_state,
            last_transition_reason=reason,
            last_state_change=last_state_change,
            cycle_started_at=cycle_started_at,
            laundry_present=laundry_present,
        )


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
