"""Final-spin detection for Laundry Monitor."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class SpinEvaluation:
    """Result of one Spin Detector evaluation."""

    detected: bool
    confidence: float
    evidence_count: int
    new_evidence: bool
    activity_recent: bool
    cycle_mature: bool


@dataclass(slots=True)
class SpinDetector:
    """Detect a probable final spin from vibration pulses and activity.

    A binary vibration sensor usually reports short ON pulses rather than a
    useful vibration intensity. The detector therefore counts rising edges
    inside a rolling time window.

    The detector does not modify the public cycle state. It only returns
    evidence and confidence to the runtime/state-machine layer.
    """

    required_events: int
    window_seconds: int
    min_cycle_seconds: int
    activity_max_age_seconds: int

    _evidence: deque[datetime] = field(default_factory=deque, init=False)
    _previous_vibration_active: bool | None = field(default=None, init=False)

    def reset(self, *, vibration_active: bool | None = None) -> None:
        """Reset evidence for a new cycle or an idle state."""
        self._evidence.clear()
        self._previous_vibration_active = vibration_active

    def evaluate(
        self,
        *,
        vibration_active: bool | None,
        activity_detected: bool,
        last_activity: datetime | None,
        cycle_started_at: datetime | None,
        now: datetime,
    ) -> SpinEvaluation:
        """Evaluate current spin evidence."""
        self._prune(now)

        new_evidence = (
            vibration_active is True
            and self._previous_vibration_active is not True
        )
        self._previous_vibration_active = vibration_active

        if new_evidence:
            self._evidence.append(now)
            self._prune(now)

        activity_recent = activity_detected or (
            last_activity is not None
            and now - last_activity
            <= timedelta(seconds=self.activity_max_age_seconds)
        )
        cycle_mature = (
            cycle_started_at is not None
            and now - cycle_started_at
            >= timedelta(seconds=self.min_cycle_seconds)
        )

        evidence_count = len(self._evidence)
        evidence_ratio = min(
            evidence_count / max(self.required_events, 1),
            1.0,
        )

        # Confidence is diagnostic only. It deliberately remains below 1.0
        # until both contextual gates are satisfied.
        context_factor = (
            (0.5 if activity_recent else 0.0)
            + (0.5 if cycle_mature else 0.0)
        )
        confidence = round(evidence_ratio * context_factor, 3)

        detected = (
            activity_recent
            and cycle_mature
            and evidence_count >= self.required_events
        )

        return SpinEvaluation(
            detected=detected,
            confidence=confidence,
            evidence_count=evidence_count,
            new_evidence=new_evidence,
            activity_recent=activity_recent,
            cycle_mature=cycle_mature,
        )

    def _prune(self, now: datetime) -> None:
        """Remove vibration evidence outside the rolling window."""
        cutoff = now - timedelta(seconds=self.window_seconds)
        while self._evidence and self._evidence[0] < cutoff:
            self._evidence.popleft()
