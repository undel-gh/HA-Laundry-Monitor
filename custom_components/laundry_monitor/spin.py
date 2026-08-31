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


@dataclass(frozen=True, slots=True)
class ElectricalSpinEvaluation:
    """Result of one experimental electrical-spin evaluation."""

    candidate: bool
    candidate_since: datetime | None
    power_rolling_median: float | None
    current_rolling_median: float | None
    current_corroborated: bool | None
    power_source_fresh: bool
    current_source_fresh: bool
    power_coverage_seconds: float
    current_coverage_seconds: float


@dataclass(slots=True)
class ElectricalSpinCandidateDetector:
    """Track an experimental sustained electrical spin signature.

    The detector is independent from the vibration detector. Power is the
    authoritative electrical signal. Optional current is corroborating only.
    A missing power threshold disables the candidate while rolling statistics
    remain available for diagnostics.
    """

    window_seconds: int
    min_coverage_seconds: int
    max_source_age_seconds: int = 30
    power_threshold_w: float | None = None
    current_threshold_a: float | None = None

    candidate: bool = field(default=False, init=False)
    candidate_since: datetime | None = field(default=None, init=False)
    power_rolling_median: float | None = field(default=None, init=False)
    current_rolling_median: float | None = field(default=None, init=False)
    current_corroborated: bool | None = field(default=None, init=False)
    power_source_fresh: bool = field(default=False, init=False)
    current_source_fresh: bool = field(default=False, init=False)
    power_coverage_seconds: float = field(default=0.0, init=False)
    current_coverage_seconds: float = field(default=0.0, init=False)

    _power_samples: deque[tuple[datetime, float]] = field(
        default_factory=deque,
        init=False,
    )
    _current_samples: deque[tuple[datetime, float]] = field(
        default_factory=deque,
        init=False,
    )

    def reset(
        self,
        *,
        now: datetime | None = None,
        power: float | None = None,
        current: float | None = None,
    ) -> None:
        """Reset diagnostics and optionally seed current source values."""
        self._power_samples.clear()
        self._current_samples.clear()
        self.candidate = False
        self.candidate_since = None
        self.power_rolling_median = None
        self.current_rolling_median = None
        self.current_corroborated = None
        self.power_source_fresh = False
        self.current_source_fresh = False
        self.power_coverage_seconds = 0.0
        self.current_coverage_seconds = 0.0

        if now is not None:
            if power is not None:
                self._power_samples.append((now, power))
                self.power_source_fresh = True
            if current is not None:
                self._current_samples.append((now, current))
                self.current_source_fresh = True

    def evaluate(
        self,
        *,
        power: float | None,
        current: float | None,
        power_updated: bool,
        current_updated: bool,
        now: datetime,
    ) -> ElectricalSpinEvaluation:
        """Update source history and calculate the electrical candidate."""
        self._update_samples(
            self._power_samples,
            value=power,
            updated=power_updated,
            now=now,
        )
        self._update_samples(
            self._current_samples,
            value=current,
            updated=current_updated,
            now=now,
        )

        (
            self.power_rolling_median,
            self.power_coverage_seconds,
        ) = self._rolling_median(self._power_samples, now)
        (
            self.current_rolling_median,
            self.current_coverage_seconds,
        ) = self._rolling_median(self._current_samples, now)
        self.power_source_fresh = self._source_is_fresh(
            self._power_samples, now
        )
        self.current_source_fresh = self._source_is_fresh(
            self._current_samples, now
        )

        power_ready = (
            self.power_threshold_w is not None
            and self.power_source_fresh
            and self.power_rolling_median is not None
            and self.power_coverage_seconds >= self.min_coverage_seconds
        )
        new_candidate = bool(
            power_ready
            and self.power_rolling_median >= self.power_threshold_w
        )

        if self.current_threshold_a is None:
            self.current_corroborated = None
        elif (
            not self.current_source_fresh
            or self.current_rolling_median is None
            or self.current_coverage_seconds < self.min_coverage_seconds
        ):
            self.current_corroborated = None
        else:
            self.current_corroborated = (
                self.current_rolling_median >= self.current_threshold_a
            )

        if new_candidate and not self.candidate:
            self.candidate_since = now
        elif not new_candidate:
            self.candidate_since = None
        self.candidate = new_candidate

        return ElectricalSpinEvaluation(
            candidate=self.candidate,
            candidate_since=self.candidate_since,
            power_rolling_median=self.power_rolling_median,
            current_rolling_median=self.current_rolling_median,
            current_corroborated=self.current_corroborated,
            power_source_fresh=self.power_source_fresh,
            current_source_fresh=self.current_source_fresh,
            power_coverage_seconds=self.power_coverage_seconds,
            current_coverage_seconds=self.current_coverage_seconds,
        )

    def _update_samples(
        self,
        samples: deque[tuple[datetime, float]],
        *,
        value: float | None,
        updated: bool,
        now: datetime,
    ) -> None:
        """Record source updates and prune samples that cannot cover the window."""
        if updated:
            if value is None:
                samples.clear()
            elif samples and samples[-1][0] == now:
                samples[-1] = (now, value)
            else:
                # Keep same-value updates too. The median is time-weighted, so
                # publication frequency cannot bias it, while these timestamps
                # are required to prove that the source is still fresh.
                samples.append((now, value))

        cutoff = now - timedelta(seconds=self.window_seconds)
        max_age = timedelta(seconds=self.max_source_age_seconds)
        while len(samples) >= 2:
            first_valid_until = min(
                samples[1][0],
                samples[0][0] + max_age,
            )
            if first_valid_until > cutoff:
                break
             samples.popleft()
        if (
            len(samples) == 1
            and samples[0][0] + max_age <= cutoff
        ):
            samples.clear()

    def _rolling_median(
        self,
        samples: deque[tuple[datetime, float]],
        now: datetime,
    ) -> tuple[float | None, float]:
        """Return a time-weighted rolling median and observed coverage."""
        if not samples:
            return None, 0.0

        cutoff = now - timedelta(seconds=self.window_seconds)
        max_age = timedelta(seconds=self.max_source_age_seconds)
        weighted_values: list[tuple[float, float]] = []

        for index, (sample_time, value) in enumerate(samples):
            start = max(sample_time, cutoff)
            next_update = (
                samples[index + 1][0]
                if index + 1 < len(samples)
                else now
            )
            end = min(
                next_update,
                now,
                sample_time + max_age,
            )
            weight = max((end - start).total_seconds(), 0.0)
            if weight > 0:
                weighted_values.append((value, weight))

        coverage = sum(weight for _, weight in weighted_values)
        if coverage <= 0:
            return None, 0.0

        midpoint = coverage / 2.0
        cumulative = 0.0
        for value, weight in sorted(weighted_values):
            cumulative += weight
            if cumulative >= midpoint:
                return value, coverage

        return weighted_values[-1][0], coverage

    def _source_is_fresh(
        self,
        samples: deque[tuple[datetime, float]],
        now: datetime,
    ) -> bool:
        """Return whether the source has a recent observed update."""
        return bool(
            samples
            and now - samples[-1][0]
            <= timedelta(seconds=self.max_source_age_seconds)
        )
