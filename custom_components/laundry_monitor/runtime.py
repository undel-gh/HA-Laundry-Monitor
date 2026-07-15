"""Runtime state and source-entity subscriptions for Laundry Monitor."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isfinite

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .activity import ActivityDetector, ActivityEvaluation
from .const import (
    CONF_ACTIVITY_THRESHOLD,
    CONF_ARMING_TIMEOUT,
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_FINISHED_RETENTION,
    CONF_FINISH_CONFIRMATION,
    CONF_LEAK_SENSOR,
    CONF_POWER_SENSOR,
    CONF_POWER_UNAVAILABLE_GRACE,
    CONF_RUNNING_FINISH_CONFIRMATION,
    CONF_SNAPSHOT_MAX_AGE,
    CONF_SPIN_ACTIVITY_MAX_AGE,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    CONF_START_CONFIRMATION,
    CONF_START_THRESHOLD,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DEFAULT_ACTIVITY_THRESHOLD,
    DEFAULT_ARMING_TIMEOUT,
    DEFAULT_FINISHED_RETENTION,
    DEFAULT_FINISH_CONFIRMATION,
    DEFAULT_POWER_UNAVAILABLE_GRACE,
    DEFAULT_RUNNING_FINISH_CONFIRMATION,
    DEFAULT_SNAPSHOT_MAX_AGE,
    DEFAULT_SPIN_ACTIVITY_MAX_AGE,
    DEFAULT_SPIN_MIN_CYCLE_TIME,
    DEFAULT_SPIN_REQUIRED_EVENTS,
    DEFAULT_SPIN_WINDOW,
    DEFAULT_START_CONFIRMATION,
    DEFAULT_START_THRESHOLD,
    EVENT_CYCLE_FINISHED,
    EVENT_CYCLE_STARTED,
    EVENT_DOOR_OPENED_AFTER_FINISH,
    EVENT_FINAL_SPIN_DETECTED,
    EVENT_LEAK_DETECTED,
    EVENT_MACHINE_UNLOADED,
    EVENT_STATE_CHANGED,
    EVENT_TRANSITION_REJECTED,
    LaundryCycleState,
    REASON_ACTIVITY_RESUMED_AFTER_FINAL_SPIN,
    REASON_ARMING_TIMEOUT,
    REASON_DOOR_CLOSED,
    REASON_DOOR_OPENED_BEFORE_START,
    REASON_FINAL_SPIN_CONFIRMED,
    REASON_FINISHED_RETENTION_EXPIRED,
    REASON_FINISH_FALLBACK_CONFIRMED,
    REASON_FINISH_INACTIVITY_CONFIRMED,
    REASON_INITIAL_SETUP,
    REASON_MARKED_UNLOADED,
    REASON_POWER_ABOVE_START_THRESHOLD,
    REASON_POWER_SENSOR_RECOVERED,
    REASON_POWER_SENSOR_UNAVAILABLE,
    REASON_STATE_RECOVERY_FALLBACK,
    REASON_STATE_RESTORED,
    SIGNAL_RUNTIME_UPDATED,
)
from .finish import FinishDetector, FinishEvaluation
from .spin import SpinDetector
from .state_machine import LaundryStateMachine, TransitionStatus
from .storage import LaundryStateStore, RuntimeSnapshot, select_recovery_state

_STARTABLE_STATES = (
    LaundryCycleState.IDLE,
    LaundryCycleState.ARMED,
    LaundryCycleState.FINISHED,
)
_FINISH_EVALUATION_STATES = (
    LaundryCycleState.RUNNING,
    LaundryCycleState.FINAL_SPIN,
)
_CYCLE_STATISTICS_UPDATE_INTERVAL = timedelta(seconds=30)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LaundryMonitorRuntime:
    """Runtime data for one Laundry Monitor config entry."""

    hass: HomeAssistant
    entry: ConfigEntry
    state_store: LaundryStateStore

    cycle_state: LaundryCycleState = LaundryCycleState.IDLE
    last_transition_reason: str = REASON_INITIAL_SETUP
    last_state_change: datetime = field(default_factory=dt_util.utcnow)

    power: float | None = None
    door_open: bool | None = None
    vibration_active: bool | None = None
    leak_detected: bool = False
    energy: float | None = None
    energy_unit: str | None = None
    laundry_present: bool = False
    last_unloaded_at: datetime | None = None
    cycle_started_at: datetime | None = None
    cycle_energy_start: float | None = None
    cycle_energy_unit: str | None = None
    last_cycle_duration: float | None = None
    last_cycle_energy: float | None = None
    last_cycle_energy_unit: str | None = None
    final_spin_detected: bool = False

    final_spin_confidence: float = 0.0
    final_spin_evidence_count: int = 0
    finish_quiet_since: datetime | None = None
    finish_deadline: datetime | None = None
    finish_remaining_seconds: float | None = None

    state_machine: LaundryStateMachine = field(init=False)
    rejected_transition_count: int = 0
    last_rejected_transition: str | None = None

    activity_detector: ActivityDetector = field(init=False)
    spin_detector: SpinDetector = field(init=False)
    finish_detector: FinishDetector = field(init=False)
    running_finish_detector: FinishDetector = field(init=False)

    _remove_source_listener: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _cancel_start_confirmation: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _cancel_finish_confirmation: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _cancel_arming_timeout: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _cancel_finished_retention: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _cancel_power_unavailable: Callable[[], None] | None = field(
        default=None,
        init=False,
    )
    _remove_statistics_interval: Callable[[], None] | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        """Initialize detector modules from config-entry options."""
        self.state_machine = LaundryStateMachine(state=self.cycle_state)
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
            confirmation_seconds=int(
                self.entry.options.get(
                    CONF_FINISH_CONFIRMATION,
                    DEFAULT_FINISH_CONFIRMATION,
                )
            )
        )
        self.running_finish_detector = FinishDetector(
            confirmation_seconds=int(
                self.entry.options.get(
                    CONF_RUNNING_FINISH_CONFIRMATION,
                    DEFAULT_RUNNING_FINISH_CONFIRMATION,
                )
            )
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
    def arming_timeout_seconds(self) -> int:
        """Return how long the optional armed state may remain active."""
        return int(
            self.entry.options.get(
                CONF_ARMING_TIMEOUT,
                DEFAULT_ARMING_TIMEOUT,
            )
        )

    @property
    def finished_retention_seconds(self) -> int:
        """Return completed-state retention when tracking is disabled."""
        return int(
            self.entry.options.get(
                CONF_FINISHED_RETENTION,
                DEFAULT_FINISHED_RETENTION,
            )
        )

    @property
    def power_unavailable_grace_seconds(self) -> int:
        """Return allowed power-source unavailability duration."""
        return int(
            self.entry.options.get(
                CONF_POWER_UNAVAILABLE_GRACE,
                DEFAULT_POWER_UNAVAILABLE_GRACE,
            )
        )

    @property
    def snapshot_max_age_seconds(self) -> int:
        """Return maximum age of an active-cycle snapshot."""
        return int(
            self.entry.options.get(
                CONF_SNAPSHOT_MAX_AGE,
                DEFAULT_SNAPSHOT_MAX_AGE,
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
    def current_cycle_duration(self) -> float | None:
        """Return elapsed seconds for the active cycle."""
        if (
            self.cycle_started_at is None
            or self.cycle_state not in _FINISH_EVALUATION_STATES
        ):
            return None
        return round(
            max(
                (dt_util.utcnow() - self.cycle_started_at).total_seconds(),
                0.0,
            ),
            1,
        )

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
        _LOGGER.debug(
            "Starting Laundry Monitor runtime for entry %s (%s)",
            self.entry.entry_id,
            self.name,
        )
        self._read_all_source_states()
        await self._async_restore_snapshot()

        if self.source_entity_ids:
            self._remove_source_listener = async_track_state_change_event(
                self.hass,
                self.source_entity_ids,
                self._async_source_state_changed,
            )

        self._resume_lifecycle_after_start()
        _LOGGER.debug(
            "Laundry Monitor runtime ready for entry %s (%s): "
            "state=%s, power=%s, door_open=%s, vibration_active=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
            self.power,
            self.door_open,
            self.vibration_active,
        )

    async def async_stop(self) -> None:
        """Remove runtime subscriptions and timers."""
        _LOGGER.debug(
            "Stopping Laundry Monitor runtime for entry %s (%s)",
            self.entry.entry_id,
            self.name,
        )
        if self._remove_source_listener is not None:
            self._remove_source_listener()
            self._remove_source_listener = None

        self._cancel_pending_start_confirmation("runtime stopping")
        self._cancel_pending_finish_confirmation("runtime stopping")
        self._cancel_pending_arming_timeout("runtime stopping")
        self._cancel_pending_finished_retention("runtime stopping")
        self._cancel_pending_power_unavailable("runtime stopping")
        self._cancel_cycle_statistics_updates()

    def _snapshot(self) -> RuntimeSnapshot:
        """Return the persistable part of runtime state."""
        return RuntimeSnapshot(
            cycle_state=self.cycle_state,
            last_transition_reason=self.last_transition_reason,
            last_state_change=self.last_state_change,
            cycle_started_at=self.cycle_started_at,
            laundry_present=self.laundry_present,
            last_unloaded_at=self.last_unloaded_at,
            cycle_energy_start=self.cycle_energy_start,
            cycle_energy_unit=self.cycle_energy_unit,
            last_cycle_duration=self.last_cycle_duration,
            last_cycle_energy=self.last_cycle_energy,
            last_cycle_energy_unit=self.last_cycle_energy_unit,
            final_spin_detected=self.final_spin_detected,
        )

    @callback
    def _schedule_snapshot_save(self) -> None:
        """Schedule persistence without blocking the state callback."""
        self.hass.async_create_task(
            self.state_store.async_save(
                self.entry.entry_id,
                self._snapshot(),
            )
        )

    async def _async_restore_snapshot(self) -> None:
        """Restore a snapshot using the configured recovery policy."""
        snapshot = await self.state_store.async_get(self.entry.entry_id)
        if snapshot is None:
            _LOGGER.debug(
                "No runtime snapshot found for entry %s (%s)",
                self.entry.entry_id,
                self.name,
            )
            return

        now = dt_util.utcnow()
        snapshot_age_seconds = max(
            (now - snapshot.last_state_change).total_seconds(),
            0.0,
        )
        recovered_state = select_recovery_state(
            snapshot,
            door_open=self.door_open,
            activity_detected=self.activity_detected,
            vibration_active=self.vibration_active,
            now=now,
            tracking_enabled=self.tracking_enabled,
            arming_timeout_seconds=self.arming_timeout_seconds,
            finished_retention_seconds=self.finished_retention_seconds,
            max_active_snapshot_age_seconds=self.snapshot_max_age_seconds,
            power_available=self.power is not None,
            require_final_spin_context=True,
        )

        _LOGGER.debug(
            "Snapshot recovery selected for entry %s (%s): "
            "stored_state=%s, recovered_state=%s, age=%.1fs, "
            "power_available=%s, activity_detected=%s, "
            "door_open=%s, vibration_active=%s",
            self.entry.entry_id,
            self.name,
            snapshot.cycle_state.value,
            recovered_state.value,
            snapshot_age_seconds,
            self.power is not None,
            self.activity_detected,
            self.door_open,
            self.vibration_active,
        )

        self.state_machine.restore(recovered_state)
        self.cycle_state = recovered_state
        self.last_transition_reason = (
            REASON_STATE_RESTORED
            if recovered_state is snapshot.cycle_state
            else REASON_STATE_RECOVERY_FALLBACK
        )
        self.last_state_change = (
            snapshot.last_state_change
            if recovered_state is snapshot.cycle_state
            else dt_util.utcnow()
        )
        self.laundry_present = snapshot.laundry_present
        self.last_unloaded_at = snapshot.last_unloaded_at
        self.last_cycle_duration = snapshot.last_cycle_duration
        self.last_cycle_energy = snapshot.last_cycle_energy
        self.last_cycle_energy_unit = snapshot.last_cycle_energy_unit
        if (
            not self.tracking_enabled
            and snapshot.cycle_state is LaundryCycleState.FINISHED
            and recovered_state is LaundryCycleState.IDLE
        ):
            self.laundry_present = False

        active_cycle_restored = recovered_state in _FINISH_EVALUATION_STATES
        self.cycle_started_at = (
            snapshot.cycle_started_at if active_cycle_restored else None
        )
        self.cycle_energy_start = (
            snapshot.cycle_energy_start if active_cycle_restored else None
        )
        self.cycle_energy_unit = (
            snapshot.cycle_energy_unit if active_cycle_restored else None
        )
        discarded_active_cycle = (
            snapshot.cycle_state in _FINISH_EVALUATION_STATES
            and not active_cycle_restored
        )
        self.final_spin_detected = (
            False
            if discarded_active_cycle
            else snapshot.final_spin_detected
        )

        self.spin_detector.reset(vibration_active=self.vibration_active)
        self.final_spin_confidence = 0.0
        self.final_spin_evidence_count = 0
        self._reset_finish_detection()

        if recovered_state is not snapshot.cycle_state:
            _LOGGER.debug(
                "Applied snapshot recovery fallback for entry %s (%s): "
                "%s -> %s",
                self.entry.entry_id,
                self.name,
                snapshot.cycle_state.value,
                recovered_state.value,
            )
            self._schedule_snapshot_save()
        else:
            _LOGGER.debug(
                "Restored runtime snapshot for entry %s (%s) in state %s",
                self.entry.entry_id,
                self.name,
                recovered_state.value,
            )

    @callback
    def _resume_lifecycle_after_start(self) -> None:
        """Resume safe timers after current states and snapshot are loaded."""
        if self.power is None:
            self._schedule_power_unavailable_error()
        else:
            # Re-evaluate the current power level after setup so a machine
            # already above the start threshold does not require a new state
            # event before cycle detection begins.
            self._handle_power_update()

        if self.cycle_state is LaundryCycleState.ARMED:
            self._schedule_arming_timeout(from_timestamp=self.last_state_change)
        elif self.cycle_state is LaundryCycleState.FINISHED:
            self._schedule_finished_retention(
                from_timestamp=self.last_state_change
            )

        if self.cycle_state in _FINISH_EVALUATION_STATES:
            self._start_cycle_statistics_updates()
            self._evaluate_finish()

    @callback
    def _read_all_source_states(self) -> None:
        """Read current states without creating public transitions."""
        for entity_id in self.source_entity_ids:
            self._update_source(entity_id, self.hass.states.get(entity_id))

        if self.power is not None:
            self.activity_detector.evaluate(self.power)
        self.spin_detector.reset(vibration_active=self.vibration_active)

    @callback
    def _async_source_state_changed(
        self,
        event: Event[EventStateChangedData],
    ) -> None:
        """Handle a source entity state change."""
        entity_id = event.data["entity_id"]
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        old_door_open = self.door_open
        old_leak = self.leak_detected

        old_available = _state_is_available(old_state)
        new_available = _state_is_available(new_state)
        if old_available != new_available:
            _LOGGER.debug(
                "Source availability changed for entry %s (%s): "
                "entity=%s, available=%s, state=%s",
                self.entry.entry_id,
                self.name,
                entity_id,
                new_available,
                new_state.state if new_state is not None else None,
            )

        if not self._update_source(entity_id, new_state):
            return

        power_entity = self.entry.data.get(CONF_POWER_SENSOR)
        door_entity = self.entry.data.get(CONF_DOOR_SENSOR)
        vibration_entity = self.entry.data.get(CONF_VIBRATION_SENSOR)

        if entity_id == power_entity:
            self._handle_power_update()
        elif entity_id == door_entity:
            self._handle_door_update(old_door_open)

        if entity_id in (power_entity, vibration_entity):
            self._evaluate_spin()
            self._evaluate_finish()

        if not old_leak and self.leak_detected:
            self.hass.bus.async_fire(
                EVENT_LEAK_DETECTED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "source_entity_id": entity_id,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

        self._notify_entities()

    @callback
    def _handle_power_update(self) -> None:
        """Evaluate power activity, availability, and cycle starts."""
        if self.power is None:
            self._cancel_pending_start_confirmation("power unavailable")
            self._reset_finish_detection()
            self._schedule_power_unavailable_error()
            return

        self._cancel_pending_power_unavailable("power data recovered")

        if self.cycle_state is LaundryCycleState.ERROR:
            self.async_set_cycle_state(
                LaundryCycleState.IDLE,
                REASON_POWER_SENSOR_RECOVERED,
            )

        evaluation = self.activity_detector.evaluate(self.power)

        if self._resume_running_after_final_spin(evaluation):
            return

        if evaluation.start_candidate:
            self._schedule_start_confirmation()
        else:
            self._cancel_pending_start_confirmation(
                "power below start threshold"
            )
            if (
                self.cycle_state is LaundryCycleState.FINISHED
                and not self.tracking_enabled
            ):
                self._schedule_finished_retention(
                    from_timestamp=self.last_state_change
                )

    @callback
    def _resume_running_after_final_spin(
        self,
        evaluation: ActivityEvaluation,
    ) -> bool:
        """Return to running on a real inactivity-to-activity edge."""
        if (
            self.cycle_state is LaundryCycleState.FINAL_SPIN
            and evaluation.activity_detected
            and evaluation.activity_changed
        ):
            _LOGGER.debug(
                "Meaningful activity resumed after final spin for entry "
                "%s (%s): power=%s",
                self.entry.entry_id,
                self.name,
                self.power,
            )
            return self.async_set_cycle_state(
                LaundryCycleState.RUNNING,
                REASON_ACTIVITY_RESUMED_AFTER_FINAL_SPIN,
            )
        return False

    @callback
    def _handle_door_update(self, old_door_open: bool | None) -> None:
        """Handle public transitions and diagnostics caused by the door."""
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
            self._cancel_pending_start_confirmation(
                "door opened before cycle start"
            )
            self.async_set_cycle_state(
                LaundryCycleState.IDLE,
                REASON_DOOR_OPENED_BEFORE_START,
            )
            return

        if (
            old_door_open is False
            and self.door_open is True
            and self.cycle_state is LaundryCycleState.FINISHED
        ):
            self.hass.bus.async_fire(
                EVENT_DOOR_OPENED_AFTER_FINISH,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

    @callback
    def _schedule_start_confirmation(self) -> None:
        """Schedule confirmation of sustained start-level power."""
        if self.cycle_state not in _STARTABLE_STATES:
            return
        if self._cancel_start_confirmation is not None:
            return

        _LOGGER.debug(
            "Scheduled start confirmation for entry %s (%s): "
            "state=%s, delay=%ss, power=%s, start_threshold=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
            self.start_confirmation_seconds,
            self.power,
            self.activity_detector.start_threshold,
        )
        self._cancel_start_confirmation = async_call_later(
            self.hass,
            self.start_confirmation_seconds,
            self._async_confirm_cycle_start,
        )

    @callback
    def _async_confirm_cycle_start(self, now: datetime) -> None:
        """Confirm a cycle start after sustained high power."""
        self._cancel_start_confirmation = None

        if self.cycle_state not in _STARTABLE_STATES:
            return
        if self.power is None or not self.activity_detector.start_candidate:
            return

        old_state = self.cycle_state
        if not self.async_set_cycle_state(
            LaundryCycleState.RUNNING,
            REASON_POWER_ABOVE_START_THRESHOLD,
        ):
            return

        self.hass.bus.async_fire(
            EVENT_CYCLE_STARTED,
            {
                "config_entry_id": self.entry.entry_id,
                "name": self.name,
                "old_state": old_state.value,
                "new_state": LaundryCycleState.RUNNING.value,
                "power": self.power,
                "start_threshold": self.activity_detector.start_threshold,
                "confirmation_seconds": self.start_confirmation_seconds,
                "timestamp": now.isoformat(),
            },
        )

    @callback
    def _cancel_pending_start_confirmation(
        self,
        reason: str = "conditions changed",
    ) -> None:
        """Cancel a pending cycle-start confirmation timer."""
        if self._cancel_start_confirmation is not None:
            self._cancel_start_confirmation()
            self._cancel_start_confirmation = None
            _LOGGER.debug(
                "Cancelled start confirmation for entry %s (%s): %s",
                self.entry.entry_id,
                self.name,
                reason,
            )

    @callback
    def _schedule_arming_timeout(
        self,
        *,
        from_timestamp: datetime | None = None,
    ) -> None:
        """Schedule deterministic armed-to-idle recovery."""
        self._cancel_pending_arming_timeout("arming timeout rescheduled")
        if self.cycle_state is not LaundryCycleState.ARMED:
            return

        delay = float(self.arming_timeout_seconds)
        if from_timestamp is not None:
            delay -= max(
                (dt_util.utcnow() - from_timestamp).total_seconds(),
                0.0,
            )

        delay = max(delay, 0.0)
        _LOGGER.debug(
            "Scheduled arming timeout for entry %s (%s): delay=%.1fs",
            self.entry.entry_id,
            self.name,
            delay,
        )
        self._cancel_arming_timeout = async_call_later(
            self.hass,
            delay,
            self._async_arming_timeout_elapsed,
        )

    @callback
    def _async_arming_timeout_elapsed(self, _now: datetime) -> None:
        """Return an expired armed state to idle."""
        self._cancel_arming_timeout = None
        _LOGGER.debug(
            "Arming timeout elapsed for entry %s (%s): state=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
        )
        if self.cycle_state is LaundryCycleState.ARMED:
            self.async_set_cycle_state(
                LaundryCycleState.IDLE,
                REASON_ARMING_TIMEOUT,
            )

    @callback
    def _cancel_pending_arming_timeout(
        self,
        reason: str = "state changed",
    ) -> None:
        """Cancel the armed-state timeout."""
        if self._cancel_arming_timeout is not None:
            self._cancel_arming_timeout()
            self._cancel_arming_timeout = None
            _LOGGER.debug(
                "Cancelled arming timeout for entry %s (%s): %s",
                self.entry.entry_id,
                self.name,
                reason,
            )

    @callback
    def _schedule_finished_retention(
        self,
        *,
        from_timestamp: datetime | None = None,
    ) -> None:
        """Schedule finished-to-idle when Laundry Tracking is disabled."""
        self._cancel_pending_finished_retention(
            "finished retention rescheduled"
        )
        if (
            self.tracking_enabled
            or self.cycle_state is not LaundryCycleState.FINISHED
        ):
            return

        delay = float(self.finished_retention_seconds)
        if from_timestamp is not None:
            delay -= max(
                (dt_util.utcnow() - from_timestamp).total_seconds(),
                0.0,
            )

        delay = max(delay, 0.0)
        _LOGGER.debug(
            "Scheduled finished-state retention for entry %s (%s): "
            "delay=%.1fs, tracking_enabled=%s",
            self.entry.entry_id,
            self.name,
            delay,
            self.tracking_enabled,
        )
        self._cancel_finished_retention = async_call_later(
            self.hass,
            delay,
            self._async_finished_retention_elapsed,
        )

    @callback
    def _async_finished_retention_elapsed(self, _now: datetime) -> None:
        """Reset an observable finished state after its retention period."""
        self._cancel_finished_retention = None
        _LOGGER.debug(
            "Finished-state retention elapsed for entry %s (%s): "
            "state=%s, tracking_enabled=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
            self.tracking_enabled,
        )
        self._reset_finished_without_tracking()

    @callback
    def _reset_finished_without_tracking(self) -> None:
        """Return finished to idle only when explicit tracking is disabled."""
        if (
            self.tracking_enabled
            or self.cycle_state is not LaundryCycleState.FINISHED
        ):
            return

        # A start confirmation already in progress takes precedence over the
        # retention reset. If power drops again, _handle_power_update()
        # immediately re-evaluates the expired retention period.
        if (
            self.activity_detector.start_candidate
            and self._cancel_start_confirmation is not None
        ):
            return

        self.laundry_present = False
        self.async_set_cycle_state(
            LaundryCycleState.IDLE,
            REASON_FINISHED_RETENTION_EXPIRED,
        )

    @callback
    def _cancel_pending_finished_retention(
        self,
        reason: str = "state changed",
    ) -> None:
        """Cancel completed-state retention."""
        if self._cancel_finished_retention is not None:
            self._cancel_finished_retention()
            self._cancel_finished_retention = None
            _LOGGER.debug(
                "Cancelled finished-state retention for entry %s (%s): %s",
                self.entry.entry_id,
                self.name,
                reason,
            )

    @callback
    def _schedule_power_unavailable_error(self) -> None:
        """Enter error only after the required power source grace period."""
        if self.power is not None:
            return
        if self.cycle_state is LaundryCycleState.ERROR:
            return
        if self._cancel_power_unavailable is not None:
            return

        _LOGGER.debug(
            "Scheduled power-unavailable grace period for entry %s (%s): "
            "delay=%ss",
            self.entry.entry_id,
            self.name,
            self.power_unavailable_grace_seconds,
        )
        self._cancel_power_unavailable = async_call_later(
            self.hass,
            self.power_unavailable_grace_seconds,
            self._async_power_unavailable_elapsed,
        )

    @callback
    def _async_power_unavailable_elapsed(self, _now: datetime) -> None:
        """Enter error when required power data stayed unavailable."""
        self._cancel_power_unavailable = None
        _LOGGER.debug(
            "Power-unavailable grace period elapsed for entry %s (%s): "
            "power=%s",
            self.entry.entry_id,
            self.name,
            self.power,
        )
        if self.power is None:
            self.async_set_cycle_state(
                LaundryCycleState.ERROR,
                REASON_POWER_SENSOR_UNAVAILABLE,
            )

    @callback
    def _cancel_pending_power_unavailable(
        self,
        reason: str = "power data available",
    ) -> None:
        """Cancel pending required-source failure confirmation."""
        if self._cancel_power_unavailable is not None:
            self._cancel_power_unavailable()
            self._cancel_power_unavailable = None
            _LOGGER.debug(
                "Cancelled power-unavailable grace period for entry "
                "%s (%s): %s",
                self.entry.entry_id,
                self.name,
                reason,
            )

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
            value = _state_as_float(state)
            unit = (
                str(state.attributes[ATTR_UNIT_OF_MEASUREMENT])
                if state is not None
                and value is not None
                and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                else None
            )
            if self.energy == value and self.energy_unit == unit:
                return False
            self.energy = value
            self.energy_unit = unit
            return True
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
        """Validate, apply, publish, and persist a public transition."""
        transition_time = dt_util.utcnow()
        result = self.state_machine.transition(
            new_state,
            reason=reason,
            now=transition_time,
        )

        if result.status is TransitionStatus.NO_CHANGE:
            _LOGGER.debug(
                "Ignored no-op transition for entry %s (%s): "
                "state=%s, reason=%s",
                self.entry.entry_id,
                self.name,
                new_state.value,
                reason,
            )
            return False

        if result.status is TransitionStatus.REJECTED:
            self.rejected_transition_count += 1
            self.last_rejected_transition = (
                f"{result.old_state.value}->{result.new_state.value}:{reason}"
            )
            _LOGGER.debug(
                "Rejected cycle-state transition for entry %s (%s): "
                "%s -> %s, reason=%s",
                self.entry.entry_id,
                self.name,
                result.old_state.value,
                result.new_state.value,
                reason,
            )
            self.hass.bus.async_fire(
                EVENT_TRANSITION_REJECTED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "old_state": result.old_state.value,
                    "requested_state": result.new_state.value,
                    "reason": reason,
                    "timestamp": transition_time.isoformat(),
                },
            )
            self._notify_entities()
            return False

        old_state = result.old_state
        _LOGGER.debug(
            "Applied cycle-state transition for entry %s (%s): "
            "%s -> %s, reason=%s",
            self.entry.entry_id,
            self.name,
            old_state.value,
            result.new_state.value,
            reason,
        )
        self.cycle_state = result.new_state
        self.last_transition_reason = reason
        self.last_state_change = transition_time

        self._apply_state_entry_actions(old_state, new_state)

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
                "confidence": self.final_spin_confidence,
                "timestamp": transition_time.isoformat(),
            },
        )

        self._schedule_snapshot_save()
        self._notify_entities()

        if new_state is LaundryCycleState.FINAL_SPIN:
            self._evaluate_finish()
        return True

    @callback
    def _apply_state_entry_actions(
        self,
        old_state: LaundryCycleState,
        new_state: LaundryCycleState,
    ) -> None:
        """Apply timer and detector lifecycle for an accepted transition."""
        if new_state is not LaundryCycleState.ARMED:
            self._cancel_pending_arming_timeout()
        if new_state is not LaundryCycleState.FINISHED:
            self._cancel_pending_finished_retention()

        if new_state is LaundryCycleState.RUNNING:
            self._cancel_pending_start_confirmation()
            if old_state is not LaundryCycleState.FINAL_SPIN:
                self._initialize_cycle_statistics()
            self.final_spin_confidence = 0.0
            self.final_spin_evidence_count = 0
            self.spin_detector.reset(vibration_active=self.vibration_active)
            self._reset_finish_detection()
            self._start_cycle_statistics_updates()
            return

        if new_state is LaundryCycleState.FINAL_SPIN:
            self.final_spin_detected = True
            self._reset_finish_detection()
            self._start_cycle_statistics_updates()
            return

        if new_state in (
            LaundryCycleState.IDLE,
            LaundryCycleState.ARMED,
        ):
            self._cancel_pending_start_confirmation()
            self._cancel_cycle_statistics_updates()
            self.cycle_started_at = None
            self.cycle_energy_start = None
            self.cycle_energy_unit = None
            self.final_spin_confidence = 0.0
            self.final_spin_evidence_count = 0
            self.spin_detector.reset(vibration_active=self.vibration_active)
            self._reset_finish_detection()
            if not self.tracking_enabled:
                self.laundry_present = False
            if new_state is LaundryCycleState.ARMED:
                self._schedule_arming_timeout()
            return

        if new_state is LaundryCycleState.FINISHED:
            self._cancel_pending_start_confirmation()
            self._finalize_cycle_statistics()
            self._cancel_cycle_statistics_updates()
            self._reset_finish_detection()
            self._schedule_finished_retention()
            return

        if new_state is LaundryCycleState.ERROR:
            self._cancel_pending_start_confirmation()
            self._cancel_cycle_statistics_updates()
            self._cancel_pending_arming_timeout()
            self._cancel_pending_finished_retention()
            self._reset_finish_detection()
            self.spin_detector.reset(vibration_active=self.vibration_active)

    @callback
    def _initialize_cycle_statistics(self) -> None:
        """Initialize statistics for a newly confirmed cycle."""
        self.cycle_started_at = self.last_state_change
        self.cycle_energy_start = self.energy
        self.cycle_energy_unit = self.energy_unit
        self.final_spin_detected = False
        _LOGGER.debug(
            "Initialized cycle statistics for entry %s (%s): "
            "started_at=%s, energy_start=%s, energy_unit=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_started_at,
            self.cycle_energy_start,
            self.cycle_energy_unit,
        )

    @callback
    def _finalize_cycle_statistics(self) -> None:
        """Finalize duration and optional energy for a completed cycle."""
        if self.cycle_started_at is not None:
            self.last_cycle_duration = round(
                max(
                    (self.last_state_change - self.cycle_started_at).total_seconds(),
                    0.0,
                ),
                1,
            )
        else:
            self.last_cycle_duration = None

        self.last_cycle_energy = None
        self.last_cycle_energy_unit = None
        if (
            self.cycle_energy_start is not None
            and self.energy is not None
            and self.cycle_energy_unit is not None
            and self.energy_unit == self.cycle_energy_unit
            and self.energy >= self.cycle_energy_start
        ):
            self.last_cycle_energy = round(
                self.energy - self.cycle_energy_start,
                6,
            )
            self.last_cycle_energy_unit = self.cycle_energy_unit

        _LOGGER.debug(
            "Finalized cycle statistics for entry %s (%s): "
            "duration=%s, energy=%s, energy_unit=%s, "
            "final_spin_detected=%s",
            self.entry.entry_id,
            self.name,
            self.last_cycle_duration,
            self.last_cycle_energy,
            self.last_cycle_energy_unit,
            self.final_spin_detected,
        )
        self.cycle_energy_start = None
        self.cycle_energy_unit = None

    @callback
    def _start_cycle_statistics_updates(self) -> None:
        """Start periodic updates for the live duration sensor."""
        if self.cycle_state not in _FINISH_EVALUATION_STATES:
            return
        if self._remove_statistics_interval is not None:
            return
        self._remove_statistics_interval = async_track_time_interval(
            self.hass,
            self._async_cycle_statistics_tick,
            _CYCLE_STATISTICS_UPDATE_INTERVAL,
        )

    @callback
    def _async_cycle_statistics_tick(self, _now: datetime) -> None:
        """Publish an updated live cycle duration."""
        if self.cycle_state in _FINISH_EVALUATION_STATES:
            self._notify_entities()

    @callback
    def _cancel_cycle_statistics_updates(self) -> None:
        """Stop periodic live-duration updates."""
        if self._remove_statistics_interval is not None:
            self._remove_statistics_interval()
            self._remove_statistics_interval = None

    @callback
    def async_mark_unloaded(self) -> None:
        """Mark laundry absent without fabricating a state transition."""
        if not self.tracking_enabled or not self.laundry_present:
            return

        unloaded_at = dt_util.utcnow()
        _LOGGER.debug(
            "Laundry marked unloaded for entry %s (%s): state=%s, "
            "timestamp=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
            unloaded_at.isoformat(),
        )
        self.laundry_present = False
        self.last_unloaded_at = unloaded_at

        if self.cycle_state is LaundryCycleState.FINISHED:
            self.async_set_cycle_state(
                LaundryCycleState.IDLE,
                REASON_MARKED_UNLOADED,
            )
        else:
            # Laundry presence changed without a public state transition.
            # Preserve transition metadata and persist only the tracking data.
            self._schedule_snapshot_save()
            self._notify_entities()

        self.hass.bus.async_fire(
            EVENT_MACHINE_UNLOADED,
            {
                "config_entry_id": self.entry.entry_id,
                "name": self.name,
                "timestamp": unloaded_at.isoformat(),
            },
        )

    @callback
    def _notify_entities(self) -> None:
        """Notify all entities belonging to this runtime."""
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _evaluate_spin(self) -> None:
        """Evaluate final-spin evidence when vibration is configured."""
        if self.cycle_state is not LaundryCycleState.RUNNING:
            return
        if not self.entry.data.get(CONF_VIBRATION_SENSOR):
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

        if changed or evaluation.detected:
            _LOGGER.debug(
                "Evaluated final-spin evidence for entry %s (%s): "
                "events=%s/%s, confidence=%.3f, detected=%s, "
                "activity_detected=%s, vibration_active=%s",
                self.entry.entry_id,
                self.name,
                evaluation.evidence_count,
                self.spin_detector.required_events,
                evaluation.confidence,
                evaluation.detected,
                self.activity_detected,
                self.vibration_active,
            )

        if evaluation.detected:
            if not self.async_set_cycle_state(
                LaundryCycleState.FINAL_SPIN,
                REASON_FINAL_SPIN_CONFIRMED,
            ):
                return
            self.hass.bus.async_fire(
                EVENT_FINAL_SPIN_DETECTED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "name": self.name,
                    "confidence": evaluation.confidence,
                    "evidence_count": evaluation.evidence_count,
                    "window_seconds": self.spin_detector.window_seconds,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )
            return

        if changed:
            self._notify_entities()

    def _active_finish_detector(self) -> FinishDetector | None:
        """Return the detector belonging to the current public state."""
        if self.cycle_state is LaundryCycleState.FINAL_SPIN:
            return self.finish_detector
        if self.cycle_state is LaundryCycleState.RUNNING:
            return self.running_finish_detector
        return None

    @callback
    def _evaluate_finish(self) -> None:
        """Evaluate normal completion and the no-spin fallback path."""
        detector = self._active_finish_detector()
        if detector is None:
            self._reset_finish_detection("state is not finish-evaluable")
            return

        if self.power is None:
            self._reset_finish_detection("power unavailable")
            return

        now = dt_util.utcnow()
        evaluation = detector.evaluate(
            activity_detected=self.activity_detected,
            last_activity=self.last_activity,
            vibration_active=self.vibration_active,
            now=now,
        )
        self._apply_finish_diagnostics(evaluation)

        if evaluation.detected:
            self._confirm_cycle_finished(now)
            return

        if not evaluation.quiet or evaluation.deadline is None:
            self._cancel_pending_finish_confirmation(
                "meaningful activity or vibration resumed"
            )
            self._notify_entities()
            return

        self._schedule_finish_confirmation(
            max((evaluation.deadline - now).total_seconds(), 0.0)
        )
        self._notify_entities()

    @callback
    def _schedule_finish_confirmation(self, delay: float) -> None:
        """Schedule the next finish evaluation at its exact deadline."""
        rescheduled = self._cancel_finish_confirmation is not None
        if self._cancel_finish_confirmation is not None:
            self._cancel_finish_confirmation()
            self._cancel_finish_confirmation = None
        _LOGGER.debug(
            "%s finish confirmation for entry %s (%s): "
            "state=%s, delay=%.1fs, quiet_since=%s, deadline=%s",
            "Rescheduled" if rescheduled else "Scheduled",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
            delay,
            self.finish_quiet_since,
            self.finish_deadline,
        )
        self._cancel_finish_confirmation = async_call_later(
            self.hass,
            delay,
            self._async_finish_confirmation_elapsed,
        )

    @callback
    def _async_finish_confirmation_elapsed(self, now: datetime) -> None:
        """Re-evaluate finish conditions after the confirmation period."""
        self._cancel_finish_confirmation = None
        _LOGGER.debug(
            "Finish confirmation timer elapsed for entry %s (%s): "
            "state=%s",
            self.entry.entry_id,
            self.name,
            self.cycle_state.value,
        )
        detector = self._active_finish_detector()
        if detector is None or self.power is None:
            return

        evaluation = detector.evaluate(
            activity_detected=self.activity_detected,
            last_activity=self.last_activity,
            vibration_active=self.vibration_active,
            now=now,
        )
        self._apply_finish_diagnostics(evaluation)

        if evaluation.detected:
            self._confirm_cycle_finished(now)
        elif evaluation.quiet and evaluation.remaining_seconds is not None:
            self._schedule_finish_confirmation(evaluation.remaining_seconds)
            self._notify_entities()

    @callback
    def _confirm_cycle_finished(self, now: datetime) -> None:
        """Apply and publish one confirmed cycle completion."""
        old_state = self.cycle_state
        detector = self._active_finish_detector()
        if detector is None:
            return

        reason = (
            REASON_FINISH_INACTIVITY_CONFIRMED
            if old_state is LaundryCycleState.FINAL_SPIN
            else REASON_FINISH_FALLBACK_CONFIRMED
        )
        quiet_since = self.finish_quiet_since
        confirmation_seconds = detector.confirmation_seconds

        _LOGGER.debug(
            "Finish conditions confirmed for entry %s (%s): "
            "state=%s, quiet_since=%s, confirmation=%ss",
            self.entry.entry_id,
            self.name,
            old_state.value,
            quiet_since,
            confirmation_seconds,
        )
        self._cancel_pending_finish_confirmation(
            "finish conditions confirmed"
        )
        if not self.async_set_cycle_state(
            LaundryCycleState.FINISHED,
            reason,
        ):
            return

        self.hass.bus.async_fire(
            EVENT_CYCLE_FINISHED,
            {
                "config_entry_id": self.entry.entry_id,
                "name": self.name,
                "old_state": old_state.value,
                "new_state": LaundryCycleState.FINISHED.value,
                "quiet_since": (
                    quiet_since.isoformat()
                    if quiet_since is not None
                    else None
                ),
                "confirmation_seconds": confirmation_seconds,
                "timestamp": now.isoformat(),
            },
        )

    @callback
    def _apply_finish_diagnostics(
        self,
        evaluation: FinishEvaluation,
    ) -> None:
        """Expose the active finish detector's timer state."""
        self.finish_quiet_since = evaluation.quiet_since
        self.finish_deadline = evaluation.deadline
        self.finish_remaining_seconds = (
            round(evaluation.remaining_seconds, 1)
            if evaluation.remaining_seconds is not None
            else None
        )

    @callback
    def _reset_finish_detection(
        self,
        reason: str = "finish detection reset",
    ) -> None:
        """Reset both completion paths and their shared diagnostics."""
        self._cancel_pending_finish_confirmation(reason)
        self.finish_detector.reset()
        self.running_finish_detector.reset()
        self.finish_quiet_since = None
        self.finish_deadline = None
        self.finish_remaining_seconds = None

    @callback
    def _cancel_pending_finish_confirmation(
        self,
        reason: str = "conditions changed",
    ) -> None:
        """Cancel the active finish timer."""
        if self._cancel_finish_confirmation is not None:
            self._cancel_finish_confirmation()
            self._cancel_finish_confirmation = None
            _LOGGER.debug(
                "Cancelled finish confirmation for entry %s (%s): %s",
                self.entry.entry_id,
                self.name,
                reason,
            )


def _state_is_available(state: State | None) -> bool:
    """Return whether a source entity has a usable HA state."""
    return (
        state is not None
        and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    )


def _state_as_float(state: State | None) -> float | None:
    """Convert a Home Assistant state to float."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None

    return value if isfinite(value) else None


def _state_as_bool(state: State | None) -> bool | None:
    """Convert a binary Home Assistant state to bool."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    return state.state == STATE_ON
