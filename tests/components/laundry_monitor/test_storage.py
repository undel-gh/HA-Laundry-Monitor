"""Test snapshot validation and recovery policy."""

from datetime import datetime, timezone

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
