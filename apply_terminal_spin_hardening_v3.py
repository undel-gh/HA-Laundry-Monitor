#!/usr/bin/env python3
"""Apply terminal-spin hardening + cycle-continuation changes.

Run from the HA-Laundry-Monitor repository root.

Preview:
    python apply_terminal_spin_hardening.py

Apply:
    python apply_terminal_spin_hardening.py --apply

The script is deliberately strict: every expected source fragment must match
exactly once (or already contain the replacement), otherwise it aborts.
"""

from __future__ import annotations

import argparse
import difflib
import json
import py_compile
import tempfile
from pathlib import Path


def replace_once(text: str, old: str, new: str, *, path: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected exactly one match, got {count}: {old[:120]!r}"
        )
    return text.replace(old, new, 1)


def replace_if_present(text: str, old: str, new: str) -> str:
    if new in text:
        return text
    if old in text:
        return text.replace(old, new, 1)
    return text


def insert_before_one_of(
    text: str,
    anchors: tuple[str, ...],
    addition: str,
    *,
    path: str,
) -> str:
    """Insert before the first unique anchor from a small approved set."""
    matches = [(anchor, text.count(anchor)) for anchor in anchors]
    for anchor, count in matches:
        if count == 1:
            return text.replace(anchor, addition + anchor, 1)
    raise RuntimeError(
        f"{path}: no unique insertion anchor found: {matches!r}"
    )


def insert_before_heading_prefix(
    text: str,
    heading_prefix: str,
    addition: str,
    *,
    path: str,
) -> str:
    """Insert before one uniquely matching Markdown heading prefix."""
    lines = text.splitlines(keepends=True)
    indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith(heading_prefix)
    ]
    if len(indexes) != 1:
        raise RuntimeError(
            f"{path}: expected one heading starting {heading_prefix!r}, "
            f"got {len(indexes)}"
        )
    index = indexes[0]
    lines.insert(index, addition)
    return "".join(lines)


NEW_CONTINUATION = '''"""Cycle-continuation detection after a provisional terminal phase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CycleContinuationEvaluation:
    """Result of one cycle-continuation evaluation."""

    detected: bool
    reason: str | None
    ordinary_activity_coverage_seconds: float
    terminal_evidence_active: bool
    heating_resumed: bool


@dataclass(slots=True)
class CycleContinuationDetector:
    """Detect strong evidence that ordinary program execution continued.

    The detector is intentionally conservative. It does not treat one activity
    edge as proof that ``final_spin`` was wrong because drain, positioning, and
    additional terminal spin activity are normal after terminal confirmation.

    Two signals are currently accepted:

    * renewed heater-level operation is an immediate contradiction;
    * for heated hybrid cycles, a long accumulation of meaningful activity
      while no mature terminal electrical episode is active.

    Coverage is bounded by ``max_observation_gap_seconds`` so a stale cached
    activity state cannot accumulate unlimited continuation evidence.
    """

    confirmation_seconds: int
    max_observation_gap_seconds: int

    ordinary_activity_coverage_seconds: float = field(default=0.0, init=False)
    _last_evaluated_at: datetime | None = field(default=None, init=False)
    _previous_ordinary_activity: bool = field(default=False, init=False)

    def reset(self, *, now: datetime | None = None) -> None:
        """Reset continuation evidence."""
        self.ordinary_activity_coverage_seconds = 0.0
        self._last_evaluated_at = now
        self._previous_ordinary_activity = False

    def evaluate(
        self,
        *,
        activity_detected: bool,
        terminal_evidence_active: bool,
        heating_active: bool,
        now: datetime,
    ) -> CycleContinuationEvaluation:
        """Evaluate whether continuation evidence is strong enough."""
        if (
            self._last_evaluated_at is not None
            and now < self._last_evaluated_at
        ):
            self.reset(now=now)

        if heating_active:
            self._last_evaluated_at = now
            self._previous_ordinary_activity = False
            return CycleContinuationEvaluation(
                detected=True,
                reason="heating_resumed_after_final_spin",
                ordinary_activity_coverage_seconds=(
                    self.ordinary_activity_coverage_seconds
                ),
                terminal_evidence_active=terminal_evidence_active,
                heating_resumed=True,
            )

        if terminal_evidence_active:
            # A mature electrical spin episode re-validates the terminal-phase
            # hypothesis, so previously accumulated contradictory activity
            # cannot leak across it.
            self.ordinary_activity_coverage_seconds = 0.0
            self._last_evaluated_at = now
            self._previous_ordinary_activity = False
            return CycleContinuationEvaluation(
                detected=False,
                reason=None,
                ordinary_activity_coverage_seconds=0.0,
                terminal_evidence_active=True,
                heating_resumed=False,
            )

        if (
            self._last_evaluated_at is not None
            and self._previous_ordinary_activity
        ):
            elapsed = max(
                (now - self._last_evaluated_at).total_seconds(),
                0.0,
            )
            self.ordinary_activity_coverage_seconds += min(
                elapsed,
                float(self.max_observation_gap_seconds),
            )

        ordinary_activity = activity_detected
        self._last_evaluated_at = now
        self._previous_ordinary_activity = ordinary_activity

        detected = (
            self.ordinary_activity_coverage_seconds
            >= float(self.confirmation_seconds)
        )
        return CycleContinuationEvaluation(
            detected=detected,
            reason=(
                "prolonged_non_terminal_activity"
                if detected
                else None
            ),
            ordinary_activity_coverage_seconds=(
                self.ordinary_activity_coverage_seconds
            ),
            terminal_evidence_active=False,
            heating_resumed=False,
        )
'''


