"""Test snapshot validation and recovery policy."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.laundry_monitor.const import LaundryCycleState
from custom_components.laundry_monitor.storage import (
    RuntimeSnapshot,
    select_recovery_state,
)

def _snapshot(state: LaundryCycleState) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        cycle_state=state,
        last_transition_reason="test",
        last_state_change=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        cycle_started_at=datetime(2026, 7, 14, 11, 0, tzinfo=timezone.utc),
        laundry_present=state in {
            LaundryCycleState.RUNNING,
            LaundryCycleState.FINAL_SPIN,
            LaundryCycleState.FINISHED,
        },
    )


@pytest.mark.parametrize("state", list(LaundryCycleState))

def _state_test_id(state: LaundryCycleState) -> str:
    """Return a CI-safe parameter ID."""
    if state is LaundryCycleState.ERROR:
        return "state-fault"

    return f"state-{state.value}"


@pytest.mark.parametrize(
    "state",
    list(LaundryCycleState),
    ids=_state_test_id,
)
def test_snapshot_round_trip(
    state: LaundryCycleState,
) -> None:
    """Test serialization of every public state."""
    snapshot = _snapshot(state)

    restored = RuntimeSnapshot.from_storage_dict(
        snapshot.as_storage_dict()
    )

    assert restored == snapshot

@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"cycle_state": "not-a-state"},
        {
            "cycle_state": "idle",
            "last_transition_reason": "test",
            "last_state_change": "invalid",
            "cycle_started_at": None,
            # A mandatory non-timing field is absent.
        },
    ],
)

def test_invalid_snapshot_is_ignored(
    invalid: dict[str, object],
) -> None:
    """Test corrupt storage cannot break integration setup."""
    assert RuntimeSnapshot.from_storage_dict(invalid) is None

def test_armed_recovery_requires_closed_door() -> None:
    snapshot = _snapshot(LaundryCycleState.ARMED)

    assert select_recovery_state(
        snapshot,
        door_open=False,
        activity_detected=False,
        vibration_active=False,
    ) is LaundryCycleState.ARMED

    assert select_recovery_state(
        snapshot,
        door_open=True,
        activity_detected=False,
        vibration_active=False,
    ) is LaundryCycleState.IDLE


@pytest.mark.parametrize(
    "state",
    [
        LaundryCycleState.RUNNING,
        LaundryCycleState.FINAL_SPIN,
        LaundryCycleState.FINISHED,
        LaundryCycleState.ERROR,
    ],
    ids=_state_test_id,
)
def test_meaningful_states_survive_restart(
    state: LaundryCycleState,
) -> None:
    """Test restoration does not lose meaningful states."""
    assert (
        select_recovery_state(
            _snapshot(state),
            door_open=False,
            activity_detected=False,
            vibration_active=False,
        )
        is state
    )


def test_snapshot_without_last_unloaded_at_is_backward_compatible() -> None:
    """Test snapshots written before unload timestamps still load."""
    stored = _snapshot(LaundryCycleState.FINISHED).as_storage_dict()
    stored.pop("last_unloaded_at")

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_unloaded_at is None


def test_snapshot_without_heating_fields_is_backward_compatible() -> None:
    """Test snapshots written before heating context still load safely."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored.pop("heating_detected")
    stored.pop("heating_detected_at")

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.heating_detected is False
    assert restored.heating_detected_at is None


def test_invalid_heating_detected_timestamp_is_discarded_locally() -> None:
    """Bad heating timing must not invalidate an otherwise safe snapshot."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["heating_detected"] = True
    stored["heating_detected_at"] = "not-a-timestamp"

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.laundry_present is True
    assert restored.heating_detected is True
    assert restored.heating_detected_at is None


def test_heating_detected_round_trip() -> None:
    """Test the latched heating fact survives serialization."""
    detected_at = datetime(2026, 7, 14, 11, 10, tzinfo=timezone.utc)
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="test",
        last_state_change=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        cycle_started_at=datetime(2026, 7, 14, 11, 0, tzinfo=timezone.utc),
        laundry_present=True,
        heating_detected=True,
        heating_detected_at=detected_at,
    )

    assert RuntimeSnapshot.from_storage_dict(
        snapshot.as_storage_dict()
    ) == snapshot

def test_not_seen_fingerprint_and_spin_evidence_round_trip() -> None:
    """Persist safe NOT_SEEN proof and the live vibration window."""
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="test",
        last_state_change=now,
        cycle_started_at=now - timedelta(minutes=10),
        laundry_present=True,
        heating_not_seen=True,
        heating_detector_version=1,
        heating_power_threshold_w=1000.0,
        heating_confirmation_seconds=30,
        heating_observation_seconds=300,
        heating_max_source_age_seconds=30,
        spin_evidence_timestamps=(
            now - timedelta(seconds=120),
            now - timedelta(seconds=60),
        ),
    )

    assert RuntimeSnapshot.from_storage_dict(
        snapshot.as_storage_dict()
    ) == snapshot


def test_not_seen_without_complete_fingerprint_fails_closed() -> None:
    """Incomplete persisted calibration must not restore NOT_SEEN."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["heating_not_seen"] = True
    stored["heating_detector_version"] = 1
    stored["heating_power_threshold_w"] = 1000.0
    stored["heating_confirmation_seconds"] = 30
    stored["heating_observation_seconds"] = 300
    stored["heating_max_source_age_seconds"] = None

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.heating_not_seen is False


