"""Test hardened Laundry Monitor state transitions."""

from datetime import datetime, timezone

import pytest

from custom_components.laundry_monitor.const import LaundryCycleState
from custom_components.laundry_monitor.state_machine import (
    ALLOWED_TRANSITIONS,
    LaundryStateMachine,
    TransitionStatus,
)


@pytest.mark.parametrize(
    ("old_state", "new_state"),
    [
        (old_state, new_state)
        for old_state, targets in ALLOWED_TRANSITIONS.items()
        for new_state in targets
    ],
)
def test_all_declared_transitions_are_applied(
    old_state: LaundryCycleState,
    new_state: LaundryCycleState,
) -> None:
    """Test every declared transition."""
    machine = LaundryStateMachine(state=old_state)
    result = machine.transition(
        new_state,
        reason="test",
        now=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
    )

    assert result.status is TransitionStatus.APPLIED
    assert machine.state is new_state


@pytest.mark.parametrize(
    ("old_state", "new_state"),
    [
        (old_state, new_state)
        for old_state in LaundryCycleState
        for new_state in LaundryCycleState
        if new_state is not old_state
        and new_state not in ALLOWED_TRANSITIONS[old_state]
    ],
)
def test_all_undeclared_transitions_are_rejected(
    old_state: LaundryCycleState,
    new_state: LaundryCycleState,
) -> None:
    """Test every path absent from the graph."""
    machine = LaundryStateMachine(state=old_state)
    result = machine.transition(
        new_state,
        reason="illegal",
        now=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
    )

    assert result.status is TransitionStatus.REJECTED
    assert machine.state is old_state


def test_same_state_is_no_change() -> None:
    """Test duplicate transition requests."""
    machine = LaundryStateMachine(state=LaundryCycleState.RUNNING)
    result = machine.transition(
        LaundryCycleState.RUNNING,
        reason="duplicate",
        now=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
    )

    assert result.status is TransitionStatus.NO_CHANGE
    assert machine.state is LaundryCycleState.RUNNING
