"""Cycle-finish detection for Laundry Monitor."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass(frozen=True, slots=True)
class FinishEvaluation:
    """Result of one Finish Detector evaluation."""
    detected: bool
    quiet: bool
    quiet_since: datetime | None
    deadline: datetime | None
    remaining_seconds: float | None

@dataclass(slots=True)
class FinishDetector:
    """Confirm that activity and vibration stayed absent long enough."""
    confirmation_seconds: int
    _quiet_since: datetime | None = None

    def reset(self) -> None:
        """Reset pending finish confirmation."""
        self._quiet_since = None

    def evaluate(self, *, activity_detected: bool, last_activity: datetime | None,
                 vibration_active: bool | None, now: datetime) -> FinishEvaluation:
        """Evaluate whether the cycle is finished."""
        quiet = not activity_detected and vibration_active is not True
        if not quiet:
            self._quiet_since = None
            return FinishEvaluation(False, False, None, None, None)
        if self._quiet_since is None:
            self._quiet_since = last_activity if last_activity is not None and last_activity <= now else now
        deadline = self._quiet_since + timedelta(seconds=self.confirmation_seconds)
        remaining = max((deadline-now).total_seconds(),0.0)
        return FinishEvaluation(now >= deadline, True, self._quiet_since, deadline, remaining)