NEW_CONTINUATION_TESTS = '''"""Tests for cycle-continuation detection."""

from datetime import datetime, timedelta, timezone

from custom_components.laundry_monitor.continuation import (
    CycleContinuationDetector,
)


def _utc() -> datetime:
    return datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_heating_resume_confirms_continuation_immediately() -> None:
    detector = CycleContinuationDetector(
        confirmation_seconds=600,
        max_observation_gap_seconds=30,
    )
    now = _utc()
    detector.reset(now=now)

    evaluation = detector.evaluate(
        activity_detected=True,
        terminal_evidence_active=False,
        heating_active=True,
        now=now + timedelta(seconds=1),
    )

    assert evaluation.detected is True
    assert evaluation.reason == "heating_resumed_after_final_spin"
    assert evaluation.heating_resumed is True


def test_prolonged_non_terminal_activity_accumulates_bounded_coverage() -> None:
    detector = CycleContinuationDetector(
        confirmation_seconds=600,
        max_observation_gap_seconds=30,
    )
    start = _utc()
    detector.reset(now=start)

    detector.evaluate(
        activity_detected=True,
        terminal_evidence_active=False,
        heating_active=False,
        now=start,
    )

    evaluation = None
    for step in range(1, 21):
        evaluation = detector.evaluate(
            activity_detected=True,
            terminal_evidence_active=False,
            heating_active=False,
            now=start + timedelta(seconds=30 * step),
        )

    assert evaluation is not None
    assert evaluation.detected is True
    assert evaluation.reason == "prolonged_non_terminal_activity"
    assert evaluation.ordinary_activity_coverage_seconds == 600.0


def test_mature_terminal_evidence_resets_continuation_coverage() -> None:
    detector = CycleContinuationDetector(
        confirmation_seconds=600,
        max_observation_gap_seconds=30,
    )
    start = _utc()
    detector.reset(now=start)

    detector.evaluate(
        activity_detected=True,
        terminal_evidence_active=False,
        heating_active=False,
        now=start,
    )
    for step in range(1, 11):
        detector.evaluate(
            activity_detected=True,
            terminal_evidence_active=False,
            heating_active=False,
            now=start + timedelta(seconds=30 * step),
        )

    assert detector.ordinary_activity_coverage_seconds == 300.0

    evaluation = detector.evaluate(
        activity_detected=True,
        terminal_evidence_active=True,
        heating_active=False,
        now=start + timedelta(seconds=330),
    )

    assert evaluation.detected is False
    assert evaluation.ordinary_activity_coverage_seconds == 0.0


def test_large_observation_gap_cannot_fabricate_coverage() -> None:
    detector = CycleContinuationDetector(
        confirmation_seconds=600,
        max_observation_gap_seconds=30,
    )
    start = _utc()
    detector.reset(now=start)

    detector.evaluate(
        activity_detected=True,
        terminal_evidence_active=False,
        heating_active=False,
        now=start,
    )
    evaluation = detector.evaluate(
        activity_detected=True,
        terminal_evidence_active=False,
        heating_active=False,
        now=start + timedelta(minutes=10),
    )

    assert evaluation.detected is False
    assert evaluation.ordinary_activity_coverage_seconds == 30.0
'''


def transform_const(text: str) -> str:
    path = "custom_components/laundry_monitor/const.py"
    text = replace_once(
        text,
        'DEFAULT_HYBRID_SPIN_REQUIRED_EVENTS: Final = 2\n'
        'DEFAULT_FINISH_CONFIRMATION: Final = 180',
        'DEFAULT_HYBRID_SPIN_REQUIRED_EVENTS: Final = 2\n'
        '# Experimental terminal-profile hardening. These remain internal while\n'
        '# cross-machine field validation is still in progress.\n'
        'HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION: Final = 45\n'
        'CYCLE_CONTINUATION_ACTIVITY_CONFIRMATION: Final = 600\n'
        'DEFAULT_FINISH_CONFIRMATION: Final = 180',
        path=path,
    )
    text = replace_once(
        text,
        'REASON_FINAL_SPIN_CONFIRMED: Final = "final_spin_confirmed"\n'
        'REASON_FINISH_INACTIVITY_CONFIRMED',
        'REASON_FINAL_SPIN_CONFIRMED: Final = "final_spin_confirmed"\n'
        'REASON_CYCLE_CONTINUATION_CONFIRMED: Final = (\n'
        '    "cycle_continuation_confirmed"\n'
        ')\n'
        'REASON_FINISH_INACTIVITY_CONFIRMED',
        path=path,
    )
    return text


def transform_spin(text: str) -> str:
    path = "custom_components/laundry_monitor/spin.py"
    text = replace_once(
        text,
        '    new_evidence: bool\n'
        '    activity_recent: bool\n'
        '    cycle_mature: bool',
        '    new_evidence: bool\n'
        '    latest_evidence_at: datetime | None\n'
        '    activity_recent: bool\n'
        '    cycle_mature: bool',
        path=path,
    )
    text = replace_once(
        text,
        '            evidence_count=evidence_count,\n'
        '            new_evidence=new_evidence,\n'
        '            activity_recent=activity_recent,',
        '            evidence_count=evidence_count,\n'
        '            new_evidence=new_evidence,\n'
        '            latest_evidence_at=(\n'
        '                self._evidence[-1] if self._evidence else None\n'
        '            ),\n'
        '            activity_recent=activity_recent,',
        path=path,
    )
    text = replace_once(
        text,
        '    def _prune(self, now: datetime) -> None:\n',
        '    @property\n'
        '    def latest_evidence_at(self) -> datetime | None:\n'
        '        """Return the newest currently retained vibration edge."""\n'
        '        return self._evidence[-1] if self._evidence else None\n\n'
        '    def _prune(self, now: datetime) -> None:\n',
        path=path,
    )
    return text


