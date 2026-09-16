"""Test heating-aware cycle context."""

from datetime import datetime, timedelta, timezone

from custom_components.laundry_monitor.heating import (
    HeatingContextDetector,
    HeatingState,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _detector(
    *,
    threshold: float | None = 1000.0,
    confirmation: int = 30,
    observation: int = 60,
    max_age: int = 30,
) -> HeatingContextDetector:
    return HeatingContextDetector(
        power_threshold_w=threshold,
        confirmation_seconds=confirmation,
        observation_seconds=observation,
        max_source_age_seconds=max_age,
    )


def test_short_heater_spike_does_not_latch_detected() -> None:
    """A short heater-level interval is not a confirmed heated cycle."""
    detector = _detector(confirmation=30)
    detector.reset(now=NOW, power=1800.0)

    result = detector.evaluate(
        power=100.0,
        power_updated=True,
        now=NOW + timedelta(seconds=10),
    )

    assert result.state is HeatingState.UNKNOWN
    assert result.heating_active is False
    assert result.confirmation_coverage_seconds == 0.0


def test_sustained_heater_load_latches_detected() -> None:
    """FR-048/049: sustained heater-level power latches DETECTED."""
    detector = _detector(confirmation=30)
    detector.reset(now=NOW, power=1800.0)

    result = detector.evaluate(
        power=1800.0,
        power_updated=True,
        now=NOW + timedelta(seconds=30),
    )

    assert result.state is HeatingState.DETECTED
    assert result.heating_active is True
    assert result.detected_at == NOW + timedelta(seconds=30)


def test_not_seen_requires_valid_observation_coverage() -> None:
    """FR-050: wall-clock passage without fresh data is insufficient."""
    detector = _detector(observation=60, max_age=30)
    detector.reset(now=NOW, power=100.0)

    result = detector.evaluate(
        power=100.0,
        power_updated=False,
        now=NOW + timedelta(seconds=60),
    )
    assert result.state is HeatingState.UNKNOWN
    assert result.observation_coverage_seconds == 30.0
    assert result.power_source_fresh is False

    detector.evaluate(
        power=100.0,
        power_updated=True,
        now=NOW + timedelta(seconds=60),
    )
    result = detector.evaluate(
        power=100.0,
        power_updated=False,
        now=NOW + timedelta(seconds=90),
    )

    assert result.state is HeatingState.NOT_SEEN
    assert result.observation_coverage_seconds == 60.0


def test_same_value_updates_extend_observed_coverage() -> None:
    """Real same-value updates refresh source freshness and coverage."""
    detector = _detector(observation=40, max_age=30)
    detector.reset(now=NOW, power=100.0)

    detector.evaluate(
        power=100.0,
        power_updated=True,
        now=NOW + timedelta(seconds=20),
    )
    result = detector.evaluate(
        power=100.0,
        power_updated=True,
        now=NOW + timedelta(seconds=40),
    )

    assert result.state is HeatingState.NOT_SEEN
    assert result.observation_coverage_seconds == 40.0
    assert result.power_source_fresh is True


def test_zero_power_counts_as_real_observation() -> None:
    """FR-050 keeps the existing zero-vs-unavailable semantics."""
    detector = _detector(observation=20)
    detector.reset(now=NOW, power=0.0)

    result = detector.evaluate(
        power=0.0,
        power_updated=False,
        now=NOW + timedelta(seconds=20),
    )

    assert result.state is HeatingState.NOT_SEEN
    assert result.observation_coverage_seconds == 20.0


def test_missing_power_does_not_advance_observation() -> None:
    """Missing power stops no-heating observation coverage."""
    detector = _detector(observation=30)
    detector.reset(now=NOW, power=100.0)

    detector.evaluate(
        power=None,
        power_updated=True,
        now=NOW + timedelta(seconds=10),
    )
    result = detector.evaluate(
        power=None,
        power_updated=False,
        now=NOW + timedelta(seconds=60),
    )

    assert result.state is HeatingState.UNKNOWN
    assert result.observation_coverage_seconds == 10.0
    assert result.power_source_fresh is False


def test_stale_heater_sample_does_not_complete_confirmation() -> None:
    """A stale heater sample cannot be extrapolated into DETECTED."""
    detector = _detector(confirmation=30, max_age=20)
    detector.reset(now=NOW, power=1800.0)

    result = detector.evaluate(
        power=1800.0,
        power_updated=False,
        now=NOW + timedelta(seconds=60),
    )

    assert result.state is HeatingState.UNKNOWN
    assert result.heating_active is False
    assert result.confirmation_coverage_seconds == 0.0


def test_not_seen_can_upgrade_to_detected() -> None:
    """A delayed heater may upgrade NOT_SEEN to DETECTED."""
    detector = _detector(confirmation=20, observation=20)
    detector.reset(now=NOW, power=100.0)
    first = detector.evaluate(
        power=100.0,
        power_updated=True,
        now=NOW + timedelta(seconds=20),
    )
    assert first.state is HeatingState.NOT_SEEN

    detector.evaluate(
        power=1800.0,
        power_updated=True,
        now=NOW + timedelta(seconds=21),
    )
    result = detector.evaluate(
        power=1800.0,
        power_updated=True,
        now=NOW + timedelta(seconds=41),
    )

    assert result.state is HeatingState.DETECTED


def test_missing_threshold_fails_closed_as_unknown() -> None:
    """Without calibration the detector never grants NOT_SEEN privileges."""
    detector = _detector(threshold=None, observation=20)
    detector.reset(now=NOW, power=100.0)

    result = detector.evaluate(
        power=100.0,
        power_updated=False,
        now=NOW + timedelta(seconds=20),
    )

    assert result.observation_coverage_seconds == 20.0
    assert result.state is HeatingState.UNKNOWN
    assert result.heating_active is False


def test_restore_detected_keeps_fact_but_discards_freshness() -> None:
    """FR-055 restores the latched fact but never cached-source freshness."""
    detector = _detector()
    detected_at = NOW - timedelta(minutes=5)

    detector.restore_detected(detected_at)
    result = detector.evaluation

    assert result.state is HeatingState.DETECTED
    assert result.detected_at == detected_at
    assert result.heating_active is False
    assert result.power_source_fresh is False
    assert result.observation_coverage_seconds == 0.0
