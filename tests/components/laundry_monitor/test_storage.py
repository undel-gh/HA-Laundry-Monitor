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
            "laundry_present": False,
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