def transform_runtime(text: str) -> str:
    path = "custom_components/laundry_monitor/runtime.py"
    text = replace_once(text, 'from .activity import ActivityDetector\nfrom .const import (', 'from .activity import ActivityDetector\nfrom .continuation import CycleContinuationDetector\nfrom .const import (', path=path)
    text = replace_once(text, '    CONF_VIBRATION_SENSOR,\n    DEFAULT_ACTIVITY_THRESHOLD,', '    CONF_VIBRATION_SENSOR,\n    CYCLE_CONTINUATION_ACTIVITY_CONFIRMATION,\n    DEFAULT_ACTIVITY_THRESHOLD,', path=path)
    text = replace_once(text, '    EVENT_TRANSITION_REJECTED,\n    LaundryCycleState,', '    EVENT_TRANSITION_REJECTED,\n    HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION,\n    LaundryCycleState,', path=path)
    text = replace_once(text, '    REASON_FINAL_SPIN_CONFIRMED,\n    REASON_FINISHED_RETENTION_EXPIRED,', '    REASON_FINAL_SPIN_CONFIRMED,\n    REASON_CYCLE_CONTINUATION_CONFIRMED,\n    REASON_FINISHED_RETENTION_EXPIRED,', path=path)
    text = replace_once(text, '    spin_gate_reason: str | None = None\n    finish_quiet_since: datetime | None = None', '    spin_gate_reason: str | None = None\n    final_spin_confirmation_count: int = 0\n    last_final_spin_revoked_at: datetime | None = None\n    cycle_continuation_reason: str | None = None\n    finish_quiet_since: datetime | None = None', path=path)
    text = replace_once(text, '    heating_detector: HeatingContextDetector = field(init=False)\n    finish_detector: FinishDetector = field(init=False)', '    heating_detector: HeatingContextDetector = field(init=False)\n    cycle_continuation_detector: CycleContinuationDetector = field(\n        init=False\n    )\n    finish_detector: FinishDetector = field(init=False)', path=path)
    text = replace_once(text, '        self.finish_detector = FinishDetector(\n            confirmation_seconds=int(', '        self.cycle_continuation_detector = CycleContinuationDetector(\n            confirmation_seconds=(\n                CYCLE_CONTINUATION_ACTIVITY_CONFIRMATION\n            ),\n            max_observation_gap_seconds=int(\n                self.entry.options.get(\n                    CONF_ELECTRICAL_SPIN_MAX_SOURCE_AGE,\n                    DEFAULT_ELECTRICAL_SPIN_MAX_SOURCE_AGE,\n                )\n            ),\n        )\n        self.finish_detector = FinishDetector(\n            confirmation_seconds=int(', path=path)
    text = replace_once(text, '    @property\n    def current_cycle_duration(self) -> float | None:\n', '    @property\n    def spin_electrical_candidate_age_seconds(self) -> float | None:\n        """Return how long the current electrical candidate has lived."""\n        if (\n            not self.spin_electrical_candidate\n            or self.spin_electrical_candidate_since is None\n        ):\n            return None\n        return round(\n            max(\n                (\n                    dt_util.utcnow()\n                    - self.spin_electrical_candidate_since\n                ).total_seconds(),\n                0.0,\n            ),\n            1,\n        )\n\n    @property\n    def heated_electrical_candidate_min_duration_seconds(self) -> int:\n        """Return the heated-cycle electrical maturity requirement."""\n        return HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n\n    @property\n    def cycle_continuation_confirmation_seconds(self) -> int:\n        """Return required contradictory activity coverage."""\n        return self.cycle_continuation_detector.confirmation_seconds\n\n    def _heated_electrical_candidate_is_mature(\n        self,\n        now: datetime,\n    ) -> bool:\n        """Return whether the current candidate survived the maturity gate."""\n        since = self.spin_electrical_candidate_since\n        return bool(\n            self.spin_electrical_candidate\n            and since is not None\n            and now - since\n            >= timedelta(\n                seconds=HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n            )\n        )\n\n    @property\n    def current_cycle_duration(self) -> float | None:\n', path=path)
    text = replace_once(text, '        self.final_spin_confirmation_path = None\n        self.final_spin_hybrid_variant = None\n        self.spin_gate_reason = None\n        self._reset_finish_detection()', '        self.final_spin_confirmation_path = None\n        self.final_spin_hybrid_variant = None\n        self.spin_gate_reason = None\n        self.final_spin_confirmation_count = 0\n        self.last_final_spin_revoked_at = None\n        self.cycle_continuation_reason = None\n        self.cycle_continuation_detector.reset(now=now)\n        self._reset_finish_detection()', path=path)
    text = replace_once(text, '            self._evaluate_heating_context()\n            self._evaluate_electrical_spin_candidate()\n            self._evaluate_finish()', '            self._evaluate_heating_context()\n            self._evaluate_electrical_spin_candidate()\n            if not self._evaluate_cycle_continuation():\n                self._evaluate_finish()', path=path)
    text = replace_once(text, '            spin_transitioned = self._evaluate_spin(now=now)\n            if not spin_transitioned:\n                self._evaluate_finish()', '            spin_transitioned = self._evaluate_spin(now=now)\n            continuation_transitioned = False\n            if not spin_transitioned:\n                continuation_transitioned = (\n                    self._evaluate_cycle_continuation(now=now)\n                )\n            if not spin_transitioned and not continuation_transitioned:\n                self._evaluate_finish()', path=path)
    text = replace_once(text, '        if new_state is LaundryCycleState.RUNNING:\n            self._cancel_pending_start_confirmation()\n            if old_state is not LaundryCycleState.FINAL_SPIN:\n                self._initialize_cycle_statistics()\n            self.final_spin_confidence = 0.0', '        if new_state is LaundryCycleState.RUNNING:\n            self._cancel_pending_start_confirmation()\n            if old_state is not LaundryCycleState.FINAL_SPIN:\n                self._initialize_cycle_statistics()\n                self.final_spin_confirmation_count = 0\n                self.last_final_spin_revoked_at = None\n                self.cycle_continuation_reason = None\n            else:\n                self.last_final_spin_revoked_at = self.last_state_change\n            self.final_spin_confidence = 0.0', path=path)
    text = replace_once(text, '            self.electrical_spin_detector.reset(\n                now=dt_util.utcnow(),\n                power=self.power,\n                current=self.current,\n            )\n            self._reset_finish_detection()', '            self.electrical_spin_detector.reset(\n                now=dt_util.utcnow(),\n                power=self.power,\n                current=self.current,\n            )\n            self.cycle_continuation_detector.reset(\n                now=self.last_state_change\n            )\n            self._reset_finish_detection()', path=path)
    text = replace_once(text, '        if new_state is LaundryCycleState.FINAL_SPIN:\n            self.final_spin_detected = True\n            self._reset_finish_detection()', '        if new_state is LaundryCycleState.FINAL_SPIN:\n            self.final_spin_detected = True\n            self.final_spin_confirmation_count += 1\n            self.cycle_continuation_detector.reset(\n                now=self.last_state_change\n            )\n            self._reset_finish_detection()', path=path)
    text = replace_once(text, '            self.heating_detector.reset()\n            self._reset_finish_detection()\n            if not self.tracking_enabled:', '            self.heating_detector.reset()\n            self.cycle_continuation_detector.reset()\n            self.cycle_continuation_reason = None\n            self.last_final_spin_revoked_at = None\n            self.final_spin_confirmation_count = 0\n            self._reset_finish_detection()\n            if not self.tracking_enabled:', path=path)
    text = replace_once(text, '            self.electrical_spin_detector.reset()\n            self._reset_finish_detection()\n            self._schedule_finished_retention()', '            self.electrical_spin_detector.reset()\n            self.cycle_continuation_detector.reset()\n            self._reset_finish_detection()\n            self._schedule_finished_retention()', path=path)
    text = replace_once(text, '        if new_state is LaundryCycleState.ERROR:\n            self._cancel_pending_start_confirmation()\n            self._cancel_cycle_statistics_updates()\n            self._cancel_pending_arming_timeout()\n            self._cancel_pending_finished_retention()\n            self._reset_finish_detection()\n            self.spin_detector.reset(vibration_active=self.vibration_active)\n            self.electrical_spin_detector.reset()\n            self.heating_detector.reset()', '        if new_state is LaundryCycleState.ERROR:\n            self._cancel_pending_start_confirmation()\n            self._cancel_cycle_statistics_updates()\n            self._cancel_pending_arming_timeout()\n            self._cancel_pending_finished_retention()\n            self._reset_finish_detection()\n            self.spin_detector.reset(vibration_active=self.vibration_active)\n            self.electrical_spin_detector.reset()\n            self.heating_detector.reset()\n            self.cycle_continuation_detector.reset()', path=path)
    text = replace_once(text, '        self.final_spin_detected = False\n        # Do not seed from a cached state here.', '        self.final_spin_detected = False\n        self.final_spin_confirmation_count = 0\n        self.last_final_spin_revoked_at = None\n        self.cycle_continuation_reason = None\n        self.cycle_continuation_detector.reset(\n            now=self.last_state_change\n        )\n        # Do not seed from a cached state here.', path=path)
    text = replace_once(text, '            self._evaluate_heating_context(now=_now)\n            self._evaluate_electrical_spin_candidate(now=_now)\n            if not self._evaluate_spin(now=_now):\n                self._notify_entities()', '            self._evaluate_heating_context(now=_now)\n            self._evaluate_electrical_spin_candidate(now=_now)\n            spin_transitioned = self._evaluate_spin(now=_now)\n            continuation_transitioned = False\n            if not spin_transitioned:\n                continuation_transitioned = (\n                    self._evaluate_cycle_continuation(now=_now)\n                )\n            if not spin_transitioned and not continuation_transitioned:\n                self._notify_entities()', path=path)
    text = replace_once(text, '                if cycle_age < effective_min:\n                    gate_reason = "heated_cycle_too_young"\n                else:\n                    confirmation_path = "hybrid"\n                    hybrid_variant = "reduced"\n                    gate_reason = "confirmed_hybrid_reduced"', '                if cycle_age < effective_min:\n                    gate_reason = "heated_cycle_too_young"\n                elif not self._heated_electrical_candidate_is_mature(\n                    timestamp\n                ):\n                    gate_reason = "heated_electrical_candidate_immature"\n                elif (\n                    self.spin_electrical_candidate_since is None\n                    or evaluation.latest_evidence_at is None\n                    or evaluation.latest_evidence_at\n                    < self.spin_electrical_candidate_since\n                ):\n                    gate_reason = (\n                        "heated_cycle_requires_fresh_vibration_"\n                        "after_electrical_candidate"\n                    )\n                else:\n                    confirmation_path = "hybrid"\n                    hybrid_variant = "reduced"\n                    gate_reason = "confirmed_hybrid_reduced"', path=path)
    text = replace_once(text, '                    "electrical_candidate": self.spin_electrical_candidate,\n                    "power_rolling_median": self.spin_power_rolling_median,', '                    "electrical_candidate": self.spin_electrical_candidate,\n                    "electrical_candidate_since": (\n                        self.spin_electrical_candidate_since.isoformat()\n                        if self.spin_electrical_candidate_since is not None\n                        else None\n                    ),\n                    "electrical_candidate_age_seconds": (\n                        self.spin_electrical_candidate_age_seconds\n                    ),\n                    "heated_candidate_min_duration_seconds": (\n                        self.heated_electrical_candidate_min_duration_seconds\n                    ),\n                    "latest_vibration_evidence_at": (\n                        evaluation.latest_evidence_at.isoformat()\n                        if evaluation.latest_evidence_at is not None\n                        else None\n                    ),\n                    "power_rolling_median": self.spin_power_rolling_median,', path=path)

    continuation_method = '''    @callback
    def _evaluate_cycle_continuation(
        self,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Return final_spin to running only after strong contradictory evidence."""
        if self.cycle_state is not LaundryCycleState.FINAL_SPIN:
            return False

        timestamp = now or dt_util.utcnow()
        heating_resumed = bool(
            self.heating_detector.heating_active
            and self.heating_detector.confirmation_coverage_seconds
            >= self.heating_detector.confirmation_seconds
        )
        prolonged_detection_enabled = (
            self.hybrid_spin_enabled
            and self.heating_state is HeatingState.DETECTED
        )

        if not heating_resumed and not prolonged_detection_enabled:
            return False

        continuation_activity_observed = bool(
            (
                self.power_activity_detected
                and self.electrical_spin_detector.power_source_fresh
            )
            or (
                self.current_activity_detected is True
                and self.electrical_spin_detector.current_source_fresh
            )
        )
        evaluation = self.cycle_continuation_detector.evaluate(
            activity_detected=continuation_activity_observed,
            terminal_evidence_active=(
                self._heated_electrical_candidate_is_mature(timestamp)
            ),
            heating_active=heating_resumed,
            now=timestamp,
        )

        if not evaluation.detected:
            return False

        self.cycle_continuation_reason = evaluation.reason
        _LOGGER.debug(
            "Cycle continuation confirmed for entry %s (%s): "
            "reason=%s, ordinary_activity_coverage=%.1fs",
            self.entry.entry_id,
            self.name,
            evaluation.reason,
            evaluation.ordinary_activity_coverage_seconds,
        )
        self._cancel_pending_finish_confirmation(
            "cycle continuation confirmed"
        )
        if not self.async_set_cycle_state(
            LaundryCycleState.RUNNING,
            REASON_CYCLE_CONTINUATION_CONFIRMED,
        ):
            return False

        return True

'''
    text = replace_once(text, '    def _active_finish_detector(self) -> FinishDetector | None:\n', continuation_method + '    def _active_finish_detector(self) -> FinishDetector | None:\n', path=path)
    return text


