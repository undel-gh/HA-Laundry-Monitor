"""Runtime state and source-entity subscriptions for Laundry Monitor."""

from __future__ import annotations

from .spin import SpinDetector
from .finish import FinishDetector, FinishEvaluation
from .state_machine import LaundryStateMachine, TransitionStatus
from .storage import LaundryStateStore, RuntimeSnapshot, select_recovery_state

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .activity import ActivityDetector
from .const import (
    CONF_ACTIVITY_THRESHOLD,
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_LEAK_SENSOR,
    CONF_POWER_SENSOR,
    CONF_START_CONFIRMATION,
    CONF_START_THRESHOLD,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DEFAULT_ACTIVITY_THRESHOLD,
    DEFAULT_START_CONFIRMATION,
    DEFAULT_START_THRESHOLD,
    EVENT_CYCLE_STARTED,
    EVENT_LEAK_DETECTED,
    EVENT_MACHINE_UNLOADED,
    EVENT_STATE_CHANGED,
    LaundryCycleState,
    REASON_DOOR_CLOSED,
    REASON_DOOR_OPENED_BEFORE_START,
    REASON_INITIAL_SETUP,
    REASON_MARKED_UNLOADED,
    REASON_POWER_ABOVE_START_THRESHOLD,
    SIGNAL_RUNTIME_UPDATED,
    CONF_SPIN_ACTIVITY_MAX_AGE,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    DEFAULT_SPIN_ACTIVITY_MAX_AGE,
    DEFAULT_SPIN_MIN_CYCLE_TIME,
    DEFAULT_SPIN_REQUIRED_EVENTS,
    DEFAULT_SPIN_WINDOW,
    EVENT_FINAL_SPIN_DETECTED,
    REASON_FINAL_SPIN_CONFIRMED,
    CONF_FINISH_CONFIRMATION,
    DEFAULT_FINISH_CONFIRMATION,
    EVENT_CYCLE_FINISHED,
    REASON_FINISH_INACTIVITY_CONFIRMED,
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
    cycle_started_at: datetime | None = None
    final_spin_confidence: float = 0.0
    final_spin_evidence_count: int = 0
    finish_quiet_since: datetime | None = None
    finish_deadline: datetime | None = None
    finish_remaining_seconds: float | None = None
    state_machine: LaundryStateMachine = field(init=False)
    state_store: LaundryStateStore = field(init=False)
    rejected_transition_count: int = 0
    last_rejected_transition: str | None = None

    activity_detector: ActivityDetector = field(init=False)
    spin_detector: SpinDetector = field(init=False)
    finish_detector: FinishDetector = field(init=False)
    _cancel_finish_confirmation: Callable[[], None] | None = field(default=None, init=False)

    _remove_source_listener: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _cancel_start_confirmation: Callable[[], None] | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        """Initialize detector modules from config-entry options."""
        self.state_machine = LaundryStateMachine(state=self.cycle_state)
        self.state_store = LaundryStateStore(self.hass)
        
        self.activity_detector = ActivityDetector(
            start_threshold=float(
                self.entry.options.get(
                    CONF_START_THRESHOLD,
                    DEFAULT_START_THRESHOLD,
                )
            ),
            activity_threshold=float(
                self.entry.options.get(
                    CONF_ACTIVITY_THRESHOLD,
                    DEFAULT_ACTIVITY_THRESHOLD,
                )
            ),            
        )
        self.spin_detector = SpinDetector(
            required_events=int(
                self.entry.options.get(
                    CONF_SPIN_REQUIRED_EVENTS,
                    DEFAULT_SPIN_REQUIRED_EVENTS,
                )
            ),
            window_seconds=int(
                self.entry.options.get(
                    CONF_SPIN_WINDOW,
                    DEFAULT_SPIN_WINDOW,
                )
            ),
            min_cycle_seconds=int(
                self.entry.options.get(
                    CONF_SPIN_MIN_CYCLE_TIME,
                    DEFAULT_SPIN_MIN_CYCLE_TIME,
                )
            ),
            activity_max_age_seconds=int(
                self.entry.options.get(
                    CONF_SPIN_ACTIVITY_MAX_AGE,
                    DEFAULT_SPIN_ACTIVITY_MAX_AGE,
                )
            ),
        )
        self.finish_detector = FinishDetector(
            confirmation_seconds=int(self.entry.options.get(
                CONF_FINISH_CONFIRMATION, DEFAULT_FINISH_CONFIRMATION
            ))
        )


    @property
    def name(self) -> str:
        """Return the configured washing-machine name."""
        return str(self.entry.data.get(CONF_NAME, self.entry.title))

    @property
    def tracking_enabled(self) -> bool:
        """Return whether laundry-presence tracking is enabled."""
        return bool(self.entry.data.get(CONF_TRACK_LAUNDRY, False))

    @property
    def start_confirmation_seconds(self) -> int:
        """Return the configured cycle-start confirmation time."""
        return int(
            self.entry.options.get(
                CONF_START_CONFIRMATION,
                DEFAULT_START_CONFIRMATION,
            )
        )

    @property
    def activity_detected(self) -> bool:
        """Return whether meaningful power activity is present."""
        return self.activity_detector.activity_detected

    @property
    def last_activity(self) -> datetime | None:
        """Return the last meaningful power activity timestamp."""
        return self.activity_detector.last_activity

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
        
        if self.cycle_state is LaundryCycleState.FINAL_SPIN:
            self._evaluate_finish()

    async def async_stop(self) -> None:
        """Remove runtime subscriptions and timers."""
        if self._remove_source_listener is not None:
            self._remove_source_listener()
            self._remove_source_listener = None

        self._cancel_pending_start_confirmation()
        self._cancel_pending_finish_confirmation()

    def _snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            cycle_state=self.cycle_state,
            last_transition_reason=self.last_transition_reason,
            last_state_change=self.last_state_change,
            cycle_started_at=self.cycle_started_at,
            laundry_present=self.laundry_present,
        )

    @callback
    def _schedule_snapshot_save(self) -> None:
        self.hass.async_create_task(
            self.state_store.async_save(self.entry.entry_id, self._snapshot())
        )

    async def _async_restore_snapshot(self) -> None:
        snapshot = await self.state_store.async_get(self.entry.entry_id)
        if snapshot is None:
            return

        recovered_state = select_recovery_state(
            snapshot,
            door_open=self.door_open,
            activity_detected=self.activity_detected,
            vibration_active=self.vibration_active,
        )

        self.state_machine.restore(recovered_state)
        self.cycle_state = recovered_state
        self.last_transition_reason = REASON_STATE_RESTORED
        self.last_state_change = snapshot.last_state_change
        self.laundry_present = snapshot.laundry_present
        self.cycle_started_at = (
            snapshot.cycle_started_at
            if recovered_state in (
                LaundryCycleState.RUNNING,
                LaundryCycleState.FINAL_SPIN,
            )
            else None
        )

        self.spin_detector.reset(vibration_active=self.vibration_active)
        self.final_spin_confidence = 0.0
        self.final_spin_evidence_count = 0
        self.finish_detector.reset()
        self.finish_quiet_since = None
        self.finish_deadline = None
        self.finish_remaining_seconds = None
    
    @callback
    def _read_all_source_states(self) -> None:
        """Read current states without causing cycle-state transitions."""
        for entity_id in self.source_entity_ids:
            self._update_source(entity_id, self.hass.states.get(entity_id))

        self.activity_detector.evaluate(self.power)
        self.spin_detector.reset(
            vibration_active=self.vibration_active,
        )

    @callback
    def _async_source_state_changed(
        self,
        event: Event[EventStateChangedData],
    ) -> None:
        """Handle a source entity state change."""
        entity_id = event.data["entity_id"]
        old_door_open = self.door_open
        old_leak = self.leak_detected

        if not self._update_source(entity_id, event.data.get("new_state")):
            return

        if entity_id == self.entry.data.get(CONF_POWER_SENSOR):
            self._handle_power_update()
        elif entity_id == self.entry.data.get(CONF_DOOR_SENSOR):
            self._handle_door_update(old_door_open)

        if entity_id in (
            self.entry.data.get(CONF_POWER_SENSOR),
            self.entry.data.get(CONF_VIBRATION_SENSOR),
        ):
            self._evaluate_spin()
        if entity_id in (
            self.entry.data.get(CONF_POWER_SENSOR),
            self.entry.data.get(CONF_VIBRATION_SENSOR),
        ):
            self._evaluate_finish()

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
    def _handle_power_update(self) -> None:
        """Evaluate power activity and manage start confirmation."""
        evaluation = self.activity_detector.evaluate(self.power)

        if evaluation.start_candidate:
            self._schedule_start_confirmation()
        else:
            self._cancel_pending_start_confirmation()

    @callback
    def _handle_door_update(self, old_door_open: bool | None) -> None:
        """Handle public state transitions caused by the door."""
        # Only a real open -> closed event arms detection. Initial closed state
        # during integration startup must not create a synthetic transition.
        if (
            old_door_open is True
            and self.door_open is False
            and self.cycle_state is LaundryCycleState.IDLE
        ):
            self.async_set_cycle_state(
                LaundryCycleState.ARMED,
                REASON_DOOR_CLOSED,
            )
            return

        if (
            self.door_open is True
            and self.cycle_state is LaundryCycleState.ARMED
        ):
            self._cancel_pending_start_confirmation()
            self.async_set_cycle_state(
                LaundryCycleState.IDLE,
                REASON_DOOR_OPENED_BEFORE_START,
            )

    @callback
    def _schedule_start_confirmation(self) -> None:
        """Schedule confirmation of sustained start-level power."""
        if self.cycle_state not in (
            LaundryCycleState.IDLE,
            LaundryCycleState.ARMED,
        ):
            return

        if self._cancel_start_confirmation is not None:
            return

        self._cancel_start_confirmation = async_call_later(
            self.hass,
            self.start_confirmation_seconds,
            self._async_confirm_cycle_start,
        )

    @callback
    def _async_confirm_cycle_start(self, _now: datetime) -> None:
        """Confirm a cycle start after sustained high power."""
        self._cancel_start_confirmation = None

        if self.cycle_state not in (
            LaundryCycleState.IDLE,
            LaundryCycleState.ARMED,
        ):
            return

        if not self.activity_detector.start_candidate:
            return

        self.async_set_cycle_state(
            LaundryCycleState.RUNNING,
            REASON_POWER_ABOVE_START_THRESHOLD,
        )
        self.hass.bus.async_fire(
            EVENT_CYCLE_STARTED,
            {
                "config_entry_id": self.entry.entry_id,
                "name": self.name,
                "power": self.power,
                "start_threshold": self.activity_detector.start_threshold,
                "confirmation_seconds": self.start_confirmation_seconds,
            },
        )

    @callback
    def _cancel_pending_start_confirmation(self) -> None:
        """Cancel a pending cycle-start confirmation timer."""
        if self._cancel_start_confirmation is not None:
            self._cancel_start_confirmation()
            self._cancel_start_confirmation = None

    @callback
    def _update_source(self, entity_id: str, state: State | None) -> bool:
        """Update one cached source value."""
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
    ) -> bool:
        transition_time = dt_util.utcnow()
        result = self.state_machine.transition(
            new_state,
            reason=reason,
            now=transition_time,
        )

        if result.status is TransitionStatus.NO_CHANGE:
            return False

        if result.status is TransitionStatus.REJECTED:
            self.rejected_transition_count += 1
            self.last_rejected_transition = (
                f"{result.old_state.value}->{result.new_state.value}:{reason}"
            )
            self.hass.bus.async_fire(
                EVENT_TRANSITION_REJECTED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "old_state": result.old_state.value,
                    "requested_state": result.new_state.value,
                    "reason": reason,
                },
            )
            self._notify_entities()
            return False

        old_state = result.old_state
        self.cycle_state = result.new_state
        self.last_transition_reason = reason
        self.last_state_change = transition_time

            # Keep the detector lifecycle logic from your working implementation here.
            # Important detail for FINAL_SPIN -> RUNNING:
            # do not replace cycle_started_at when returning from a false spin candidate.
        
        if new_state is LaundryCycleState.RUNNING:
            if old_state is not LaundryCycleState.FINAL_SPIN:
                self.cycle_started_at = transition_time

            self.final_spin_confidence = 0.0
            self.final_spin_evidence_count = 0
            self.spin_detector.reset(vibration_active=self.vibration_active)
            self._reset_finish_detection()

        elif new_state is LaundryCycleState.FINAL_SPIN:
            self.finish_detector.reset()
            self.finish_quiet_since = None
            self.finish_deadline = None
            self.finish_remaining_seconds = None

        elif new_state in (LaundryCycleState.IDLE, LaundryCycleState.ARMED):
            self.cycle_started_at = None
            self.final_spin_confidence = 0.0
            self.final_spin_evidence_count = 0
            self.spin_detector.reset(vibration_active=self.vibration_active)
            self._reset_finish_detection()
   
        elif new_state is LaundryCycleState.FINISHED:
            self._reset_finish_detection()

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
                "old_state": old_state.value,
                "new_state": new_state.value,
                "reason": reason,
            },
        )

        self._schedule_snapshot_save()
        self._notify_entities()

        if new_state is LaundryCycleState.FINAL_SPIN:
            # Выполняем после публикации нового состояния.
            self._evaluate_finish()
        return True
        
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
            self._schedule_snapshot_save()
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

    @callback
    def _evaluate_spin(self) -> None:
        """Evaluate final-spin evidence."""
        if self.cycle_state is not LaundryCycleState.RUNNING:
            return

        evaluation = self.spin_detector.evaluate(
            vibration_active=self.vibration_active,
            activity_detected=self.activity_detected,
            last_activity=self.last_activity,
            cycle_started_at=self.cycle_started_at,
            now=dt_util.utcnow(),
        )

        changed = (
            self.final_spin_confidence != evaluation.confidence
            or self.final_spin_evidence_count != evaluation.evidence_count
        )
        self.final_spin_confidence = evaluation.confidence
        self.final_spin_evidence_count = evaluation.evidence_count

        if evaluation.detected:
            self.async_set_cycle_state(
                LaundryCycleState.FINAL_SPIN,
                REASON_FINAL_SPIN_CONFIRMED,
            )
            self.hass.bus.async_fire(
                EVENT_FINAL_SPIN_DETECTED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "confidence": evaluation.confidence,
                    "evidence_count": evaluation.evidence_count,
                    "window_seconds": self.spin_detector.window_seconds,
                },
            )
            return

        if changed:
            self._notify_entities()

    @callback
    def _evaluate_finish(self) -> None:
        if self.cycle_state is not LaundryCycleState.FINAL_SPIN:
            self._reset_finish_detection()
            return
        now = dt_util.utcnow()
        evaluation = self.finish_detector.evaluate(
            activity_detected=self.activity_detected,
            last_activity=self.last_activity,
            vibration_active=self.vibration_active,
            now=now,
        )
        self._apply_finish_diagnostics(evaluation)
        if evaluation.detected:
            self._confirm_cycle_finished()
            return
        if not evaluation.quiet or evaluation.deadline is None:
            self._cancel_pending_finish_confirmation()
            self._notify_entities()
            return
        self._schedule_finish_confirmation(max((evaluation.deadline-now).total_seconds(),0.0))
        self._notify_entities()

    @callback
    def _schedule_finish_confirmation(self, delay: float) -> None:
        self._cancel_pending_finish_confirmation()
        self._cancel_finish_confirmation = async_call_later(
            self.hass, delay, self._async_finish_confirmation_elapsed
        )

    @callback
    def _async_finish_confirmation_elapsed(self, now: datetime) -> None:
        self._cancel_finish_confirmation = None
        if self.cycle_state is not LaundryCycleState.FINAL_SPIN:
            return
        evaluation = self.finish_detector.evaluate(
            activity_detected=self.activity_detected,
            last_activity=self.last_activity,
            vibration_active=self.vibration_active,
            now=now,
        )
        self._apply_finish_diagnostics(evaluation)
        if evaluation.detected:
            self._confirm_cycle_finished()
        elif evaluation.quiet and evaluation.remaining_seconds is not None:
            self._schedule_finish_confirmation(evaluation.remaining_seconds)
            self._notify_entities()

    @callback
    def _confirm_cycle_finished(self) -> None:
        self._cancel_pending_finish_confirmation()
        self.async_set_cycle_state(
            LaundryCycleState.FINISHED,
            REASON_FINISH_INACTIVITY_CONFIRMED,
        )
        self.hass.bus.async_fire(EVENT_CYCLE_FINISHED, {
            "config_entry_id": self.entry.entry_id,
            "name": self.name,
            "quiet_since": self.finish_quiet_since,
            "confirmation_seconds": self.finish_detector.confirmation_seconds,
        })

    @callback
    def _apply_finish_diagnostics(self, evaluation: FinishEvaluation) -> None:
        self.finish_quiet_since = evaluation.quiet_since
        self.finish_deadline = evaluation.deadline
        self.finish_remaining_seconds = (
            round(evaluation.remaining_seconds,1)
            if evaluation.remaining_seconds is not None else None
        )

    @callback
    def _reset_finish_detection(self) -> None:
        self._cancel_pending_finish_confirmation()
        self.finish_detector.reset()
        self.finish_quiet_since = None
        self.finish_deadline = None
        self.finish_remaining_seconds = None

    @callback
    def _cancel_pending_finish_confirmation(self) -> None:
        if self._cancel_finish_confirmation is not None:
            self._cancel_finish_confirmation()
            self._cancel_finish_confirmation = None

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
