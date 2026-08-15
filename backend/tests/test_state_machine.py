import pytest

from newsroom_fleet.domain.state_machine import (
    IllegalTransitionError,
    PublicationState,
    can_transition,
    transition,
)


def test_happy_path_chain():
    state = PublicationState.DRAFT
    for target in (
        PublicationState.REVIEWING,
        PublicationState.HUMAN_REVIEW,
        PublicationState.EDITOR_READY,
        PublicationState.EDITOR_APPROVED,
        PublicationState.PUBLISHED,
        PublicationState.RECHECK_PENDING,
        PublicationState.CORRECTION_CANDIDATE,
        PublicationState.PUBLISHED,
    ):
        state = transition(state, target)
    assert state is PublicationState.PUBLISHED


def test_draft_cannot_jump_to_published():
    assert not can_transition(PublicationState.DRAFT, PublicationState.PUBLISHED)
    with pytest.raises(IllegalTransitionError):
        transition(PublicationState.DRAFT, PublicationState.PUBLISHED)


def test_published_cannot_return_to_draft_or_review():
    for target in (
        PublicationState.DRAFT,
        PublicationState.REVIEWING,
        PublicationState.HUMAN_REVIEW,
        PublicationState.EDITOR_APPROVED,
    ):
        assert not can_transition(PublicationState.PUBLISHED, target)


def test_no_self_loops():
    for state in PublicationState:
        assert not can_transition(state, state)