def transform_diagnostics(text: str) -> str:
    path = "custom_components/laundry_monitor/diagnostics.py"
    text = replace_once(text, '                "evidence_count": (\n                    runtime.final_spin_evidence_count\n                ),\n                "confirmation_path": runtime.final_spin_confirmation_path,', '                "evidence_count": (\n                    runtime.final_spin_evidence_count\n                ),\n                "latest_vibration_evidence_at": _serialize_datetime(\n                    runtime.spin_detector.latest_evidence_at\n                ),\n                "confirmation_path": runtime.final_spin_confirmation_path,', path=path)
    text = replace_once(text, '                    "candidate_since": _serialize_datetime(\n                        runtime.spin_electrical_candidate_since\n                    ),\n                    "window_seconds": (', '                    "candidate_since": _serialize_datetime(\n                        runtime.spin_electrical_candidate_since\n                    ),\n                    "candidate_age_seconds": (\n                        runtime.spin_electrical_candidate_age_seconds\n                    ),\n                    "heated_min_duration_seconds": (\n                        runtime.heated_electrical_candidate_min_duration_seconds\n                    ),\n                    "window_seconds": (', path=path)
    text = replace_once(text, '                },\n            },\n            "finish": {', '                },\n                "continuation": {\n                    "confirmation_seconds": (\n                        runtime.cycle_continuation_confirmation_seconds\n                    ),\n                    "ordinary_activity_coverage_seconds": (\n                        runtime.cycle_continuation_detector\n                        .ordinary_activity_coverage_seconds\n                    ),\n                    "last_reason": runtime.cycle_continuation_reason,\n                    "last_final_spin_revoked_at": _serialize_datetime(\n                        runtime.last_final_spin_revoked_at\n                    ),\n                    "final_spin_confirmation_count": (\n                        runtime.final_spin_confirmation_count\n                    ),\n                },\n            },\n            "finish": {', path=path)
    return text


def transform_test_diagnostics(text: str) -> str:
    return replace_if_present(text, '    device = dr.async_get(hass).async_get_device(\n        identifiers={(DOMAIN, entry.entry_id)}\n    )', '    device_registry = dr.async_get(hass)\n    device = device_registry.async_get_device_by_identifier(\n        (DOMAIN, entry.entry_id),\n        entry.entry_id,\n    )')


def transform_ru_json(text: str) -> str:
    return replace_if_present(text, '          "": "Минимальное время цикла до финального отжима",', '          "spin_min_cycle_time": "Минимальное время цикла до финального отжима",')


