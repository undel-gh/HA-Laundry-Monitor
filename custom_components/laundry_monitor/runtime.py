"""Runtime state and source-entity subscriptions for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_LEAK_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    EVENT_LEAK_DETECTED,
    EVENT_MACHINE_UNLOADED,
    EVENT_STATE_CHANGED,
    LaundryCycleState,
    REASON_INITIAL_SETUP,
    REASON_MARKED_UNLOADED,
    SIGNAL_RUNTIME_UPDATED,
)


@dataclass(slots=True)
class LaundryMonitorRuntime:
    """Runtime data for one Laundry Monitor config entry."""

    hass: HomeAssistant
    entry: ConfigEntry

    cycle_state: LaundryCycleState = LaundryCycleState.IDLE
    last_transition_reason: str = REASON_INITIAL_SETUP
    last_state_change: datetime = field(default_factory=dt_util.utcnow)

    power: float | None = None
    door_open: bool | None = None
    vibration_active: bool | None = None
    leak_detected: bool = False
    energy: float | None = None
    laundry_present: bool = False

    _remove_source_listener: Any | None = field(default=None, init=False)

    @property
    def name(self) -> str:
        """Return the configured washing-machine name."""
        return str(self.entry.data.get(CONF_NAME, self.entry.title))

    @property
    def tracking_enabled(self) -> bool:
        """Return whether laundry-presence tracking is enabled."""
        return bool(self.entry.data.get(CONF_TRACK_LAUNDRY, False))

    @property
    def signal(self) -> str:
        """Return the dispatcher signal for this config entry."""
        return f"{SIGNAL_RUNTIME_UPDATED}_{self.entry.entry_id}"

    @property
    def source_entity_ids(self) -> tuple[str, ...]:
        """Return configured source entity IDs."""
        keys = (
            CONF_POWER_SENSOR,
            CONF_DOOR_SENSOR,
            CONF_VIBRATION_SENSOR,
            CONF_LEAK_SENSOR,
            CONF_ENERGY_SENSOR,
        )
        return tuple(
            entity_id
            for key in keys
            if isinstance((entity_id := self.entry.data.get(key)), str)
            and entity_id
        )

    async def async_start(self) -> None:
        """Read initial source states and subscribe to future changes."""
        self._read_all_source_states()

        if self.source_entity_ids:
            self._remove_source_listener = async_track_state_change_event(
                self.hass,
                self.source_entity_ids,
                self._async_source_state_changed,
            )

    async def async_stop(self) -> None:
        """Remove runtime subscriptions."""
        if self._remove_source_listener is not None:
            self._remove_source_listener()
            self._remove_source_listener = None

    @callback
    def _read_all_source_states(self) -> None:
        """Read the current state of every configured source entity."""
        for entity_id in self.source_entity_ids:
            self._update_source(entity_id, self.hass.states.get(entity_id))

    @callback
    def _async_source_state_changed(
        self,
        event: Event[EventStateChangedData],
    ) -> None:
        """Handle a source entity state change."""
        entity_id = event.data["entity_id"]
        old_leak = self.leak_detected

        if not self._update_source(entity_id, event.data.get("new_state")):
            return

        if not old_leak and self.leak_detected:
            self.hass.bus.async_fire(
                EVENT_LEAK_DETECTED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "source_entity_id": entity_id,
                },
            )

        self._notify_entities()

    @callback
    def _update_source(self, entity_id: str, state: State | None) -> bool:
        """Update one cached source value.

        Return True when the cached value changed.
        """
        value: object
        data_key: str

        if entity_id == self.entry.data.get(CONF_POWER_SENSOR):
            data_key = "power"
            value = _state_as_float(state)
        elif entity_id == self.entry.data.get(CONF_DOOR_SENSOR):
            data_key = "door_open"
            value = _state_as_bool(state)
        elif entity_id == self.entry.data.get(CONF_VIBRATION_SENSOR):
            data_key = "vibration_active"
            value = _state_as_bool(state)
        elif entity_id == self.entry.data.get(CONF_LEAK_SENSOR):
            data_key = "leak_detected"
            value = _state_as_bool(state) is True
        elif entity_id == self.entry.data.get(CONF_ENERGY_SENSOR):
            data_key = "energy"
            value = _state_as_float(state)
        else:
            return False

        if getattr(self, data_key) == value:
            return False

        setattr(self, data_key, value)
        return True

    @callback
    def async_set_cycle_state(
        self,
        new_state: LaundryCycleState,
        reason: str,
    ) -> None:
        """Set the public cycle state.

        Detectors and the state machine will call this method in later stages.
        """
        if self.cycle_state == new_state and self.last_transition_reason == reason:
            return

        old_state = self.cycle_state
        self.cycle_state = new_state
        self.last_transition_reason = reason
        self.last_state_change = dt_util.utcnow()

        if new_state in (
            LaundryCycleState.RUNNING,
            LaundryCycleState.FINAL_SPIN,
            LaundryCycleState.FINISHED,
        ):
            self.laundry_present = True

        self.hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "config_entry_id": self.entry.entry_id,
                "name": self.name,
                "old_state": old_state,
                "new_state": new_state,
                "reason": reason,
            },
        )
        self._notify_entities()

    @callback
    def async_mark_unloaded(self) -> None:
        """Mark the washing machine as unloaded."""
        if not self.tracking_enabled:
            return

        self.laundry_present = False

        if self.cycle_state is LaundryCycleState.FINISHED:
            self.async_set_cycle_state(
                LaundryCycleState.IDLE,
                REASON_MARKED_UNLOADED,
            )
        else:
            self.last_transition_reason = REASON_MARKED_UNLOADED
            self.last_state_change = dt_util.utcnow()
            self._notify_entities()

        self.hass.bus.async_fire(
            EVENT_MACHINE_UNLOADED,
            {
                "config_entry_id": self.entry.entry_id,
                "name": self.name,
            },
        )

    @callback
    def _notify_entities(self) -> None:
        """Notify all entities belonging to this runtime."""
        async_dispatcher_send(self.hass, self.signal)


def _state_as_float(state: State | None) -> float | None:
    """Convert a Home Assistant state to float."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _state_as_bool(state: State | None) -> bool | None:
    """Convert a binary Home Assistant state to bool."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    return state.state == STATE_ON
