"""Heating-context detection for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class HeatingState(StrEnum):
    """Cycle-local heating context used by hybrid spin gating."""

    UNKNOWN = "unknown"
    NOT_SEEN = "not_seen"
    DETECTED = "detected"


@dataclass(frozen=True, slots=True)
class HeatingEvaluation:
    """Result of one heating-context evaluation."""

    state: HeatingState
    heating_active: bool
    detected_at: datetime | None
    observation_coverage_seconds: float
    confirmation_coverage_seconds: float
    power_source_fresh: bool


@dataclass(slots=True)
class HeatingContextDetector:
    """Track sustained heater operation and reliable no-heating coverage.

    ``DETECTED`` is latched for the cycle. ``NOT_SEEN`` is reached only from
    observed, fresh power coverage; missing or stale telemetry never advances
    that conclusion.
    """

    power_threshold_w: float | None
    confirmation_seconds: int = 30
    observation_seconds: int = 300
    max_source_age_seconds: int = 30

    state: HeatingState = field(default=HeatingState.UNKNOWN, init=False)
    heating_active: bool = field(default=False, init=False)
    detected_at: datetime | None = field(default=None, init=False)
    observation_coverage_seconds: float = field(default=0.0, init=False)
    confirmation_coverage_seconds: float = field(default=0.0, init=False)
    power_source_fresh: bool = field(default=False, init=False)

    _last_power: float | None = field(default=None, init=False)
    _last_power_update_at: datetime | None = field(default=None, init=False)
    _last_evaluated_at: datetime | None = field(default=None, init=False)

    def reset(
        self,
        *,
        now: datetime | None = None,
        power: float | None = None,
    ) -> None:
        """Reset heating context for a new cycle."""
        self.state = HeatingState.UNKNOWN
        self.heating_active = False
        self.detected_at = None
        self.observation_coverage_seconds = 0.0
        self.confirmation_coverage_seconds = 0.0
        self.power_source_fresh = False
        self._last_power = None
        self._last_power_update_at = None
        self._last_evaluated_at = now

        if now is not None and power is not None:
            self._last_power = power
            self._last_power_update_at = now
            self.power_source_fresh = True
            self.heating_active = self._is_heater_level(power)

    def restore_detected(self, detected_at: datetime | None = None) -> None:
        """Restore only the safely persisted latched heating fact."""
        self.reset()
        self.state = HeatingState.DETECTED
        self.detected_at = detected_at

    def evaluate(
        self,
        *,
        power: float | None,
        power_updated: bool,
        now: datetime,
    ) -> HeatingEvaluation:
        """Update observed coverage and return current heating context."""
        self._accrue_previous_sample(now)

        if power_updated:
            if power is None:
                self._last_power = None
                self._last_power_update_at = None
                self.confirmation_coverage_seconds = 0.0
            else:
                self._last_power = power
                self._last_power_update_at = now
                if not self._is_heater_level(power):
                    self.confirmation_coverage_seconds = 0.0

        self._last_evaluated_at = now
        self.power_source_fresh = self._source_is_fresh(now)
        self.heating_active = bool(
            self.power_source_fresh
            and self._last_power is not None
            and self._is_heater_level(self._last_power)
        )

        if (
            self.state is not HeatingState.DETECTED
            and self.confirmation_coverage_seconds >= self.confirmation_seconds
        ):
            self.state = HeatingState.DETECTED
            self.detected_at = now

        if (
            self.state is HeatingState.UNKNOWN
            and self.power_threshold_w is not None
            and not self.heating_active
            and self.observation_coverage_seconds >= self.observation_seconds
        ):
            self.state = HeatingState.NOT_SEEN

        return self.evaluation

    @property
    def evaluation(self) -> HeatingEvaluation:
        """Return current diagnostics without changing detector state."""
        return HeatingEvaluation(
            state=self.state,
            heating_active=self.heating_active,
            detected_at=self.detected_at,
            observation_coverage_seconds=self.observation_coverage_seconds,
            confirmation_coverage_seconds=self.confirmation_coverage_seconds,
            power_source_fresh=self.power_source_fresh,
        )

    def _accrue_previous_sample(self, now: datetime) -> None:
        """Accrue only time supported by a real, non-stale power sample."""
        if (
            self._last_power is None
            or self._last_power_update_at is None
            or self._last_evaluated_at is None
        ):
            return

        valid_until = self._last_power_update_at + timedelta(
            seconds=self.max_source_age_seconds
        )
        start = max(self._last_evaluated_at, self._last_power_update_at)
        end = min(now, valid_until)
        observed_seconds = max((end - start).total_seconds(), 0.0)

        if observed_seconds > 0:
            self.observation_coverage_seconds = min(
                self.observation_coverage_seconds + observed_seconds,
                float(self.observation_seconds),
            )
            if self._is_heater_level(self._last_power):
                self.confirmation_coverage_seconds += observed_seconds
            else:
                self.confirmation_coverage_seconds = 0.0

        if now > valid_until:
            # A freshness gap breaks heater-confirmation continuity.
            self.confirmation_coverage_seconds = 0.0

    def _is_heater_level(self, power: float) -> bool:
        """Return whether power is at or above the configured heater level."""
        return bool(
            self.power_threshold_w is not None
            and power >= self.power_threshold_w
        )

    def _source_is_fresh(self, now: datetime) -> bool:
        """Return whether a real power observation is still fresh."""
        return bool(
            self._last_power is not None
            and self._last_power_update_at is not None
            and now - self._last_power_update_at
            <= timedelta(seconds=self.max_source_age_seconds)
        )