def transform_spin_runtime_tests(text: str) -> str:
    path = "tests/components/laundry_monitor/test_spin_runtime.py"
    text = replace_once(text, '    DOMAIN,\n    LaundryCycleState,\n    REASON_FINAL_SPIN_CONFIRMED,', '    DOMAIN,\n    HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION,\n    LaundryCycleState,\n    REASON_CYCLE_CONTINUATION_CONFIRMED,\n    REASON_FINAL_SPIN_CONFIRMED,', path=path)
    text = replace_once(text, '    await _vibration_pulse(hass)\n    await _vibration_pulse(hass)\n\n    assert runtime.cycle_state is LaundryCycleState.RUNNING\n    assert runtime.spin_gate_reason == "heated_cycle_too_young"\n\n    runtime.cycle_started_at = dt_util.utcnow() - timedelta(minutes=16)\n    assert runtime._evaluate_spin()\n', '    assert runtime.spin_electrical_candidate is True\n    runtime.electrical_spin_detector.candidate_since = (\n        dt_util.utcnow()\n        - timedelta(\n            seconds=HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n        )\n    )\n    await _vibration_pulse(hass)\n    await _vibration_pulse(hass)\n\n    assert runtime.cycle_state is LaundryCycleState.RUNNING\n    assert runtime.spin_gate_reason == "heated_cycle_too_young"\n\n    runtime.cycle_started_at = dt_util.utcnow() - timedelta(minutes=16)\n    assert runtime._evaluate_spin()\n', path=path)
    text = replace_once(text, '    assert runtime.spin_electrical_candidate is True\n    assert runtime._evaluate_spin(now=candidate_now)\n    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN\n    assert runtime.final_spin_confirmation_path == "hybrid"\n    assert runtime.final_spin_hybrid_variant == "reduced"\n', '    assert runtime.spin_electrical_candidate is True\n    assert not runtime._evaluate_spin(now=candidate_now)\n    assert runtime.spin_gate_reason == "heated_electrical_candidate_immature"\n\n    mature_now = candidate_now + timedelta(\n        seconds=HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n    )\n    assert not runtime._evaluate_spin(now=mature_now)\n    assert runtime.spin_gate_reason == (\n        "heated_cycle_requires_fresh_vibration_after_electrical_candidate"\n    )\n\n    runtime.vibration_active = True\n    assert runtime._evaluate_spin(now=mature_now + timedelta(seconds=1))\n    runtime.vibration_active = False\n\n    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN\n    assert runtime.final_spin_confirmation_path == "hybrid"\n    assert runtime.final_spin_hybrid_variant == "reduced"\n', path=path)
    new_test = '''\n\nasync def test_heated_false_terminal_can_be_revoked_after_strong_continuation(\n    hass: HomeAssistant,\n    enable_custom_integrations: None,\n) -> None:\n    """FR-061: prolonged non-terminal activity can revoke heated final_spin."""\n    entry = await _setup_entry(\n        hass,\n        hybrid_enabled=True,\n        electrical_power_threshold=100.0,\n        heating_power_threshold=1000.0,\n        spin_min_cycle_time=0,\n        heated_cycle_min_time=0,\n    )\n    runtime = entry.runtime_data\n    runtime.heating_detector.restore_detected(\n        dt_util.utcnow() - timedelta(minutes=20)\n    )\n    runtime.final_spin_confirmation_path = "hybrid"\n\n    assert runtime.async_set_cycle_state(\n        LaundryCycleState.FINAL_SPIN,\n        "test_false_terminal",\n    )\n    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN\n\n    start = dt_util.utcnow()\n    runtime.cycle_continuation_detector.reset(now=start)\n    runtime.electrical_spin_detector.reset()\n    # Simulate fresh power observations during the continued program.\n    runtime.electrical_spin_detector.power_source_fresh = True\n\n    assert not runtime._evaluate_cycle_continuation(now=start)\n    transitioned = False\n    for step in range(1, 21):\n        transitioned = runtime._evaluate_cycle_continuation(\n            now=start + timedelta(seconds=30 * step)\n        )\n\n    assert transitioned is True\n    assert runtime.cycle_state is LaundryCycleState.RUNNING\n    assert runtime.last_transition_reason == REASON_CYCLE_CONTINUATION_CONFIRMED\n    assert runtime.cycle_continuation_reason == (\n        "prolonged_non_terminal_activity"\n    )\n    assert runtime.last_final_spin_revoked_at is not None\n    assert runtime.final_spin_confirmation_count == 1\n    assert runtime.final_spin_evidence_count == 0\n    assert runtime.final_spin_confirmation_path is None\n\n\nasync def test_stale_activity_cannot_confirm_cycle_continuation(\n    hass: HomeAssistant,\n    enable_custom_integrations: None,\n) -> None:\n    """FR-061: stale cached activity cannot accumulate continuation proof."""\n    entry = await _setup_entry(\n        hass,\n        hybrid_enabled=True,\n        electrical_power_threshold=100.0,\n        heating_power_threshold=1000.0,\n        spin_min_cycle_time=0,\n        heated_cycle_min_time=0,\n    )\n    runtime = entry.runtime_data\n    runtime.heating_detector.restore_detected(\n        dt_util.utcnow() - timedelta(minutes=20)\n    )\n\n    assert runtime.async_set_cycle_state(\n        LaundryCycleState.FINAL_SPIN,\n        "test_false_terminal",\n    )\n    start = dt_util.utcnow()\n    runtime.cycle_continuation_detector.reset(now=start)\n    runtime.electrical_spin_detector.reset()\n\n    for step in range(1, 25):\n        assert not runtime._evaluate_cycle_continuation(\n            now=start + timedelta(seconds=30 * step)\n        )\n\n    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN\n    assert (\n        runtime.cycle_continuation_detector\n        .ordinary_activity_coverage_seconds\n        == 0.0\n    )\n\n\nasync def test_heating_resume_revokes_final_spin_immediately(\n    hass: HomeAssistant,\n    enable_custom_integrations: None,\n) -> None:\n    """FR-061: renewed heating is a strong continuation contradiction."""\n    entry = await _setup_entry(\n        hass,\n        hybrid_enabled=False,\n        heating_power_threshold=1000.0,\n        spin_min_cycle_time=0,\n    )\n    runtime = entry.runtime_data\n\n    assert runtime.async_set_cycle_state(\n        LaundryCycleState.FINAL_SPIN,\n        "test_false_terminal",\n    )\n    runtime.heating_detector.restore_detected(\n        dt_util.utcnow() - timedelta(minutes=5)\n    )\n    runtime.heating_detector.heating_active = True\n    runtime.heating_detector.confirmation_coverage_seconds = float(\n        runtime.heating_detector.confirmation_seconds\n    )\n\n    assert runtime._evaluate_cycle_continuation()\n    assert runtime.cycle_state is LaundryCycleState.RUNNING\n    assert runtime.cycle_continuation_reason == (\n        "heating_resumed_after_final_spin"\n    )\n'''
    anchor = '\n\nasync def test_electrical_candidate_resets_when_cycle_finishes('
    if 'test_heated_false_terminal_can_be_revoked_after_strong_continuation' not in text:
        text = replace_once(text, anchor, new_test + anchor, path=path)
    return text


