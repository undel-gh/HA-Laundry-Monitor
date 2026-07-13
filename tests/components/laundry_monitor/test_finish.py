"""Test the standalone Finish Detector."""
from datetime import datetime, timedelta, timezone
from custom_components.laundry_monitor.finish import FinishDetector

def test_detects_sustained_quiet_period() -> None:
    detector=FinishDetector(confirmation_seconds=180)
    start=datetime(2026,7,13,12,0,tzinfo=timezone.utc)
    initial=detector.evaluate(activity_detected=False,last_activity=start,vibration_active=False,now=start+timedelta(seconds=60))
    finished=detector.evaluate(activity_detected=False,last_activity=start,vibration_active=False,now=start+timedelta(seconds=181))
    assert not initial.detected
    assert initial.quiet_since == start
    assert initial.remaining_seconds == 120
    assert finished.detected
    assert finished.remaining_seconds == 0

def test_activity_resets_confirmation() -> None:
    detector=FinishDetector(confirmation_seconds=180)
    start=datetime(2026,7,13,12,0,tzinfo=timezone.utc)
    detector.evaluate(activity_detected=False,last_activity=start,vibration_active=False,now=start+timedelta(seconds=100))
    active=detector.evaluate(activity_detected=True,last_activity=start+timedelta(seconds=120),vibration_active=False,now=start+timedelta(seconds=120))
    again=detector.evaluate(activity_detected=False,last_activity=start+timedelta(seconds=120),vibration_active=False,now=start+timedelta(seconds=121))
    assert not active.quiet
    assert active.quiet_since is None
    assert again.quiet_since == start+timedelta(seconds=120)

def test_vibration_resets_confirmation() -> None:
    detector=FinishDetector(confirmation_seconds=30)
    now=datetime(2026,7,13,12,0,tzinfo=timezone.utc)
    detector.evaluate(activity_detected=False,last_activity=now,vibration_active=False,now=now)
    vibration=detector.evaluate(activity_detected=False,last_activity=now,vibration_active=True,now=now+timedelta(seconds=20))
    assert not vibration.quiet
    assert vibration.deadline is None

def test_unknown_vibration_does_not_block_finish() -> None:
    detector=FinishDetector(confirmation_seconds=30)
    now=datetime(2026,7,13,12,0,tzinfo=timezone.utc)
    result=detector.evaluate(activity_detected=False,last_activity=now,vibration_active=None,now=now+timedelta(seconds=31))
    assert result.detected