def test_invalid_spin_evidence_timestamps_are_discarded_locally() -> None:
    """Bad vibration metadata must not discard the whole snapshot."""
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["laundry_present"] = True
    stored["last_cycle_duration"] = 1234.0
    stored["spin_evidence_timestamps"] = [
        (now - timedelta(seconds=60)).isoformat(),
        "not-a-timestamp",
        "2026-09-22T11:59:30",
        123,
    ]

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 1234.0
    assert restored.spin_evidence_timestamps == (
        now - timedelta(seconds=60),
    )


def test_corrupt_heating_fingerprint_only_drops_not_seen_proof() -> None:
    """Corrupt recovery proof degrades heating to UNKNOWN, not the cycle."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["laundry_present"] = True
    stored["last_cycle_energy"] = 0.42
    stored["heating_not_seen"] = True
    stored["heating_detector_version"] = "abc"
    stored["heating_power_threshold_w"] = "broken"
    stored["heating_confirmation_seconds"] = 30
    stored["heating_observation_seconds"] = 300
    stored["heating_max_source_age_seconds"] = 30

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.laundry_present is True
    assert restored.last_cycle_energy == 0.42
    assert restored.heating_not_seen is False
    assert restored.heating_detector_version is None
    assert restored.heating_power_threshold_w is None


def test_naive_heating_detected_at_is_discarded_locally() -> None:
    """Naive diagnostic time cannot poison an otherwise valid snapshot."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["heating_detected"] = True
    stored["heating_detected_at"] = "2026-09-22T11:59:30"

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.heating_detected is True
    assert restored.heating_detected_at is None


def test_contradictory_heating_flags_keep_stricter_detected_fact() -> None:
    """Corrupt NOT_SEEN beside DETECTED must degrade locally."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["heating_detected"] = True
    stored["heating_not_seen"] = True
    stored["heating_detector_version"] = 1
    stored["heating_power_threshold_w"] = 1000.0
    stored["heating_confirmation_seconds"] = 30
    stored["heating_observation_seconds"] = 300
    stored["heating_max_source_age_seconds"] = 30

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.heating_detected is True
    assert restored.heating_not_seen is False


def test_last_unloaded_at_round_trip() -> None:
    """Test a recorded unload timestamp survives serialization."""
    unloaded_at = datetime(2026, 7, 15, 9, 30, tzinfo=timezone.utc)
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.IDLE,
        last_transition_reason="marked_unloaded",
        last_state_change=unloaded_at,
        cycle_started_at=None,
        laundry_present=False,
        last_unloaded_at=unloaded_at,
    )

    restored = RuntimeSnapshot.from_storage_dict(
        snapshot.as_storage_dict()
    )

    assert restored == snapshot

@pytest.mark.parametrize(
    "invalid_time",
    [
        "2026-07-14T12:00:00",
        "not-a-timestamp",
        123,
        None,
    ],
)
def test_required_last_state_change_must_be_aware(
    invalid_time: object,
) -> None:
    """Corrupt mandatory timing must fail closed, retaining valid history."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["last_state_change"] = invalid_time
    stored["last_cycle_duration"] = 2400.0
    stored["last_cycle_energy"] = 0.81
    stored["last_cycle_energy_unit"] = "kWh"

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_state_change is None
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 2400.0
    assert restored.last_cycle_energy == 0.81
    assert restored.last_cycle_energy_unit == "kWh"
    assert select_recovery_state(
        restored,
        door_open=False,
        activity_detected=True,
        vibration_active=True,
        now=datetime(2026, 7, 14, 12, 1, tzinfo=timezone.utc),
        power_available=True,
    ) is LaundryCycleState.IDLE
    assert RuntimeSnapshot.from_storage_dict(
        restored.as_storage_dict()
    ).last_state_change is None