def transform_requirements(text: str) -> str:
    path = "docs/en/REQUIREMENTS.md"
    addition = '''## FR-059\n\nWhen hybrid terminal-spin confirmation is enabled and heating has been latched as `detected`, the electrical spin candidate shall not corroborate `final_spin` immediately upon becoming active. It shall first satisfy a minimum maturity duration. The initial experimental implementation uses 45 seconds. This requirement is based on sustained terminal-profile structure rather than a second machine-specific power threshold.\n\n---\n\n## FR-060\n\nFor a heated cycle using hybrid confirmation, at least one retained vibration rising edge used for terminal confirmation shall occur at or after the start of the current electrical spin candidate. Vibration evidence accumulated entirely before the current electrical episode shall not be sufficient, even after the candidate becomes mature. The maturity requirement from FR-059 and this temporal-correlation requirement are cumulative.\n\n---\n\n## FR-061\n\n`final_spin` shall be revocable through a dedicated `cycle_continuation_confirmed` decision. Ordinary activity or one activity edge alone shall not revoke `final_spin`. The initial conservative implementation shall accept (a) renewed confirmed heater-level operation after `final_spin` as immediate contradictory evidence, or (b) for a heated hybrid cycle, at least 600 seconds of accumulated meaningful-activity coverage while no mature terminal electrical episode is active. Observation gaps shall be bounded by source-freshness limits so stale cached activity cannot fabricate continuation evidence. A mature terminal electrical episode shall clear accumulated prolonged-activity contradiction evidence.\n\nWhen continuation is confirmed, the same cycle shall transition `final_spin → running` without creating a new cycle identifier or start timestamp. The final-spin finish timer shall be cancelled, the normal running-state finish fallback shall become active, old spin evidence and electrical rolling history shall be cleared, and the latched heating context shall be preserved.\n\n---\n\n'''
    if '## FR-059\n' not in text:
        text = replace_once(text, '# Non-Functional Requirements\n', addition + '# Non-Functional Requirements\n', path=path)
    return text


def transform_state_machine_doc(text: str) -> str:
    path = "docs/en/STATE_MACHINE.md"

    maturity_paragraph = (
        "For heated cycles using hybrid confirmation, the electrical candidate "
        "must also mature for the experimental 45-second minimum, and at least "
        "one retained vibration rising edge must occur at or after the start of "
        "that same electrical candidate. Old vibration evidence from before the "
        "current electrical episode cannot complete heated-cycle confirmation."
    )
    if "experimental 45-second minimum" not in text:
        text = insert_before_one_of(
            text,
            (
                "The experimental hybrid detector combines vibration and "
                "electrical evidence with heating-aware cycle context.\n",
                "The normal reduced-evidence hybrid path requires:\n",
            ),
            maturity_paragraph + "\n\n",
            path=path,
        )

    text = replace_if_present(
        text,
        "The exact continuation-confirmation algorithm is implementation-specific "
        "until sufficient field data exists.",
        "The initial continuation-confirmation algorithm remains experimental "
        "while additional field data is collected.",
    )

    continuation_detail = (
        "The initial continuation detector accepts two conservative "
        "contradictions. Renewed confirmed heater-level operation after "
        "`final_spin` confirms continuation immediately. For a heated hybrid "
        "cycle, the detector can also accumulate meaningful-activity coverage "
        "only while no mature terminal electrical episode is active; 600 "
        "seconds of such bounded observed coverage confirms continuation. A "
        "mature terminal electrical episode resets this accumulated "
        "contradiction evidence. Source-freshness bounds prevent stale cached "
        "activity from accumulating unlimited coverage.\n\n"
        "On `final_spin → running`, the existing cycle identity and "
        "`cycle_started_at` are preserved. The shorter final-spin finish timer "
        "is cancelled, the running-state fallback becomes active again, old "
        "vibration evidence and electrical rolling history are cleared, and "
        "latched heating context is retained. Historical diagnostics may record "
        "that a previous final-spin decision was revoked.\n\n"
    )
    if "The initial continuation detector accepts two conservative" not in text:
        section_start = text.find("#### Activity after final spin")
        if section_start == -1:
            raise RuntimeError(
                f"{path}: missing 'Activity after final spin' section"
            )
        section_end = text.find("#### Valid exits", section_start)
        if section_end == -1:
            raise RuntimeError(
                f"{path}: missing Valid exits after final-spin activity section"
            )
        text = text[:section_end] + continuation_detail + text[section_end:]

    return text

def transform_spec(text: str) -> str:
    path = "docs/en/SPECIFICATION.md"

    maturity_paragraph = (
        "For a heated cycle with hybrid confirmation enabled, the electrical "
        "spin candidate must remain active for an experimental minimum of 45 "
        "seconds before it may corroborate `final_spin`. At least one retained "
        "vibration rising edge must also occur at or after the start of that "
        "same electrical candidate. A short intermediate electrical spin or "
        "vibration evidence accumulated only before the current candidate "
        "cannot satisfy the heated terminal rule.\n\n"
    )
    if "experimental minimum of 45 seconds" not in text:
        text = insert_before_one_of(
            text,
            (
                "The electrical candidate corroborates mechanical evidence; "
                "it never replaces it.",
                "The runtime supports two confirmation paths:",
            ),
            maturity_paragraph,
            path=path,
        )

    text = replace_if_present(
        text,
        "The exact continuation-confirmation algorithm remains "
        "implementation-specific until validated across more machines, "
        "programs, and loads.",
        "The initial continuation-confirmation algorithm remains experimental "
        "while it is validated across more machines, programs, and loads.",
    )

    continuation_paragraph = (
        "The initial conservative continuation detector treats renewed "
        "confirmed heater operation as an immediate contradiction. In heated "
        "hybrid cycles it also accumulates meaningful-activity coverage while "
        "no mature terminal electrical episode is active; 600 seconds of such "
        "bounded observed coverage confirms continuation. A mature terminal "
        "electrical episode resets that accumulated contradiction evidence. On "
        "continuation, the existing cycle identity/start timestamp and latched "
        "heating context are preserved while old spin/electrical terminal "
        "evidence is cleared and finish evaluation returns to the running-state "
        "fallback.\n\n"
    )
    if "The initial conservative continuation detector treats renewed" not in text:
        marker = "A return from `final_spin` to `running`"
        start = text.find(marker)
        if start == -1:
            raise RuntimeError(f"{path}: missing final_spin continuation paragraph")
        end = text.find("\n\n", start)
        if end == -1:
            raise RuntimeError(f"{path}: malformed final_spin continuation paragraph")
        insert_at = end + 2
        text = text[:insert_at] + continuation_paragraph + text[insert_at:]

    if "| Heated electrical candidate maturity | 45 s |" not in text:
        lines = text.splitlines(keepends=True)
        matches = [
            i for i, line in enumerate(lines)
            if line.lstrip().startswith("| Hybrid spin required events |")
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"{path}: expected one Hybrid spin required events row, "
                f"got {len(matches)}"
            )
        i = matches[0] + 1
        lines.insert(
            i,
            "| Heated electrical candidate maturity | 45 s | "
            "Experimental internal minimum candidate age before heated hybrid "
            "confirmation |\n"
            "| Cycle-continuation contradictory activity coverage | 600 s | "
            "Experimental internal observed-activity coverage required for "
            "prolonged continuation confirmation |\n",
        )
        text = "".join(lines)

    return text

