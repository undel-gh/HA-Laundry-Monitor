"""Pure ordered final-spin decision policy regression matrix (issue #3)."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.laundry_monitor.heating import HeatingState
from custom_components.laundry_monitor.spin import SpinEvaluation
from custom_components.laundry_monitor.spin_decision import (
    SpinDecision,
    SpinDecisionInputs,
    decide_spin_confirmation,
)

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _evaluation(
    *,
    detected: bool = False,
    count: int = 2,
    recent: bool = True,
    mature: bool = True,
    edge: datetime | None = NOW - timedelta(seconds=5),
) -> SpinEvaluation:
    """Build immutable detector evidence (no mocked runtime objects)."""
    return SpinEvaluation(
        detected=detected,
        confidence=1.0 if detected else 0.667,
        evidence_count=count,
        new_evidence=False,
        latest_evidence_at=edge,
        activity_recent=recent,
        cycle_mature=mature,
    )


def _inputs(**overrides: object) -> SpinDecisionInputs:
    """Eligible NOT_SEEN reduced-hybrid baseline."""
    baseline = SpinDecisionInputs(
        evaluation=_evaluation(),
        now=NOW,
        hybrid_enabled=True,
        heating_state=HeatingState.NOT_SEEN,
        heating_active=False,
        electrical_power_threshold_configured=True,
        heating_power_threshold_configured=True,
        electrical_candidate=True,
        electrical_candidate_since=NOW - timedelta(seconds=60),
        cycle_started_at=NOW - timedelta(seconds=1200),
        vibration_required_events=3,
        hybrid_required_events=2,
        spin_min_cycle_seconds=600,
        heated_cycle_min_seconds=900,
        heated_candidate_min_duration_seconds=45,
    )
    return replace(baseline, **overrides)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        pytest.param(
            {}, ("hybrid", "reduced", "confirmed_hybrid_reduced"),
            id="mature-not-seen-reduced-hybrid",
        ),
        pytest.param(
            {
                "heating_active": True,
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(detected=True, count=3),
            },
            (None, None, "heating_active"),
            id="heater-active-blocks-every-path",
        ),
        pytest.param(
            {"evaluation": _evaluation(detected=True, count=3)},
            ("vibration_only", None, "confirmed_vibration_only"),
            id="full-vibration-not-seen",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.UNKNOWN,
                "evaluation": _evaluation(detected=True, count=3),
            },
            ("vibration_only", None, "confirmed_vibration_only"),
            id="full-vibration-unknown-heating-still-eligible",
        ),
        pytest.param(
            {
                "hybrid_enabled": False,
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(detected=True, count=3),
            },
            ("vibration_only", None, "confirmed_vibration_only"),
            id="hybrid-off-retains-heated-vibration-only",
        ),
        pytest.param(
            {"hybrid_enabled": False},
            (None, None, "hybrid_disabled"),
            id="hybrid-disabled-priority",
        ),
        pytest.param(
            {
                "hybrid_enabled": False,
                "electrical_power_threshold_configured": False,
            },
            (None, None, "hybrid_disabled"),
            id="hybrid-disabled-before-missing-electrical-threshold",
        ),
        pytest.param(
            {"electrical_power_threshold_configured": False},
            (None, None, "hybrid_spin_threshold_not_configured"),
            id="missing-electrical-spin-threshold",
        ),
        pytest.param(
            {
                "electrical_power_threshold_configured": False,
                "heating_power_threshold_configured": False,
            },
            (None, None, "hybrid_spin_threshold_not_configured"),
            id="electrical-threshold-priority",
        ),
        pytest.param(
            {"heating_power_threshold_configured": False},
            (None, None, "hybrid_heating_not_configured"),
            id="missing-heating-threshold",
        ),
        pytest.param(
            {
                "heating_power_threshold_configured": False,
                "electrical_candidate": False,
            },
            (None, None, "hybrid_heating_not_configured"),
            id="heating-threshold-before-electrical-candidate",
        ),
        pytest.param(
            {"electrical_candidate": False},
            (None, None, "electrical_candidate_inactive"),
            id="inactive-electrical-candidate",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(detected=True, count=3),
                "electrical_candidate": False,
            },
            (None, None, "heated_cycle_requires_electrical_candidate"),
            id="heated-full-vibration-cannot-bypass-candidate-fr058",
        ),
        pytest.param(
            {"evaluation": _evaluation(recent=False)},
            (None, None, "activity_not_recent"),
            id="stale-meaningful-activity",
        ),
        pytest.param(
            {
                "evaluation": _evaluation(recent=False),
                "heating_state": HeatingState.UNKNOWN,
            },
            (None, None, "activity_not_recent"),
            id="stale-activity-precedes-heating-unknown",
        ),
        pytest.param(
            {"heating_state": HeatingState.UNKNOWN},
            (None, None, "heating_unknown"),
            id="unknown-heating-blocks-reduced-hybrid",
        ),
        pytest.param(
            {"evaluation": _evaluation(mature=False)},
            (None, None, "fast_path_requires_full_vibration"),
            id="early-not-seen-requires-full-evidence",
        ),
        pytest.param(
            {
                "evaluation": _evaluation(
                    detected=False, count=3, mature=False
                )
            },
            ("hybrid", "fast_non_heated", "confirmed_fast_non_heated"),
            id="early-fast-not-seen-three-edges",
        ),
        pytest.param(
            {"evaluation": _evaluation(count=1)},
            (None, None, "hybrid_vibration_insufficient"),
            id="reduced-vibration-insufficient",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(count=1),
                "cycle_started_at": None,
            },
            (None, None, "hybrid_vibration_insufficient"),
            id="reduced-count-gate-before-cycle-age",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "cycle_started_at": None,
            },
            (None, None, "cycle_age_unknown"),
            id="heated-cycle-start-missing",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "cycle_started_at": NOW - timedelta(seconds=899),
            },
            (None, None, "heated_cycle_too_young"),
            id="heated-cycle-below-minimum",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "cycle_started_at": NOW + timedelta(seconds=10),
            },
            (None, None, "heated_cycle_too_young"),
            id="negative-heated-age-clamped-to-zero",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "electrical_candidate_since": None,
            },
            (None, None, "heated_electrical_candidate_immature"),
            id="heated-candidate-without-start",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "electrical_candidate_since": NOW - timedelta(
                    seconds=44, milliseconds=999
                ),
            },
            (None, None, "heated_electrical_candidate_immature"),
            id="heated-candidate-just-below-45-seconds-fr059",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "electrical_candidate_since": NOW + timedelta(seconds=1),
            },
            (None, None, "heated_electrical_candidate_immature"),
            id="candidate-start-in-future-fails-maturity",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(edge=None),
            },
            (
                None, None,
                "heated_cycle_requires_fresh_vibration_after_electrical_candidate",
            ),
            id="heated-no-latest-edge-fr060",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(
                    edge=NOW - timedelta(seconds=61)
                ),
            },
            (
                None, None,
                "heated_cycle_requires_fresh_vibration_after_electrical_candidate",
            ),
            id="heated-vibration-before-current-candidate-fr060",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(
                    detected=True, count=3,
                    edge=NOW - timedelta(seconds=61),
                ),
            },
            (
                None, None,
                "heated_cycle_requires_fresh_vibration_after_electrical_candidate",
            ),
            id="heated-full-evidence-still-needs-fresh-edge-fr058-fr060",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(
                    edge=NOW - timedelta(seconds=45)
                ),
                "electrical_candidate_since": NOW - timedelta(seconds=45),
            },
            ("hybrid", "reduced", "confirmed_hybrid_reduced"),
            id="candidate-45-seconds-and-edge-exactly-equal-fr059-fr060",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "cycle_started_at": NOW - timedelta(seconds=900),
            },
            ("hybrid", "reduced", "confirmed_hybrid_reduced"),
            id="heated-cycle-exact-minimum-age",
        ),
        pytest.param(
            {
                "heating_state": HeatingState.DETECTED,
                "evaluation": _evaluation(detected=True, count=3),
            },
            ("hybrid", "reduced", "confirmed_hybrid_reduced"),
            id="heated-full-evidence-uses-hybrid-not-vibration-only",
        ),
    ],
)
def test_pure_gate_precedence(
    facts: dict[str, object],
    expected: tuple[str | None, str | None, str],
) -> None:
    """Lock branch order and all diagnostic strings to the original runtime."""
    inputs = _inputs(**facts)
    decision = decide_spin_confirmation(inputs)

    assert (
        decision.confirmation_path,
        decision.hybrid_variant,
        decision.gate_reason,
    ) == expected
    assert decision.confirmed is (expected[0] is not None)


def test_decision_is_immutable_deterministic_and_has_no_detector_effect() -> None:
    """Running a policy again cannot alter frozen evidence or its inputs."""
    evaluation = _evaluation(detected=True, count=3)
    inputs = _inputs(
        evaluation=evaluation,
        heating_state=HeatingState.DETECTED,
    )
    original = replace(inputs)
    first = decide_spin_confirmation(inputs)
    second = decide_spin_confirmation(inputs)

    assert first == second
    assert inputs == original
    assert evaluation.evidence_count == 3
    assert first == SpinDecision(
        "hybrid", "reduced", "confirmed_hybrid_reduced"
    )

    with pytest.raises(FrozenInstanceError):
        inputs.hybrid_enabled = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.gate_reason = "other"  # type: ignore[misc]
