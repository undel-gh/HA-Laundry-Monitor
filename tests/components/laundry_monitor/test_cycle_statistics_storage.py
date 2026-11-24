"""Test persistence of Laundry Monitor cycle statistics."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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


def test_non_finite_cycle_statistics_degrade_independently() -> None:
    """One invalid numeric statistic must not discard other history."""
    stored = {
        "cycle_state": "finished",
        "last_transition_reason": "finish_confirmed",
        "last_state_change": "2026-07-15T12:00:00+00:00",
        "cycle_started_at": None,
        "laundry_present": True,
        "last_cycle_duration": "nan",
        "last_cycle_energy": 0.56,
        "last_cycle_energy_unit": "kWh",
    }

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_state is LaundryCycleState.FINISHED
    assert restored.laundry_present is True
    assert restored.last_cycle_duration is None
    assert restored.last_cycle_energy == 0.56
    assert restored.last_cycle_energy_unit == "kWh"


def test_corrupt_active_energy_and_completed_energy_do_not_poison_duration() -> None:
    """Independent energy fields fail locally without losing known duration."""
    stored = {
        "cycle_state": "running",
        "last_transition_reason": "test",
        "last_state_change": "2026-07-15T12:00:00+00:00",
        "cycle_started_at": "2026-07-15T11:00:00+00:00",
        "laundry_present": True,
        "cycle_energy_start": "inf",
        "cycle_energy_unit": "kWh",
        "last_cycle_energy": "invalid",
        "last_cycle_energy_unit": "kWh",
        "last_cycle_duration": 3600.0,
    }

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert restored.cycle_energy_start is None
    assert restored.cycle_energy_unit is None
    assert restored.last_cycle_energy is None
    assert restored.last_cycle_energy_unit is None
    assert restored.last_cycle_duration == 3600.0
    assert restored.cycle_state is LaundryCycleState.RUNNING


def _stored_statistics() -> dict[str, object]:
    """Return independent valid history and active-cycle statistics."""
    return {
        "cycle_state": "running",
        "last_transition_reason": "stored_running",
        "last_state_change": "2026-07-15T12:00:00+00:00",
        "cycle_started_at": "2026-07-15T11:00:00+00:00",
        "laundry_present": True,
        "last_unloaded_at": "2026-07-14T12:00:00+03:00",
        "cycle_energy_start": 125.3,
        "cycle_energy_unit": "kWh",
        "last_cycle_duration": 3600.0,
        "last_cycle_energy": 0.82,
        "last_cycle_energy_unit": "kWh",
    }


@pytest.mark.parametrize("field", ["cycle_energy_unit", "last_cycle_energy_unit"])
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, None, id="absent"),
        pytest.param("", None, id="empty"),
        pytest.param("  \t", None, id="blank"),
        pytest.param("kWh", "kWh", id="canonical"),
        pytest.param(" Wh ", "Wh", id="trimmed"),
        pytest.param("custom-unit", "custom-unit", id="arbitrary-string"),
        pytest.param(123, None, id="integer"),
        pytest.param(1.5, None, id="float"),
        pytest.param(True, None, id="true"),
        pytest.param(False, None, id="false"),
        pytest.param([], None, id="list"),
        pytest.param({"unit": "kWh"}, None, id="object"),
    ],
)
def test_optional_energy_units_require_strings(
    field: str, value: object, expected: str | None
) -> None:
    """Reject non-string units locally while retaining legitimate amounts."""
    stored = _stored_statistics()
    stored[field] = value

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    assert getattr(restored, field) == expected
    other = (
        "last_cycle_energy_unit"
        if field == "cycle_energy_unit"
        else "cycle_energy_unit"
    )
    assert getattr(restored, other) == "kWh"
    assert restored.cycle_energy_start == 125.3
    assert restored.last_cycle_energy == 0.82
    assert restored.last_cycle_duration == 3600.0
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.laundry_present is True
    assert restored.last_unloaded_at == datetime.fromisoformat(
        "2026-07-14T12:00:00+03:00"
    )
    assert RuntimeSnapshot.from_storage_dict(
        restored.as_storage_dict()
    ) == restored


@pytest.mark.parametrize(
    "field", ["cycle_energy_start", "last_cycle_duration", "last_cycle_energy"]
)
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, None, id="absent"),
        pytest.param(True, None, id="true"),
        pytest.param(False, None, id="false"),
        pytest.param(0, 0.0, id="zero"),
        pytest.param(12, 12.0, id="integer"),
        pytest.param(1.25, 1.25, id="float"),
        pytest.param(" 1.25 ", 1.25, id="legacy-string"),
        pytest.param("0", 0.0, id="legacy-zero"),
        pytest.param("1e2", 100.0, id="legacy-exponent"),
        pytest.param(float("nan"), None, id="nan"),
        pytest.param(float("inf"), None, id="inf"),
        pytest.param(float("-inf"), None, id="negative-inf"),
        pytest.param("nan", None, id="string-nan"),
        pytest.param("1e400", None, id="string-overflow"),
        pytest.param(10**400, None, id="integer-overflow"),
        pytest.param("bad", None, id="non-numeric"),
        pytest.param([], None, id="list"),
        pytest.param({}, None, id="object"),
    ],
)
def test_optional_numeric_statistics_degrade_independently(
    field: str, value: object, expected: float | None
) -> None:
    """Reject bools/non-finite values without losing independent history."""
    stored = _stored_statistics()
    stored[field] = value

    restored = RuntimeSnapshot.from_storage_dict(stored)

    assert restored is not None
    actual = getattr(restored, field)
    assert actual == expected
    if expected is not None:
        assert isinstance(actual, float)
    for other in (
        "cycle_energy_start", "last_cycle_duration", "last_cycle_energy"
    ):
        if other != field:
            assert getattr(restored, other) == stored[other]
    assert restored.cycle_energy_unit == (
        None if field == "cycle_energy_start" and expected is None else "kWh"
    )
    assert restored.last_cycle_energy_unit == (
        None if field == "last_cycle_energy" and expected is None else "kWh"
    )
    assert restored.cycle_state is LaundryCycleState.RUNNING
    assert restored.cycle_started_at == datetime.fromisoformat(
        "2026-07-15T11:00:00+00:00"
    )
    assert restored.laundry_present is True
    assert restored.last_unloaded_at == datetime.fromisoformat(
        "2026-07-14T12:00:00+03:00"
    )
    assert RuntimeSnapshot.from_storage_dict(
        restored.as_storage_dict()
    ) == restored