def transform_architecture(text: str) -> str:
    path = "docs/en/ARCHITECTURE.md"

    maturity_paragraph = (
        "For heated hybrid confirmation, the electrical candidate is not usable "
        "immediately when it becomes active. It must survive an experimental "
        "45-second maturity gate, and at least one retained vibration rising "
        "edge must belong temporally to the same candidate episode by occurring "
        "at or after its start. This temporal correlation is intended to reject "
        "short intermediate spins without introducing a second machine-specific "
        "power threshold.\n\n"
    )
    if "45-second maturity gate" not in text:
        text = insert_before_one_of(
            text,
            (
                "Window, coverage, freshness, electrical thresholds, heating "
                "threshold, and heating timing values are configurable.",
                "The detector must not assume that the terminal spin sequence "
                "has a fixed duration",
            ),
            maturity_paragraph,
            path=path,
        )

    paragraph = (
        "### Cycle Continuation Detector\n\n"
        "`final_spin` is a strong but revocable terminal-phase hypothesis. The "
        "Cycle Continuation Detector is evaluated only after that state has been "
        "entered and is deliberately stricter than normal activity handling.\n\n"
        "It accepts renewed confirmed heater operation as an immediate "
        "contradiction. For heated hybrid cycles it also accumulates bounded "
        "meaningful-activity coverage while no mature terminal electrical "
        "episode is active. The initial experimental confirmation requirement "
        "is 600 seconds of such coverage. A mature terminal electrical episode "
        "resets the accumulated contradiction evidence.\n\n"
        "When continuation is confirmed, runtime requests the already-legal "
        "`final_spin → running` transition, cancels final-spin finish timing, "
        "clears vibration/electrical terminal evidence, preserves the same cycle "
        "start/statistics context and latched heating fact, and resumes the "
        "conservative running-state finish path.\n\n"
    )
    if "### Cycle Continuation Detector\n" not in text:
        text = insert_before_one_of(
            text,
            ("## 3.4 Finish Detector\n", "## 3.4 Finish Detector\r\n"),
            paragraph,
            path=path,
        )

    return text

def transform_readme(text: str) -> str:
    path = "README.md"

    maturity_bullet = (
        "- In a heated hybrid cycle, the electrical spin candidate must mature "
        "for 45 seconds and at least one vibration edge must occur at or after "
        "the start of that candidate before it may confirm `final_spin`.\n"
    )
    if "must mature for 45 seconds" not in text:
        text = insert_before_one_of(
            text,
            (
                "- Stale electrical samples must not continue supporting an "
                "electrical candidate after the configured maximum source age.\n",
                "- Finish is inferred from the absence of meaningful electrical "
                "activity over time rather than from an exact standby-power value.\n",
            ),
            maturity_bullet,
            path=path,
        )

    continuation_bullet = (
        "- `final_spin` is a revocable terminal-phase hypothesis: ordinary "
        "activity alone does not revoke it, but strong dedicated "
        "`cycle_continuation_confirmed` evidence can return the same cycle to "
        "`running`.\n"
    )
    if "revocable terminal-phase hypothesis" not in text:
        text = insert_before_one_of(
            text,
            (
                "- Finish is inferred from the absence of meaningful electrical "
                "activity over time rather than from an exact standby-power value.\n",
                "- Stale electrical samples must not continue supporting an "
                "electrical candidate after the configured maximum source age.\n",
            ),
            continuation_bullet,
            path=path,
        )

    return text

def transform_project_map(text: str) -> str:
    path = "PROJECT_MAP.md"

    lines = text.splitlines(keepends=True)

    for i, line in enumerate(lines):
        if (
            "Terminal spin sequence / terminal phase / experimental hybrid spin confirmation"
            in line
            and line.lstrip().startswith("|")
        ):
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = (
                "| Terminal spin sequence / terminal phase / experimental hybrid "
                "spin confirmation / continuation | `SPECIFICATION.md §7.2`, "
                "`STATE_MACHINE.md §8.4` | `spin.py`, `heating.py`, "
                "`continuation.py`, `runtime.py` | `test_spin.py`, "
                "`test_spin_runtime.py`, `test_heating.py`, "
                "`test_heating_entities.py`, `test_continuation.py` |"
                + newline
            )
            break

    text = "".join(lines)
    text = replace_if_present(
        text,
        "Terminal-phase, hybrid-spin, heating-context, and recovery rules are "
        "currently FR-029 through FR-058.",
        "Terminal-phase, hybrid-spin, heating-context, continuation, and "
        "recovery rules are currently FR-029 through FR-061.",
    )
    text = replace_if_present(
        text,
        "Component boundaries and data flow: source normalization → Activity "
        "Detector / Spin Detector / Finish Detector → State Machine, with "
        "Laundry Tracking, Leak Detector, statistics, diagnostics, and HA "
        "entities separated.",
        "Component boundaries and data flow: source normalization → Activity "
        "Detector / Spin Detector / Cycle Continuation Detector / Finish "
        "Detector → State Machine, with Laundry Tracking, Leak Detector, "
        "statistics, diagnostics, and HA entities separated.",
    )
    text = replace_if_present(
        text,
        "5. `runtime.py` plus the relevant detector (`activity.py`, `spin.py`, "
        "`heating.py`, `finish.py`) — what is actually implemented?",
        "5. `runtime.py` plus the relevant detector (`activity.py`, `spin.py`, "
        "`heating.py`, `continuation.py`, `finish.py`) — what is actually "
        "implemented?",
    )

    continuation_module = (
        "### `continuation.py`\n"
        "Cycle Continuation Detector. Evaluates strong contradictory evidence "
        "after `final_spin`: renewed heating or prolonged bounded meaningful "
        "activity without a mature terminal electrical episode. It does not "
        "change state directly; runtime owns the `final_spin → running` "
        "transition.\n\n"
    )
    if "### `continuation.py`" not in text:
        text = insert_before_one_of(
            text,
            ("### `finish.py`\n", "### `finish.py`\r\n"),
            continuation_module,
            path=path,
        )

    continuation_test = (
        "### `test_continuation.py`\n"
        "Unit tests for cycle-continuation evidence, bounded activity coverage, "
        "heating-resume contradiction, and reset by mature terminal evidence.\n\n"
    )
    if "### `test_continuation.py`" not in text:
        text = insert_before_one_of(
            text,
            ("### `test_finish.py`\n", "### `test_finish.py`\r\n"),
            continuation_test,
            path=path,
        )

    if "continuation.py" not in text or "test_continuation.py" not in text:
        raise RuntimeError(f"{path}: continuation entries were not added")

    return text

