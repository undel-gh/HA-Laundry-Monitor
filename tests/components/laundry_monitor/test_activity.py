"""Test the electrical Activity Detector."""

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


def test_current_supplements_activity_but_not_cycle_start() -> None:
    """Test current extends activity without becoming a start source."""
    detector = ActivityDetector(
        start_threshold=10.0,
        activity_threshold=5.0,
        current_activity_threshold=0.1,
    )
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)

    evaluation = detector.evaluate(0.25, 0.35, now=now)

    assert evaluation.activity_detected is True
    assert evaluation.power_activity_detected is False
    assert evaluation.current_activity_detected is True
    assert evaluation.start_candidate is False
    assert detector.last_activity == now
    assert detector.last_current_activity == now
    assert detector.last_power_activity is None


def test_unavailable_current_falls_back_to_power_only() -> None:
    """Test an unavailable optional current source is not zero current."""
    detector = ActivityDetector(
        start_threshold=10.0,
        activity_threshold=5.0,
        current_activity_threshold=0.1,
    )
    active_at = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    unavailable_at = datetime(2026, 7, 17, 12, 1, tzinfo=timezone.utc)

    detector.evaluate(0.25, 0.35, now=active_at)
    evaluation = detector.evaluate(
        0.25,
        None,
        now=unavailable_at,
        power_updated=False,
        current_updated=True,
    )

    assert evaluation.activity_detected is False
    assert evaluation.current_activity_detected is None
    assert detector.last_current_activity == unavailable_at
    assert detector.last_activity == unavailable_at
