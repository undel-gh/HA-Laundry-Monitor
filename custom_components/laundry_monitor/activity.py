"""Electrical activity detection for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.util import dt as dt_util


@dataclass(frozen=True, slots=True)
class ActivityEvaluation:
    """Result of one activity-detector evaluation."""

    activity_detected: bool
    power_activity_detected: bool
    current_activity_detected: bool | None
    start_candidate: bool
    activity_changed: bool
    last_activity_changed: bool


@dataclass(slots=True)
class ActivityDetector:
    """Detect meaningful activity from power and optional current readings.

    Power remains authoritative for cycle-start detection. Current is only a
    supplemental activity source and cannot create a start candidate.
    """

    start_threshold: float
    activity_threshold: float
    current_activity_threshold: float | None = None

    activity_detected: bool = False
    power_activity_detected: bool = False
    current_activity_detected: bool | None = None
    start_candidate: bool = False
    last_activity: datetime | None = None
    last_power_activity: datetime | None = None
    last_current_activity: datetime | None = None

    def evaluate(
        self,
        power: float | None,
        current: float | None = None,
        *,
        now: datetime | None = None,
        power_updated: bool = True,
        current_updated: bool = True,
    ) -> ActivityEvaluation:
        """Evaluate current electrical readings.

        The ``*_updated`` flags identify which source produced this
        evaluation. They keep source-specific timestamps honest when the
        other value is only a cached reading.
        """
        timestamp = now or dt_util.utcnow()
        old_activity = self.activity_detected
        old_last_activity = self.last_activity
        old_power_activity = self.power_activity_detected
        old_current_activity = self.current_activity_detected

        self.power_activity_detected = (
            power is not None and power >= self.activity_threshold
        )
        self.start_candidate = (
            power is not None and power >= self.start_threshold
        )

        if self.current_activity_threshold is None or current is None:
            self.current_activity_detected = None
        else:
            self.current_activity_detected = (
                current >= self.current_activity_threshold
            )

        if power_updated and (
            self.power_activity_detected or old_power_activity
        ):
            self.last_power_activity = timestamp

        if current_updated and (
            self.current_activity_detected is True
            or old_current_activity is True
        ):
            self.last_current_activity = timestamp

        self.activity_detected = (
            self.power_activity_detected
            or self.current_activity_detected is True
        )
        source_activity_times = (
            timestamp_value
            for timestamp_value in (
                self.last_power_activity,
                self.last_current_activity,
            )
            if timestamp_value is not None
        )
        self.last_activity = max(source_activity_times, default=None)

        return ActivityEvaluation(
            activity_detected=self.activity_detected,
            power_activity_detected=self.power_activity_detected,
            current_activity_detected=self.current_activity_detected,
            start_candidate=self.start_candidate,
            activity_changed=old_activity != self.activity_detected,
            last_activity_changed=old_last_activity != self.last_activity,
        )
