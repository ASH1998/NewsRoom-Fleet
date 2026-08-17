"""Live-desk output schemas and the citation-locator guard.

The model produces a *judgement*; this module turns it into a signed `Verdict`.
The conversion is not a formality — it is where two safety rules are applied
that a prompt cannot be trusted to enforce:

1. **A citation must resolve.** The desk is handed an explicit list of locators
   it may cite. If it returns a locator outside that list, the verdict is
   rejected and downgraded to UNSUPPORTED with a `broken_locator` flag. That is
   the hallucinated-citation defence from the report's threat table, and it runs
   on every live verdict rather than being sampled.

2. **VERIFIED requires evidence.** A verified judgement with no usable locator
   is downgraded, because the Editor Gate's `usable_verified` check would block
   it anyway — better to record *why* it was downgraded than to emit an
   evidence-free verification and let the gate reject it anonymously.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from newsroom_fleet.desks._common import new_verdict
from newsroom_fleet.domain.authority import is_approved
from newsroom_fleet.domain.contracts import (
    Claim,
    Desk,
    EvidenceRef,
    Verdict,
    VerdictResult,
)


class DeskJudgement(BaseModel):
    """What a live reviewer desk returns. Deliberately small and checkable."""

    result: Literal["verified", "contradicted", "unsupported", "abstain"] = Field(
        description=(
            "verified only if the supplied evidence directly supports the claim; "
            "contradicted if the evidence conflicts with it; unsupported if the "
            "evidence does not establish it; abstain if the claim is outside the "
            "scope of the evidence provided"
        )
    )
    confidence: float = Field(ge=0.0, le=1.0, description="0.0-1.0")
    reason: str = Field(description="One or two sentences an editor can act on.")
    evidence_locator: str = Field(
        default="",
        description=(
            "Must be copied exactly from the allowed_locators list in the request. "
            "Leave empty if no listed locator applies."
        ),
    )
    evidence_excerpt: str = Field(
        default="", description="Short verbatim excerpt from the cited evidence."
    )
    flags: list[str] = Field(default_factory=list)


_RESULTS: dict[str, VerdictResult] = {
    "verified": VerdictResult.VERIFIED,
    "contradicted": VerdictResult.CONTRADICTED,
    "unsupported": VerdictResult.UNSUPPORTED,
    "abstain": VerdictResult.ABSTAIN,
}

#: Results that must be backed by a resolvable locator to stand.
_EVIDENCE_REQUIRED = (VerdictResult.VERIFIED, VerdictResult.CONTRADICTED)


def to_verdict(
    *,
    judgement: DeskJudgement,
    claim: Claim,
    desk: Desk,
    agent_version: str,
    allowed: dict[str, str],
) -> Verdict:
    """Convert a model judgement into a signed verdict, enforcing the guards.

    `allowed` maps every locator the desk was permitted to cite to the identity
    that supplied it.
    """
    result = _RESULTS[judgement.result]
    locator = judgement.evidence_locator.strip()
    flags = list(judgement.flags)

    if locator and locator not in allowed:
        # The desk cited something it was never given. Reject the citation and
        # the verification that rested on it.
        return new_verdict(
            claim=claim,
            desk=desk,
            agent_version=agent_version,
            result=VerdictResult.UNSUPPORTED,
            confidence=min(judgement.confidence, 0.5),
            needs_human=True,
            flags=[*flags, "broken_locator"],
            reason=(
                f"citation rejected: locator '{locator}' is not among the evidence this desk "
                f"was given; original judgement was '{judgement.result}' — {judgement.reason}"
            ),
        )

    evidence: list[EvidenceRef] = []
    if locator:
        evidence.append(
            EvidenceRef(
                source_identity=allowed[locator],
                locator=locator,
                excerpt=judgement.evidence_excerpt[:400],
                retrieved_at=datetime.now(UTC),
            )
        )

    if result in _EVIDENCE_REQUIRED and not evidence:
        return new_verdict(
            claim=claim,
            desk=desk,
            agent_version=agent_version,
            result=VerdictResult.UNSUPPORTED,
            confidence=min(judgement.confidence, 0.5),
            needs_human=True,
            flags=[*flags, "missing_locator"],
            reason=(
                f"'{judgement.result}' asserted without a resolvable evidence locator — "
                f"{judgement.reason}"
            ),
        )

    return new_verdict(
        claim=claim,
        desk=desk,
        agent_version=agent_version,
        result=result,
        confidence=judgement.confidence,
        needs_human=result is not VerdictResult.VERIFIED,
        flags=flags,
        reason=judgement.reason,
        evidence=evidence,
    )


def apply_authority_rule(
    verdict: Verdict,
    *,
    locator_domains: dict[str, str],
    extra_approved: tuple[str, ...] = (),
) -> Verdict:
    """Only an approved authority may clear a claim; anything may raise one.

    Applied to web-grounded verdicts after `to_verdict`. A `VERIFIED` resting on
    an unapproved domain is downgraded to `UNSUPPORTED` — the evidence is kept
    and shown to the editor, because "a source we do not vouch for agrees with
    this" is genuinely useful context. It just is not verification.

    Non-verified results pass through untouched: an unapproved source that
    *contradicts* the article is still worth an editor's attention.
    """
    if verdict.result is not VerdictResult.VERIFIED:
        return verdict

    cited = [ref.locator for ref in verdict.evidence]
    domains = [locator_domains.get(locator, "") for locator in cited]
    if any(is_approved(domain, extra_approved) for domain in domains):
        return verdict

    shown = ", ".join(d for d in domains if d) or "an unidentified source"
    return verdict.model_copy(
        update={
            "result": VerdictResult.UNSUPPORTED,
            "needs_human": True,
            "confidence": min(verdict.confidence, 0.6),
            "flags": [*verdict.flags, "unapproved_source"],
            "reason": (
                f"corroborated only by {shown}, which is not on the newsroom's approved "
                f"authority list — an editor must confirm the source before this can "
                f"clear. Finding was: {verdict.reason}"
            ),
        }
    )
