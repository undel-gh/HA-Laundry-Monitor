"""Test the power-based Activity Detector."""

from datetime import datetime, timezone

from custom_components.laundry_monitor.activity import ActivityDetector


def test_activity_detector_thresholds() -> None:
    """Test activity and start-candidate threshold evaluation."""
    detector = ActivityDetector(
        start_threshold=10.0,
        activity_threshold=5.0,
    )
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    evaluation = detector.evaluate(0.25, now=now)
    assert evaluation.activity_detected is False
    assert evaluation.start_candidate is False
    assert detector.last_activity is None

    evaluation = detector.evaluate(7.5, now=now)
    assert evaluation.activity_detected is True
    assert evaluation.start_candidate is False
    assert detector.last_activity == now

    evaluation = detector.evaluate(20.0, now=now)
    assert evaluation.activity_detected is True
    assert evaluation.start_candidate is True


def test_unknown_power_clears_current_activity() -> None:
    """Test unavailable power without erasing last activity."""
    detector = ActivityDetector(
        start_threshold=10.0,
        activity_threshold=5.0,
    )
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    detector.evaluate(20.0, now=now)
    detector.evaluate(None, now=now)

    assert detector.activity_detected is False
    assert detector.start_candidate is False
    assert detector.last_activity == now
