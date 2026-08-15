"""The Editor Gate: deterministic policy evaluation over persisted verdict state.

Canonical decision rules (design report appendix):
- Missing reviewer result        -> NEEDS_HUMAN
- Worker timeout or exception    -> NEEDS_HUMAN
- Contradicted or unsupported    -> NEEDS_HUMAN
- Quarantined evidence           -> unusable for verification
- Reviewer conflict              -> preserve both and escalate
- Low confidence                 -> abstain or escalate, never verify
- Reporter approval attempt      -> deny
- Editor approval without resolved policy requirements -> deny
- Scheduled data change          -> correction/update candidate, never auto-publish

This module only *evaluates* and *denies*. It never mutates verdicts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from newsroom_fleet.domain.contracts import (
    Claim,
    Desk,
    EditorDecision,
    EditorDisposition,
    Role,
    Verdict,
    VerdictResult,
)
from newsroom_fleet.domain.state_machine import PublicationState

#: A VERIFIED verdict below this confidence is treated as escalation, never verification.
MIN_VERIFY_CONFIDENCE = 0.5


class ClaimAssessment(BaseModel):
    claim_id: str
    ok: bool
    missing_desks: list[Desk] = Field(default_factory=list)
    blocking_verdict_ids: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    conflict: bool = False


class GateReport(BaseModel):
    article_id: str
    state: PublicationState  # EDITOR_READY iff every claim assessment is ok
    assessments: list[ClaimAssessment]

    @property
    def blocking_verdict_ids(self) -> list[str]:
        return [vid for a in self.assessments for vid in a.blocking_verdict_ids]

    @property
    def blocked_claim_ids(self) -> list[str]:
        return [a.claim_id for a in self.assessments if not a.ok]


class PublishDecision(BaseModel):
    allowed: bool
    denials: list[str] = Field(default_factory=list)


def usable_verified(verdict: Verdict) -> bool:
    """A verdict counts as verified only with evidence and defensible confidence."""
    return (
        verdict.result is VerdictResult.VERIFIED
        and not verdict.needs_human
        and bool(verdict.evidence)
        and verdict.confidence >= MIN_VERIFY_CONFIDENCE
    )


def assess_claim(claim: Claim, desk_verdicts: list[Verdict]) -> ClaimAssessment:
    """Evaluate one claim against its required desks. Worker-level verdicts only —
    the aggregator's summary is not a substitute for reviewer evidence."""
    by_desk: dict[Desk, list[Verdict]] = {}
    for v in desk_verdicts:
        if v.desk is Desk.VERDICT_AGGREGATOR:
            continue
        by_desk.setdefault(v.desk, []).append(v)

    missing: list[Desk] = []
    blocking_ids: list[str] = []
    reasons: list[str] = []

    for desk in claim.required_desks:
        verdicts = by_desk.get(desk, [])
        if not verdicts:
            # Missing reviewer result -> NEEDS_HUMAN.
            missing.append(desk)
            reasons.append(f"{desk.value}: no verdict on record")
            continue
        for v in verdicts:
            if v.result is VerdictResult.ERROR:
                # Worker timeout or exception -> NEEDS_HUMAN.
                blocking_ids.append(v.verdict_id)
                reasons.append(f"{desk.value}: worker failure ({v.error_detail or 'error'})")
            elif v.result in (VerdictResult.CONTRADICTED, VerdictResult.UNSUPPORTED):
                # Contradicted or unsupported -> NEEDS_HUMAN.
                blocking_ids.append(v.verdict_id)
                reasons.append(f"{desk.value}: {v.result.value} — {v.reason}")
            elif v.result is VerdictResult.ABSTAIN:
                # Low confidence / out of scope -> escalate, never verify.
                blocking_ids.append(v.verdict_id)
                reasons.append(f"{desk.value}: abstains — {v.reason}")
            elif not usable_verified(v):
                # VERIFIED without evidence or below confidence floor -> escalate.
                blocking_ids.append(v.verdict_id)
                reasons.append(f"{desk.value}: verification lacks defensible evidence")

    # Reviewer conflict -> preserve both and escalate. A worker's VERIFIED cannot
    # erase another desk's blocking verdict; both stay in the record.
    conflict = bool(blocking_ids) and any(usable_verified(v) for vs in by_desk.values() for v in vs)

    return ClaimAssessment(
        claim_id=claim.claim_id,
        ok=not missing and not blocking_ids,
        missing_desks=missing,
        blocking_verdict_ids=blocking_ids,
        blocking_reasons=reasons,
        conflict=conflict,
    )


def evaluate_gate(article_id: str, claims: list[Claim], verdicts: list[Verdict]) -> GateReport:
    by_claim: dict[str, list[Verdict]] = {}
    for v in verdicts:
        by_claim.setdefault(v.claim_id, []).append(v)

    assessments = [assess_claim(c, by_claim.get(c.claim_id, [])) for c in claims]
    state = (
        PublicationState.EDITOR_READY
        if all(a.ok for a in assessments)
        else PublicationState.HUMAN_REVIEW
    )
    return GateReport(article_id=article_id, state=state, assessments=assessments)


def decide_publish(
    *,
    role: Role,
    gate: GateReport,
    editor_decision: EditorDecision | None,
) -> PublishDecision:
    """Server-side publish denial. The highest-value moment of the demo."""
    denials: list[str] = []

    # Reporter approval attempt -> deny. Always. (Model never publishes either:
    # only the EDITOR role is ever issued to a human.)
    if role is not Role.EDITOR:
        denials.append(f"role '{role.value}' has no publish authority; an editor must approve")

    if editor_decision is not None and editor_decision.disposition is not EditorDisposition.APPROVE:
        denials.append("recorded editor decision is not an approval")

    if gate.state is not PublicationState.EDITOR_READY:
        blocking = set(gate.blocking_verdict_ids)
        resolved = (
            set(editor_decision.resolved_verdict_ids) if editor_decision is not None else set()
        )
        unresolved = sorted(blocking - resolved)
        if editor_decision is None:
            denials.append(
                f"{len(gate.blocked_claim_ids)} claim(s) unresolved and no editor decision recorded"
            )
        elif unresolved:
            denials.append(f"{len(unresolved)} blocking verdict(s) not resolved by the decision")
        if editor_decision is not None and not editor_decision.revised_text:
            denials.append("blocked claims require a revised text for the safe version")

    return PublishDecision(allowed=not denials, denials=denials)
