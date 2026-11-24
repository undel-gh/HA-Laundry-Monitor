"""Pure heating-aware terminal-spin confirmation policy.

The runtime owns all detector updates, persistent evidence, state transitions,
Home Assistant events and notifications. This module only chooses a policy
result from explicitly supplied immutable facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .heating import HeatingState
from .spin import SpinEvaluation


@dataclass(frozen=True, slots=True)
class SpinDecisionInputs:
    """Immutable evaluation and calibration facts from the runtime."""

    evaluation: SpinEvaluation
    now: datetime
    hybrid_enabled: bool
    heating_state: HeatingState
    heating_active: bool
    electrical_power_threshold_configured: bool
    heating_power_threshold_configured: bool
    electrical_candidate: bool
    electrical_candidate_since: datetime | None
    cycle_started_at: datetime | None
    vibration_required_events: int
    hybrid_required_events: int
    spin_min_cycle_seconds: int
    heated_cycle_min_seconds: int
    heated_candidate_min_duration_seconds: int


@dataclass(frozen=True, slots=True)
class SpinDecision:
    """Side-effect-free decision, including the original diagnostic reason."""

    confirmation_path: str | None
    hybrid_variant: str | None
    gate_reason: str

    @property
    def confirmed(self) -> bool:
        """Return whether the runtime may request a final-spin transition."""
        return self.confirmation_path is not None


def decide_spin_confirmation(inputs: SpinDecisionInputs) -> SpinDecision:
    """Apply the existing ordered policy after SpinDetector.evaluate().

    The order is a behavioral contract: see the first-match decision table in
    docs/reference/STATE_MACHINE.md, Section 8.4. Do not reorder gates.
    """
    evaluation = inputs.evaluation
    heated_hybrid_requires_electrical = (
        inputs.hybrid_enabled
        and inputs.heating_state is HeatingState.DETECTED
    )

    if inputs.heating_active:
        return SpinDecision(None, None, "heating_active")

    if evaluation.detected and not heated_hybrid_requires_electrical:
        return SpinDecision("vibration_only", None, "confirmed_vibration_only")

    if not inputs.hybrid_enabled:
        return SpinDecision(None, None, "hybrid_disabled")

    if not inputs.electrical_power_threshold_configured:
        return SpinDecision(None, None, "hybrid_spin_threshold_not_configured")

    if not inputs.heating_power_threshold_configured:
        return SpinDecision(None, None, "hybrid_heating_not_configured")

    if not inputs.electrical_candidate:
        if heated_hybrid_requires_electrical and evaluation.detected:
            return SpinDecision(
                None, None, "heated_cycle_requires_electrical_candidate"
            )
        return SpinDecision(None, None, "electrical_candidate_inactive")

    if not evaluation.activity_recent:
        return SpinDecision(None, None, "activity_not_recent")

    if inputs.heating_state is HeatingState.UNKNOWN:
        return SpinDecision(None, None, "heating_unknown")

    if (
        inputs.heating_state is HeatingState.NOT_SEEN
        and not evaluation.cycle_mature
    ):
        if evaluation.evidence_count >= inputs.vibration_required_events:
            return SpinDecision(
                "hybrid", "fast_non_heated", "confirmed_fast_non_heated"
            )
        return SpinDecision(None, None, "fast_path_requires_full_vibration")

    if evaluation.evidence_count < inputs.hybrid_required_events:
        return SpinDecision(None, None, "hybrid_vibration_insufficient")

    if inputs.heating_state is HeatingState.DETECTED:
        if inputs.cycle_started_at is None:
            return SpinDecision(None, None, "cycle_age_unknown")

        cycle_age = max(
            (inputs.now - inputs.cycle_started_at).total_seconds(),
            0.0,
        )
        effective_min = max(
            inputs.spin_min_cycle_seconds,
            inputs.heated_cycle_min_seconds,
        )
        if cycle_age < effective_min:
            return SpinDecision(None, None, "heated_cycle_too_young")

        candidate_since = inputs.electrical_candidate_since
        if not (
            inputs.electrical_candidate
            and candidate_since is not None
            and inputs.now - candidate_since
            >= timedelta(
                seconds=inputs.heated_candidate_min_duration_seconds
            )
        ):
            return SpinDecision(
                None, None, "heated_electrical_candidate_immature"
            )

        if (
            candidate_since is None
            or evaluation.latest_evidence_at is None
            or evaluation.latest_evidence_at < candidate_since
        ):
            return SpinDecision(
                None,
                None,
                "heated_cycle_requires_fresh_vibration_after_electrical_candidate",
            )

        return SpinDecision("hybrid", "reduced", "confirmed_hybrid_reduced")

    return SpinDecision("hybrid", "reduced", "confirmed_hybrid_reduced")
