"""Grounded Source Verifier: the ladder is attached → search → abstain.

All rules are pinned without any network call: attached sources are never
overridden by search, quarantined evidence is never laundered by it, and a
web-grounded verification only stands if the citing domain is an approved
authority.
"""

from __future__ import annotations

from newsroom_fleet.desks.base import QuarantineNotice, SourceEvidenceView
from newsroom_fleet.desks.live._contracts import DeskJudgement
from newsroom_fleet.desks.live.grounded_source_verifier import GroundedSourceVerifier
from newsroom_fleet.desks.live.grounding import GroundedEvidence, GroundingSource
from newsroom_fleet.domain.contracts import (
    Claim,
    ClaimType,
    Desk,
    RiskTier,
    Source,
    Verdict,
    VerdictResult,
)


def _claim(*, source_refs: list[str] | None = None) -> Claim:
    return Claim(
        claim_id="clm_01",
        article_id="art_gsv",
        text='"This deal will create a thousand jobs," said Councilmember Maria Delgado.',
        span=(0, 60),
        type=ClaimType.QUOTATION,
        risk_tier=RiskTier.MEDIUM,
        required_desks=[Desk.SOURCE_VERIFIER],
        source_refs=source_refs or [],
        extractor_version="test",
    )


def _evidence(
    *, domain: str = "example.com", text: str = "The council published the remark."
) -> GroundedEvidence:
    return GroundedEvidence(
        text=text,
        sources=(
            GroundingSource(ref="web_1", uri="https://example/web_1", domain=domain, title="t"),
        ),
    )


class FakeResearcher:
    """Counts calls so tests can prove search never ran."""

    def __init__(self, evidence: GroundedEvidence) -> None:
        self.evidence = evidence
        self.calls = 0

    async def research(self, claim_text: str, *, article_id: str) -> GroundedEvidence:
        self.calls += 1
        return self.evidence


class FakeAgent:
    def __init__(self, judgement: DeskJudgement) -> None:
        self.judgement = judgement

    async def run(self, payload, schema):
        return self.judgement


class FakeSourceDesk:
    async def review(self, view) -> Verdict:
        return Verdict(
            verdict_id="vrd_attached",
            article_id=view.claim.article_id,
            claim_id=view.claim.claim_id,
            desk=Desk.SOURCE_VERIFIER,
            agent_version="adk-source-verifier-1.0.0",
            result=VerdictResult.UNSUPPORTED,
            confidence=1.0,
            needs_human=True,
            reason="attached-source path",
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )


def _view(claim: Claim) -> SourceEvidenceView:
    return SourceEvidenceView(claim=claim, cited_sources=(), quarantined=())


def _desk(researcher, judgement=None, approved=("gov.example",)) -> GroundedSourceVerifier:
    desk = GroundedSourceVerifier("test-model", researcher=researcher, approved_domains=approved)
    desk._source_desk = FakeSourceDesk()
    if judgement is not None:
        desk._agent = FakeAgent(judgement)
    return desk


async def test_cited_source_is_decided_by_the_plain_desk_search_never_runs():
    researcher = FakeResearcher(_evidence())
    desk = _desk(researcher)
    view = SourceEvidenceView(
        claim=_claim(source_refs=["transcript"]),
        cited_sources=(
            Source(source_id="transcript", kind="interview", name="t", content="hello"),
        ),
        quarantined=(),
    )
    verdict = await desk.review(view)
    assert verdict.reason == "attached-source path"
    assert researcher.calls == 0


async def test_quarantined_source_is_not_laundered_by_search():
    """A reporter's quarantined memo stays quarantined; the desk does not go
    looking for replacement evidence the intake gateway already refused."""
    researcher = FakeResearcher(_evidence())
    desk = _desk(researcher)
    view = SourceEvidenceView(
        claim=_claim(source_refs=["leaked_memo"]),
        cited_sources=(),
        quarantined=(
            QuarantineNotice(
                source_id="leaked_memo", detector="prompt_injection", policy_version="p1"
            ),
        ),
    )
    verdict = await desk.review(view)
    assert verdict.reason == "attached-source path"  # the plain desk's quarantine branch
    assert researcher.calls == 0


async def test_unsourced_claim_researches_and_unapproved_domain_cannot_clear():
    researcher = FakeResearcher(_evidence(domain="random-blog.example"))
    desk = _desk(
        researcher,
        judgement=DeskJudgement(
            result="verified",
            confidence=0.9,
            reason="the quote appears in the retrieved report",
            evidence_locator="web_1",
            evidence_excerpt="a thousand jobs",
        ),
    )
    verdict = await desk.review(_view(_claim()))
    assert researcher.calls == 1
    # apply_authority_rule: a random page agreeing is context, not verification.
    assert verdict.result is VerdictResult.UNSUPPORTED
    assert "unapproved_source" in verdict.flags
    assert "web_grounded" in verdict.flags
    assert verdict.needs_human is True


async def test_approved_domain_can_clear_an_unsourced_claim():
    researcher = FakeResearcher(_evidence(domain="gov.example"))
    desk = _desk(
        researcher,
        judgement=DeskJudgement(
            result="verified",
            confidence=0.9,
            reason="the official transcript contains the quoted language",
            evidence_locator="web_1",
            evidence_excerpt="a thousand jobs",
        ),
    )
    verdict = await desk.review(_view(_claim()))
    assert verdict.result is VerdictResult.VERIFIED
    # The citable handle is materialised to the real URI an editor can open.
    assert verdict.evidence[0].locator == "https://example/web_1"


async def test_ungrounded_answer_from_memory_abstains():
    researcher = FakeResearcher(
        GroundedEvidence(text="The quote is real.", sources=())  # no grounding chunks
    )
    desk = _desk(researcher)
    verdict = await desk.review(_view(_claim()))
    assert verdict.result is VerdictResult.ABSTAIN
    assert "ungrounded_answer" in verdict.flags


async def test_no_source_found_abstains():
    researcher = FakeResearcher(GroundedEvidence(text="", sources=()))
    desk = _desk(researcher)
    verdict = await desk.review(_view(_claim()))
    assert verdict.result is VerdictResult.ABSTAIN
    assert "no_source_found" in verdict.flags
