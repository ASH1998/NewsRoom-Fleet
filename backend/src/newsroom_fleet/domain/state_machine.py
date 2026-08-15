"""Publication state machine (design report: "Publication state machine").

The gate fails closed: any illegal or unearned transition raises, it never coerces.
"""

from __future__ import annotations

from enum import StrEnum


class PublicationState(StrEnum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    HUMAN_REVIEW = "human_review"
    EDITOR_READY = "editor_ready"
    EDITOR_APPROVED = "editor_approved"
    PUBLISHED = "published"
    RECHECK_PENDING = "recheck_pending"
    CORRECTION_CANDIDATE = "correction_candidate"


TRANSITIONS: dict[PublicationState, frozenset[PublicationState]] = {
    PublicationState.DRAFT: frozenset({PublicationState.REVIEWING}),
    PublicationState.REVIEWING: frozenset(
        {PublicationState.EDITOR_READY, PublicationState.HUMAN_REVIEW}
    ),
    PublicationState.HUMAN_REVIEW: frozenset(
        {PublicationState.REVIEWING, PublicationState.EDITOR_READY}
    ),
    PublicationState.EDITOR_READY: frozenset(
        {PublicationState.EDITOR_APPROVED, PublicationState.HUMAN_REVIEW}
    ),
    PublicationState.EDITOR_APPROVED: frozenset({PublicationState.PUBLISHED}),
    PublicationState.PUBLISHED: frozenset({PublicationState.RECHECK_PENDING}),
    PublicationState.RECHECK_PENDING: frozenset(
        {PublicationState.PUBLISHED, PublicationState.CORRECTION_CANDIDATE}
    ),
    PublicationState.CORRECTION_CANDIDATE: frozenset({PublicationState.PUBLISHED}),
}


class IllegalTransitionError(Exception):
    def __init__(self, current: PublicationState, target: PublicationState) -> None:
        super().__init__(f"illegal transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: PublicationState, target: PublicationState) -> bool:
    return target in TRANSITIONS[current]


def transition(current: PublicationState, target: PublicationState) -> PublicationState:
    """Return the target state or raise. The only way state ever changes."""
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
    return target
