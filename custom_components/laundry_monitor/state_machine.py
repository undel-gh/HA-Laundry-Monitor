"""Hardened public state machine for Laundry Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .const import LaundryCycleState


class TransitionStatus(StrEnum):
    """Outcome of a requested state transition."""

    APPLIED = "applied"
    NO_CHANGE = "no_change"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Result of a state-transition request."""

    status: TransitionStatus
    old_state: LaundryCycleState
    new_state: LaundryCycleState
    reason: str
    occurred_at: datetime


ALLOWED_TRANSITIONS: dict[LaundryCycleState, frozenset[LaundryCycleState]] = {
    LaundryCycleState.IDLE: frozenset(
        {
            LaundryCycleState.ARMED,
            LaundryCycleState.RUNNING,
            LaundryCycleState.ERROR,
        }
    ),
    LaundryCycleState.ARMED: frozenset(
        {
            LaundryCycleState.IDLE,
            LaundryCycleState.RUNNING,
            LaundryCycleState.ERROR,
        }
    ),
    LaundryCycleState.RUNNING: frozenset(
        {
            LaundryCycleState.FINAL_SPIN,
            LaundryCycleState.FINISHED,
            LaundryCycleState.ERROR,
        }
    ),
    LaundryCycleState.FINAL_SPIN: frozenset(
        {
            LaundryCycleState.RUNNING,
            LaundryCycleState.FINISHED,
            LaundryCycleState.ERROR,
        }
    ),
    LaundryCycleState.FINISHED: frozenset(
        {
            LaundryCycleState.IDLE,
            LaundryCycleState.RUNNING,
            LaundryCycleState.ERROR,
        }
    ),
    LaundryCycleState.ERROR: frozenset({LaundryCycleState.IDLE}),
}


@dataclass(slots=True)
class LaundryStateMachine:
    """Validate and apply public state transitions."""

    state: LaundryCycleState = LaundryCycleState.IDLE

    def can_transition(self, new_state: LaundryCycleState) -> bool:
        """Return whether a transition is legal."""
        return (
            new_state is self.state
            or new_state in ALLOWED_TRANSITIONS[self.state]
        )

    def transition(
        self,
        new_state: LaundryCycleState,
        *,
        reason: str,
        now: datetime,
    ) -> TransitionResult:
        """Validate and apply a state transition."""
        old_state = self.state

        if new_state is old_state:
            return TransitionResult(
                TransitionStatus.NO_CHANGE,
                old_state,
                new_state,
                reason,
                now,
            )

        if new_state not in ALLOWED_TRANSITIONS[old_state]:
            return TransitionResult(
                TransitionStatus.REJECTED,
                old_state,
                new_state,
                reason,
                now,
            )

        self.state = new_state
        return TransitionResult(
            TransitionStatus.APPLIED,
            old_state,
            new_state,
            reason,
            now,
        )

    def restore(self, state: LaundryCycleState) -> None:
        """Restore a validated persisted state."""
        self.state = state