def transform_user_manual_en(text: str) -> str:
    path = "docs/en/USER_MANUAL.md"
    addition = (
        "### 10.9 Heated-cycle terminal-profile maturity and continuation\n\n"
        "For a cycle where heating has been detected and hybrid confirmation is "
        "enabled, an electrical spin candidate does not confirm the terminal "
        "phase immediately. The current experimental implementation requires "
        "the candidate to remain active for at least **45 seconds** and requires "
        "at least one retained vibration OFF-to-ON edge to occur at or after "
        "the start of that same electrical candidate. Vibration accumulated only "
        "before the electrical episode cannot complete heated-cycle "
        "confirmation.\n\n"
        "`final_spin` is also revocable when later evidence strongly contradicts "
        "the terminal-phase hypothesis. Laundry Monitor does **not** return to "
        "`running` merely because activity resumes. Instead, renewed confirmed "
        "heater operation is treated as immediate continuation evidence. In a "
        "heated hybrid cycle, prolonged meaningful activity can also confirm "
        "continuation after **600 seconds of accumulated observed activity "
        "coverage** while no mature terminal electrical episode is active. "
        "Source-freshness bounds prevent stale cached activity from accumulating "
        "this coverage.\n\n"
        "When continuation is confirmed, the same cycle returns to `running`; "
        "its original cycle start is preserved, the short final-spin finish "
        "timer is cancelled, old terminal vibration/electrical evidence is "
        "cleared, and the conservative running-state finish fallback resumes.\n\n"
        "These two durations are experimental internal safeguards during field "
        "validation rather than new machine-specific power thresholds.\n\n"
        "---\n\n"
    )
    if "### 10.9 Heated-cycle terminal-profile maturity and continuation" not in text:
        text = insert_before_heading_prefix(
            text,
            "## 11.",
            addition,
            path=path,
        )
    return text

def transform_user_manual_ru(text: str) -> str:
    path = "docs/ru/USER_MANUAL.md"
    addition = (
        "### 10.9 Зрелость terminal-profile в heated-цикле и возврат к "
        "`running`\n\n"
        "Если в цикле был обнаружен нагрев и включён hybrid, одного появления "
        "electrical spin candidate недостаточно для подтверждения терминальной "
        "фазы. В текущей экспериментальной реализации candidate должен "
        "оставаться активным не менее **45 секунд**, а как минимум один "
        "сохранённый фронт вибрации OFF → ON должен произойти не раньше начала "
        "этого же electrical candidate. События вибрации, накопленные только до "
        "начала электрического эпизода, не могут завершить heated-cycle "
        "подтверждение.\n\n"
        "Состояние `final_spin` также становится отзывной гипотезой: при сильном "
        "противоречащем сигнале интеграция может подтвердить "
        "`cycle_continuation_confirmed` и вернуть тот же цикл в `running`. "
        "Простого возобновления активности для этого недостаточно. Повторное "
        "подтверждённое включение нагревателя после `final_spin` считается "
        "сильным немедленным признаком продолжения программы. Для heated "
        "hybrid-цикла продолжение также может быть подтверждено после **600 "
        "секунд накопленного наблюдаемого времени значимой активности**, пока "
        "отсутствует зрелый terminal electrical episode. Ограничение freshness "
        "не позволяет устаревшему состоянию источника искусственно накапливать "
        "это время.\n\n"
        "При подтверждении continuation сохраняются исходные начало и "
        "идентичность цикла и latched heating context; короткий таймер завершения "
        "после `final_spin` отменяется, старые vibration/electrical terminal "
        "evidence очищаются, а снова используется консервативный running-state "
        "fallback.\n\n"
        "Оба временных значения пока являются экспериментальными внутренними "
        "защитными параметрами для field validation, а не новыми "
        "machine-specific порогами мощности.\n\n"
        "---\n\n"
    )
    if "### 10.9 Зрелость terminal-profile" not in text:
        text = insert_before_heading_prefix(
            text,
            "## 11.",
            addition,
            path=path,
        )
    return text


TRANSFORMS = {
    "README.md": transform_readme,
    "custom_components/laundry_monitor/const.py": transform_const,
    "custom_components/laundry_monitor/spin.py": transform_spin,
    "custom_components/laundry_monitor/runtime.py": transform_runtime,
    "custom_components/laundry_monitor/diagnostics.py": transform_diagnostics,
    "custom_components/laundry_monitor/translations/ru.json": transform_ru_json,
    "tests/components/laundry_monitor/test_diagnostics.py": transform_test_diagnostics,
    "tests/components/laundry_monitor/test_spin_runtime.py": transform_spin_runtime_tests,
    "docs/en/REQUIREMENTS.md": transform_requirements,
    "docs/en/STATE_MACHINE.md": transform_state_machine_doc,
    "docs/en/SPECIFICATION.md": transform_spec,
    "docs/en/ARCHITECTURE.md": transform_architecture,
    "PROJECT_MAP.md": transform_project_map,
    "docs/en/USER_MANUAL.md": transform_user_manual_en,
    "docs/ru/USER_MANUAL.md": transform_user_manual_ru,
}

NEW_FILES = {
    "custom_components/laundry_monitor/continuation.py": NEW_CONTINUATION,
    "tests/components/laundry_monitor/test_continuation.py": NEW_CONTINUATION_TESTS,
}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    rendered: dict[str, tuple[str, str]] = {}

    for rel, transformer in TRANSFORMS.items():
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"Run from repository root; missing {rel}")
        before = path.read_text(encoding="utf-8")
        after = transformer(before)
        rendered[rel] = (before, after)

    for rel, content in NEW_FILES.items():
        path = root / rel
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if before and before != content:
            raise RuntimeError(f"{rel} already exists with different content")
        rendered[rel] = (before, content)

    for rel in (
        "custom_components/laundry_monitor/translations/en.json",
        "custom_components/laundry_monitor/translations/ru.json",
    ):
        if rel in rendered:
            json.loads(rendered[rel][1])
        else:
            json.loads((root / rel).read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for rel, (_before, after) in rendered.items():
            if not rel.endswith(".py"):
                continue
            temp_path = tmpdir / Path(rel).name
            temp_path.write_text(after, encoding="utf-8")
            py_compile.compile(str(temp_path), doraise=True)

    diff_lines: list[str] = []
    for rel, (before, after) in rendered.items():
        if before == after:
            continue
        diff_lines.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )

    print("".join(diff_lines), end="")
    if args.apply:
        for rel, (_before, after) in rendered.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(after, encoding="utf-8")
        print(f"\nApplied terminal-spin hardening to {len(rendered)} files.")
    else:
        print("\nPreview only. Re-run with --apply to write the changes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
