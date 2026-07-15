"""Test conservative state recovery policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.laundry_monitor.const import LaundryCycleState
from custom_components.laundry_monitor.storage import (
    RuntimeSnapshot,
    select_recovery_state,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _snapshot(
    state: LaundryCycleState,
    *,
    age_seconds: int,
) -> RuntimeSnapshot:
    """Create a snapshot of a known age."""
    return RuntimeSnapshot(
        cycle_state=state,
        last_transition_reason="test",
        last_state_change=NOW - timedelta(seconds=age_seconds),
        cycle_started_at=NOW - timedelta(hours=2),
        laundry_present=state
        in {
            LaundryCycleState.RUNNING,
            LaundryCycleState.FINAL_SPIN,
            LaundryCycleState.FINISHED,
        },
    )


def test_stale_active_snapshot_returns_to_idle() -> None:
    """Test old running context is not restored indefinitely."""
    recovered = select_recovery_state(
        _snapshot(LaundryCycleState.RUNNING, age_seconds=7201),
        door_open=None,
        activity_detected=False,
        vibration_active=None,
        now=NOW,
        max_active_snapshot_age_seconds=7200,
        power_available=True,
    )

    assert recovered is LaundryCycleState.IDLE


def test_final_spin_without_context_recovers_as_running() -> None:
    """Test transient spin evidence is not fabricated after restart."""
    recovered = select_recovery_state(
        _snapshot(LaundryCycleState.FINAL_SPIN, age_seconds=60),
        door_open=None,
        activity_detected=False,
        vibration_active=False,
        now=NOW,
        max_active_snapshot_age_seconds=7200,
        power_available=True,
        require_final_spin_context=True,
    )

    assert recovered is LaundryCycleState.RUNNING


def test_finished_retention_is_applied_during_recovery() -> None:
    """Test disabled tracking cannot restore an expired finished state."""
    recovered = select_recovery_state(
        _snapshot(LaundryCycleState.FINISHED, age_seconds=301),
        door_open=None,
        activity_detected=False,
        vibration_active=None,
        now=NOW,
        tracking_enabled=False,
        finished_retention_seconds=300,
        power_available=True,
    )

    assert recovered is LaundryCycleState.IDLE


def test_error_recovers_when_required_power_is_valid() -> None:
    """Test an obsolete error snapshot does not trap the runtime."""
    recovered = select_recovery_state(
        _snapshot(LaundryCycleState.ERROR, age_seconds=10),
        door_open=None,
        activity_detected=False,
        vibration_active=None,
        now=NOW,
        power_available=True,
    )

    assert recovered is LaundryCycleState.IDLE