@pytest.mark.parametrize(
    "state",
    [LaundryCycleState.RUNNING, LaundryCycleState.FINAL_SPIN],
)
@pytest.mark.parametrize(
    "invalid_time",
    [
        "2026-07-14T11:00:00",
        "not-a-timestamp",
        123,
        None,
    ],
)
def test_invalid_cycle_start_drops_only_active_recovery(
    state: LaundryCycleState,
    invalid_time: object,
) -> None:
    """Keep tracking and history, but do not recover a mistimed cycle."""
    stored = _snapshot(state).as_storage_dict()
    stored["cycle_started_at"] = invalid_time
    stored["last_cycle_duration"] = 2400.0

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_started_at is None
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 2400.0
    assert select_recovery_state(
        restored,
        door_open=False,
        activity_detected=False,
        vibration_active=False,
        now=datetime(2026, 7, 14, 12, 1, tzinfo=timezone.utc),
        max_active_snapshot_age_seconds=86400,
    ) is LaundryCycleState.IDLE


def test_invalid_cycle_start_does_not_discard_completed_statistics() -> None:
    """FINISHED snapshots do not require an active cycle-start timestamp."""
    stored = _snapshot(LaundryCycleState.FINISHED).as_storage_dict()
    stored["cycle_started_at"] = "2026-07-14T11:00:00"
    stored["last_cycle_duration"] = 2400.0

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_state is LaundryCycleState.FINISHED
    assert restored.cycle_started_at is None
    assert restored.last_cycle_duration == 2400.0


@pytest.mark.parametrize(
    "invalid_time",
    ["2026-07-14T11:00:00", "not-a-timestamp", 123, {}],
)
def test_bad_optional_unload_timestamp_degrades_locally(
    invalid_time: object,
) -> None:
    """An invalid unload time must not discard a safe active cycle/history."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["last_unloaded_at"] = invalid_time
    stored["last_cycle_duration"] = 2700.0
    stored["last_cycle_energy"] = 0.9
    stored["last_cycle_energy_unit"] = "kWh"

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_unloaded_at is None
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.last_state_change is not None
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 2700.0
    assert restored.last_cycle_energy == 0.9


def test_timezone_offset_timestamps_remain_valid() -> None:
    """Offset-aware timestamps other than UTC remain supported."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["last_state_change"] = "2026-07-14T15:00:00+03:00"
    stored["cycle_started_at"] = "2026-07-14T14:00:00+03:00"

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_state_change.utcoffset() == timedelta(hours=3)
    assert restored.cycle_started_at is not None
    assert restored.cycle_started_at.utcoffset() == timedelta(hours=3)


@pytest.mark.parametrize(
    "state",
    list(LaundryCycleState),
    ids=_state_test_id,
)
def test_missing_transition_time_forces_idle_even_for_nonactive_states(
    state: LaundryCycleState,
) -> None:
    """Missing timing never revives ARMED, FINISHED, ERROR or a live cycle."""
    stored = _snapshot(state).as_storage_dict()
    stored.pop("last_state_change")
    stored["last_cycle_duration"] = 1234.0

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_state_change is None
    assert restored.last_cycle_duration == 1234.0
    assert select_recovery_state(
        restored,
        door_open=False,
        activity_detected=True,
        vibration_active=True,
        now=datetime(2026, 7, 14, 12, 1, tzinfo=timezone.utc),
        power_available=False,
    ) is LaundryCycleState.IDLE


def test_salvage_independent_unload_history_with_corrupt_core_time() -> None:
    """Independent unload time and statistics survive a broken core clock."""
    stored = _snapshot(LaundryCycleState.FINISHED).as_storage_dict()
    stored["last_state_change"] = "bad-clock"
    stored["last_unloaded_at"] = "2026-07-13T09:30:00+03:00"
    stored["laundry_present"] = True
    stored["last_cycle_duration"] = 3600.0
    stored["last_cycle_energy"] = 0.75

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_state_change is None
    assert restored.last_unloaded_at is not None
    assert restored.last_unloaded_at.utcoffset() == timedelta(hours=3)
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 3600.0
    assert restored.last_cycle_energy == 0.75


