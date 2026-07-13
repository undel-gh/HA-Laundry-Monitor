"""Power-based activity detection for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.util import dt as dt_util


@dataclass(frozen=True, slots=True)
class ActivityEvaluation:
    """Result of one activity-detector evaluation."""

    activity_detected: bool
    start_candidate: bool
    activity_changed: bool
    last_activity_changed: bool


@dataclass(slots=True)
class ActivityDetector:
    """Detect meaningful washing-machine activity from power readings.

    This detector does not change the public cycle state. It only evaluates
    power and records whether meaningful activity is currently present.
    """

    start_threshold: float
    activity_threshold: float

    activity_detected: bool = False
    start_candidate: bool = False
    last_activity: datetime | None = None

    def evaluate(
        self,
        power: float | None,
        *,
        now: datetime | None = None,
    ) -> ActivityEvaluation:
        """Evaluate a new power reading."""
        timestamp = now or dt_util.utcnow()
        old_activity = self.activity_detected
        old_last_activity = self.last_activity

        if power is None:
            self.activity_detected = False
            self.start_candidate = False
        else:
            self.activity_detected = power >= self.activity_threshold
            self.start_candidate = power >= self.start_threshold

            if self.activity_detected:
                self.last_activity = timestamp

        return ActivityEvaluation(
            activity_detected=self.activity_detected,
            start_candidate=self.start_candidate,
            activity_changed=old_activity != self.activity_detected,
            last_activity_changed=old_last_activity != self.last_activity,
        )
