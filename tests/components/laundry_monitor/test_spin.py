"""Test the standalone Spin Detector."""

from datetime import datetime, timedelta, timezone

from custom_components.laundry_monitor.spin import SpinDetector


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
