"""Test persistence of Laundry Monitor cycle statistics."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.laundry_monitor.const import LaundryCycleState
from custom_components.laundry_monitor.storage import RuntimeSnapshot


def test_cycle_statistics_snapshot_round_trip() -> None:
    """Test all completed and active statistics survive serialization."""
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.FINAL_SPIN,
        last_transition_reason="final_spin_confirmed",
        last_state_change=datetime(
            2026,
            7,
            15,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        cycle_started_at=datetime(
            2026,
            7,
            15,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        laundry_present=True,
        cycle_energy_start=125.3,
        cycle_energy_unit="kWh",
        last_cycle_duration=7200.0,
        last_cycle_energy=0.82,
        last_cycle_energy_unit="kWh",
        final_spin_detected=True,
    )

    assert RuntimeSnapshot.from_storage_dict(
        snapshot.as_storage_dict()
    ) == snapshot


def test_snapshot_without_cycle_statistics_is_backward_compatible() -> None:
    """Test snapshots from before Cycle Statistics still load."""
    stored = {
        "cycle_state": "running",
        "last_transition_reason": "power_above_start_threshold",
        "last_state_change": "2026-07-15T12:00:00+00:00",
        "cycle_started_at": "2026-07-15T11:00:00+00:00",
        "laundry_present": True,
    }

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_energy_start is None
    assert restored.cycle_energy_unit is None
    assert restored.last_cycle_duration is None
    assert restored.last_cycle_energy is None
    assert restored.last_cycle_energy_unit is None
    assert restored.final_spin_detected is False


def test_non_finite_cycle_statistics_are_rejected() -> None:
    """Test corrupt numeric statistics cannot enter runtime state."""
    stored = {
        "cycle_state": "finished",
        "last_transition_reason": "finish_confirmed",
        "last_state_change": "2026-07-15T12:00:00+00:00",
        "cycle_started_at": None,
        "laundry_present": True,
        "last_cycle_duration": "nan",
    }

    assert RuntimeSnapshot.from_storage_dict(stored) is None