@pytest.mark.parametrize("invalid_time", ["bad", "2026-07-14T11:00:00", 123, None])
def test_corrupt_timing_and_unload_do_not_poison_independent_statistics(
    invalid_time: object,
) -> None:
    """Multiple corrupt timestamps still salvage independent valid data."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored["last_state_change"] = invalid_time
    stored["last_unloaded_at"] = invalid_time
    stored["cycle_started_at"] = invalid_time
    stored["last_cycle_duration"] = 1234.5
    stored["last_cycle_energy"] = 0.42

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.last_state_change is None
    assert restored.last_unloaded_at is None
    assert restored.cycle_started_at is None
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 1234.5
    assert restored.last_cycle_energy == 0.42
    assert select_recovery_state(
        restored,
        door_open=False,
        activity_detected=True,
        vibration_active=True,
    ) is LaundryCycleState.IDLE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("laundry_present", "false"),
        ("laundry_present", 1),
        ("laundry_present", None),
        ("last_transition_reason", None),
        ("last_transition_reason", {}),
        ("last_transition_reason", ""),
    ],
)
def test_corrupt_mandatory_identity_fields_still_reject_snapshot(
    field: str,
    value: object,
) -> None:
    """No coercion may manufacture independently trusted history."""
    stored = _snapshot(LaundryCycleState.FINISHED).as_storage_dict()
    stored["last_state_change"] = "invalid"
    stored[field] = value

    assert RuntimeSnapshot.from_storage_dict(stored) is None


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [
        pytest.param(True, None, id="true"),
        pytest.param(False, None, id="false"),
        pytest.param(None, None, id="absent"),
        pytest.param(float("nan"), None, id="nan"),
        pytest.param(float("inf"), None, id="infinity"),
        pytest.param(10**400, None, id="integer-overflow"),
        pytest.param([], None, id="list"),
        pytest.param({}, None, id="object"),
        pytest.param(1000, 1000.0, id="integer"),
        pytest.param(1000.5, 1000.5, id="float"),
        pytest.param("1000.5", 1000.5, id="legacy-numeric-string"),
    ],
)
def test_optional_heating_threshold_types_preserve_independent_context(
    threshold: object, expected: float | None
) -> None:
    """Corrupt numeric fingerprint cannot authorize persisted NOT_SEEN."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored.update(
        heating_not_seen=True,
        heating_detector_version=1,
        heating_power_threshold_w=threshold,
        heating_confirmation_seconds=30,
        heating_observation_seconds=300,
        heating_max_source_age_seconds=30,
        last_cycle_duration=1234.0,
        last_cycle_energy=0.42,
        last_cycle_energy_unit="kWh",
        last_unloaded_at="2026-07-13T10:00:00+03:00",
        spin_evidence_timestamps=["2026-07-14T11:59:00+00:00"],
    )

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.heating_power_threshold_w == expected
    assert restored.heating_not_seen is (expected is not None)
    assert restored.heating_detector_version == 1
    assert restored.heating_confirmation_seconds == 30
    assert restored.heating_observation_seconds == 300
    assert restored.heating_max_source_age_seconds == 30
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.laundry_present is True
    assert restored.last_cycle_duration == 1234.0
    assert restored.last_cycle_energy == 0.42
    assert restored.last_cycle_energy_unit == "kWh"
    assert restored.last_unloaded_at == datetime.fromisoformat(
        "2026-07-13T10:00:00+03:00"
    )
    assert restored.spin_evidence_timestamps == (
        datetime.fromisoformat("2026-07-14T11:59:00+00:00"),
    )


def test_invalid_optional_heating_threshold_retains_detected_fact() -> None:
    """A damaged NOT_SEEN fingerprint cannot erase latched DETECTED."""
    stored = _snapshot(LaundryCycleState.RUNNING).as_storage_dict()
    stored.update(
        heating_detected=True,
        heating_detected_at="2026-07-14T11:20:00+00:00",
        heating_not_seen=True,
        heating_detector_version=1,
        heating_power_threshold_w=True,
        heating_confirmation_seconds=30,
        heating_observation_seconds=300,
        heating_max_source_age_seconds=30,
    )
    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.heating_detected is True
    assert restored.heating_detected_at == datetime.fromisoformat(
        "2026-07-14T11:20:00+00:00"
    )
    assert restored.heating_not_seen is False
    assert restored.heating_power_threshold_w is None
