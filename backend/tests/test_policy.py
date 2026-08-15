"""Editor Gate: every canonical decision rule from the design report appendix."""

from datetime import UTC, datetime
from uuid import uuid4

from newsroom_fleet.domain.contracts import (
    Claim,
    ClaimType,
    Desk,
    EditorDecision,
    EditorDisposition,
    EvidenceRef,
    RiskTier,
    Role,
    Verdict,
    VerdictResult,
)
from newsroom_fleet.domain.policy import (
    MIN_VERIFY_CONFIDENCE,
    decide_publish,
    evaluate_gate,
)
from newsroom_fleet.domain.state_machine import PublicationState

ARTICLE = "art_test"


def make_claim(desks: list[Desk], claim_id: str = "clm_01") -> Claim:
    return Claim(
        claim_id=claim_id,
        article_id=ARTICLE,
        text="A checkable claim.",
        span=(0, 18),
        type=ClaimType.GENERAL,
        risk_tier=RiskTier.LOW,
        required_desks=desks,
        extractor_version="test",
    )


def make_verdict(
    desk: Desk,
    result: VerdictResult,
    *,
    claim_id: str = "clm_01",
    confidence: float = 0.9,
    needs_human: bool = False,
    with_evidence: bool = True,
) -> Verdict:
    evidence = (
        [
            EvidenceRef(
                source_identity="fixture",
                locator="fixture#1",
                excerpt="e",
                retrieved_at=datetime.now(UTC),
            )
        ]
        if with_evidence
        else []
    )
    return Verdict(
        verdict_id=f"vrd_{uuid4().hex[:8]}",
        article_id=ARTICLE,
        claim_id=claim_id,
        desk=desk,
        agent_version="test",
        result=result,
        confidence=confidence,
        needs_human=needs_human,
        reason="test",
        evidence=evidence,
        created_at=datetime.now(UTC),
    )


def make_decision(resolved: list[str], revised: str | None = "safe revision") -> EditorDecision:
    return EditorDecision(
        decision_id="dec_1",
        article_id=ARTICLE,
        actor="editor@test",
        role=Role.EDITOR,
        disposition=EditorDisposition.APPROVE,
        rationale="reviewed",
        revised_text=revised,
        resolved_verdict_ids=resolved,
        created_at=datetime.now(UTC),
    )


def test_missing_reviewer_result_blocks():
    gate = evaluate_gate(ARTICLE, [make_claim([Desk.DATA_CHECKER])], [])
    assert gate.state is PublicationState.HUMAN_REVIEW
    assert gate.assessments[0].missing_desks == [Desk.DATA_CHECKER]


def test_contradicted_and_unsupported_block():
    for result in (VerdictResult.CONTRADICTED, VerdictResult.UNSUPPORTED, VerdictResult.ABSTAIN):
        gate = evaluate_gate(
            ARTICLE,
            [make_claim([Desk.DATA_CHECKER])],
            [make_verdict(Desk.DATA_CHECKER, result)],
        )
        assert gate.state is PublicationState.HUMAN_REVIEW, result
        assert gate.blocking_verdict_ids


def test_worker_error_blocks():
    gate = evaluate_gate(
        ARTICLE,
        [make_claim([Desk.SOURCE_VERIFIER])],
        [make_verdict(Desk.SOURCE_VERIFIER, VerdictResult.ERROR)],
    )
    assert gate.state is PublicationState.HUMAN_REVIEW
    assert "worker failure" in gate.assessments[0].blocking_reasons[0]


def test_verified_requires_evidence_and_confidence():
    for bad in (
        make_verdict(Desk.DATA_CHECKER, VerdictResult.VERIFIED, with_evidence=False),
        make_verdict(
            Desk.DATA_CHECKER, VerdictResult.VERIFIED, confidence=MIN_VERIFY_CONFIDENCE - 0.01
        ),
        make_verdict(Desk.DATA_CHECKER, VerdictResult.VERIFIED, needs_human=True),
    ):
        gate = evaluate_gate(ARTICLE, [make_claim([Desk.DATA_CHECKER])], [bad])
        assert gate.state is PublicationState.HUMAN_REVIEW


def test_all_clear_is_editor_ready():
    verdicts = [
        make_verdict(Desk.SOURCE_VERIFIER, VerdictResult.VERIFIED),
        make_verdict(Desk.STANDARDS_REVIEWER, VerdictResult.VERIFIED),
    ]
    gate = evaluate_gate(
        ARTICLE, [make_claim([Desk.SOURCE_VERIFIER, Desk.STANDARDS_REVIEWER])], verdicts
    )
    assert gate.state is PublicationState.EDITOR_READY
    assert gate.blocked_claim_ids == []


def test_reviewer_conflict_is_preserved_and_escalated():
    verdicts = [
        make_verdict(Desk.SOURCE_VERIFIER, VerdictResult.VERIFIED),
        make_verdict(Desk.STANDARDS_REVIEWER, VerdictResult.CONTRADICTED),
    ]
    gate = evaluate_gate(
        ARTICLE, [make_claim([Desk.SOURCE_VERIFIER, Desk.STANDARDS_REVIEWER])], verdicts
    )
    assert gate.state is PublicationState.HUMAN_REVIEW
    assert gate.assessments[0].conflict is True
    assert len(gate.assessments[0].blocking_verdict_ids) == 1  # both verdicts stay on record


def test_reporter_approval_attempt_denied():
    gate = evaluate_gate(
        ARTICLE,
        [make_claim([Desk.DATA_CHECKER])],
        [make_verdict(Desk.DATA_CHECKER, VerdictResult.VERIFIED)],
    )
    decision = decide_publish(role=Role.REPORTER, gate=gate, editor_decision=None)
    assert not decision.allowed
    assert any("no publish authority" in d for d in decision.denials)


def test_editor_approval_without_resolution_denied():
    bad = make_verdict(Desk.DATA_CHECKER, VerdictResult.CONTRADICTED)
    gate = evaluate_gate(ARTICLE, [make_claim([Desk.DATA_CHECKER])], [bad])
    # no decision at all
    assert not decide_publish(role=Role.EDITOR, gate=gate, editor_decision=None).allowed
    # decision covering nothing
    assert not decide_publish(
        role=Role.EDITOR, gate=gate, editor_decision=make_decision(resolved=[])
    ).allowed
    # decision covering the verdict but without revised text
    assert not decide_publish(
        role=Role.EDITOR, gate=gate, editor_decision=make_decision([bad.verdict_id], revised=None)
    ).allowed


def test_editor_resolution_allows_publish():
    bad = make_verdict(Desk.DATA_CHECKER, VerdictResult.CONTRADICTED)
    gate = evaluate_gate(ARTICLE, [make_claim([Desk.DATA_CHECKER])], [bad])
    outcome = decide_publish(
        role=Role.EDITOR, gate=gate, editor_decision=make_decision([bad.verdict_id])
    )
    assert outcome.allowed, outcome.denials
