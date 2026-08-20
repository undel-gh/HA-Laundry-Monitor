"""Test the standalone Spin Detector."""

from datetime import datetime, timedelta, timezone

from custom_components.laundry_monitor.spin import (
    ElectricalSpinCandidateDetector,
    SpinDetector,
)


def _pulse(
    detector: SpinDetector,
    *,
    now: datetime,
    last_activity: datetime,
    cycle_started_at: datetime,
):
    """Create one OFF -> ON vibration pulse."""
    detector.evaluate(
        vibration_active=False,
        activity_detected=True,
        last_activity=last_activity,
        cycle_started_at=cycle_started_at,
        now=now,
    )
    return detector.evaluate(
        vibration_active=True,
        activity_detected=True,
        last_activity=last_activity,
        cycle_started_at=cycle_started_at,
        now=now,
    )


def test_detects_repeated_vibration_with_context() -> None:
    """Test final-spin detection after enough vibration evidence."""
    detector = SpinDetector(
        required_events=3,
        window_seconds=180,
        min_cycle_seconds=600,
        activity_max_age_seconds=120,
    )
    start = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    now = start + timedelta(minutes=20)

    first = _pulse(
        detector,
        now=now,
        last_activity=now,
        cycle_started_at=start,
    )
    second = _pulse(
        detector,
        now=now + timedelta(seconds=20),
        last_activity=now,
        cycle_started_at=start,
    )
    third = _pulse(
        detector,
        now=now + timedelta(seconds=40),
        last_activity=now,
        cycle_started_at=start,
    )

    assert first.detected is False
    assert second.detected is False
    assert third.detected is True
    assert third.evidence_count == 3
    assert third.confidence == 1.0


def test_single_vibration_event_is_not_enough() -> None:
    """Test protection against an accidental vibration event."""
    detector = SpinDetector(
        required_events=3,
        window_seconds=180,
        min_cycle_seconds=0,
        activity_max_age_seconds=120,
    )
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    result = _pulse(
        detector,
        now=now,
        last_activity=now,
        cycle_started_at=now,
    )

    assert result.detected is False
    assert result.evidence_count == 1


def test_old_vibration_evidence_expires() -> None:
    """Test rolling-window pruning."""
    detector = SpinDetector(
        required_events=2,
        window_seconds=60,
        min_cycle_seconds=0,
        activity_max_age_seconds=120,
    )
    start = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    _pulse(
        detector,
        now=start,
        last_activity=start,
        cycle_started_at=start,
    )
    result = _pulse(
        detector,
        now=start + timedelta(seconds=61),
        last_activity=start + timedelta(seconds=61),
        cycle_started_at=start,
    )

    assert result.detected is False
    assert result.evidence_count == 1


def test_recent_activity_is_required() -> None:
    """Test that vibration alone cannot confirm a final spin."""
    detector = SpinDetector(
        required_events=1,
        window_seconds=180,
        min_cycle_seconds=0,
        activity_max_age_seconds=30,
    )
    now = datetime(2026, 7, 13, 12, 10, tzinfo=timezone.utc)

    detector.evaluate(
        vibration_active=False,
        activity_detected=False,
        last_activity=now - timedelta(minutes=2),
        cycle_started_at=now - timedelta(minutes=10),
        now=now,
    )
    result = detector.evaluate(
        vibration_active=True,
        activity_detected=False,
        last_activity=now - timedelta(minutes=2),
        cycle_started_at=now - timedelta(minutes=10),
        now=now,
    )

    assert result.detected is False
    assert result.activity_recent is False
    assert result.confidence == 0.5


def test_minimum_cycle_time_is_required() -> None:
    """Test protection against vibration near the start of a cycle."""
    detector = SpinDetector(
        required_events=1,
        window_seconds=180,
        min_cycle_seconds=600,
        activity_max_age_seconds=120,
    )
    now = datetime(2026, 7, 13, 12, 5, tzinfo=timezone.utc)

    result = _pulse(
        detector,
        now=now,
        last_activity=now,
        cycle_started_at=now - timedelta(minutes=5),
    )

    assert result.detected is False
    assert result.cycle_mature is False
    assert result.confidence == 0.5


def test_electrical_candidate_requires_configured_power_threshold() -> None:
    """No universal power threshold means no electrical candidate."""
    detector = ElectricalSpinCandidateDetector(
        window_seconds=30,
        min_coverage_seconds=20,
    )
    start = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    detector.reset(now=start, power=150.0)

    result = detector.evaluate(
        power=150.0,
        current=None,
        power_updated=False,
        current_updated=False,
        now=start + timedelta(seconds=30),
    )

    assert result.power_rolling_median == 150.0
    assert result.candidate is False


def test_electrical_candidate_detects_sustained_configured_power() -> None:
    """A configured sustained power signature becomes a candidate."""
    detector = ElectricalSpinCandidateDetector(
        window_seconds=30,
        min_coverage_seconds=20,
        power_threshold_w=100.0,
    )
    start = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    detector.reset(now=start, power=150.0)

    result = detector.evaluate(
        power=150.0,
        current=None,
        power_updated=False,
        current_updated=False,
        now=start + timedelta(seconds=20),
    )

    assert result.candidate is True
    assert result.candidate_since == start + timedelta(seconds=20)
    assert result.power_rolling_median == 150.0


def test_electrical_candidate_uses_time_weighted_median() -> None:
    """Publication frequency cannot dominate the rolling median."""
    detector = ElectricalSpinCandidateDetector(
        window_seconds=30,
        min_coverage_seconds=20,
        power_threshold_w=100.0,
    )
    start = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    detector.reset(now=start, power=20.0)
    detector.evaluate(
        power=150.0,
        current=None,
        power_updated=True,
        current_updated=False,
        now=start + timedelta(seconds=20),
    )
    for seconds in (21, 22, 23, 24, 25):
        detector.evaluate(
            power=150.0,
            current=None,
            power_updated=True,
            current_updated=False,
            now=start + timedelta(seconds=seconds),
        )

    result = detector.evaluate(
        power=150.0,
        current=None,
        power_updated=False,
        current_updated=False,
        now=start + timedelta(seconds=30),
    )

    assert result.power_rolling_median == 20.0
    assert result.candidate is False


def test_current_is_corroborating_only() -> None:
    """Current cannot create an electrical candidate when power is low."""
    detector = ElectricalSpinCandidateDetector(
        window_seconds=30,
        min_coverage_seconds=20,
        power_threshold_w=100.0,
        current_threshold_a=0.7,
    )
    start = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    detector.reset(now=start, power=30.0, current=1.1)

    result = detector.evaluate(
        power=30.0,
        current=1.1,
        power_updated=False,
        current_updated=False,
        now=start + timedelta(seconds=20),
    )

    assert result.candidate is False
    assert result.current_corroborated is True
