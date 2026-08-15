"""The approved-authority rule: anything may raise a claim, only an authority clears one."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from newsroom_fleet.desks.live._contracts import apply_authority_rule
from newsroom_fleet.domain.authority import is_approved
from newsroom_fleet.domain.contracts import (
    Claim,
    ClaimType,
    Desk,
    EvidenceRef,
    RiskTier,
    Verdict,
    VerdictResult,
)


@pytest.mark.parametrize(
    "domain",
    [
        "pib.gov.in",
        "mospi.gov.in",
        "www.pib.gov.in",  # www is stripped
        "rbi.org.in",
        "who.int",
        "ec.europa.eu",
        "federalreserve.gov",
    ],
)
def test_approved_authorities(domain: str) -> None:
    assert is_approved(domain)


@pytest.mark.parametrize(
    "domain",
    [
        "affairscloud.com",
        "somenewsblog.in",
        "",
        "notgov.in",  # must not match ".gov.in" by bare substring
        "gov.in.example.com",  # suffix match only, not any occurrence
        "mediumgov",
    ],
)
def test_unapproved_sources(domain: str) -> None:
    assert not is_approved(domain)


def test_extra_domains_extend_the_list() -> None:
    assert not is_approved("harborview-clerk.org")
    assert is_approved("harborview-clerk.org", ("harborview-clerk.org",))


def _claim() -> Claim:
    return Claim(
        claim_id="clm_01",
        article_id="art_1",
        text="Unemployment was 4.2 percent.",
        span=(0, 29),
        type=ClaimType.NUMERIC,
        risk_tier=RiskTier.MEDIUM,
        required_desks=[Desk.DATA_CHECKER],
        extractor_version="test",
    )


def _verdict(result: VerdictResult, locator: str) -> Verdict:
    return Verdict(
        verdict_id="vrd_1",
        article_id="art_1",
        claim_id="clm_01",
        desk=Desk.DATA_CHECKER,
        agent_version="test",
        result=result,
        confidence=0.95,
        reason="finding",
        evidence=[
            EvidenceRef(
                source_identity="web",
                locator=locator,
                excerpt="",
                retrieved_at=datetime.now(UTC),
            )
        ],
        created_at=datetime.now(UTC),
    )


def test_verified_on_an_approved_authority_stands() -> None:
    verdict = apply_authority_rule(
        _verdict(VerdictResult.VERIFIED, "web_1"),
        locator_domains={"web_1": "pib.gov.in"},
    )
    assert verdict.result is VerdictResult.VERIFIED
    assert "unapproved_source" not in verdict.flags


def test_verified_on_a_blog_is_downgraded_not_dropped() -> None:
    """The evidence survives — an editor should see who agreed with the reporter."""
    verdict = apply_authority_rule(
        _verdict(VerdictResult.VERIFIED, "web_1"),
        locator_domains={"web_1": "affairscloud.com"},
    )
    assert verdict.result is VerdictResult.UNSUPPORTED
    assert verdict.needs_human
    assert "unapproved_source" in verdict.flags
    assert "affairscloud.com" in verdict.reason
    assert verdict.evidence  # the citation is retained for the editor


def test_contradiction_from_an_unapproved_source_survives() -> None:
    """Anything may raise a problem: a blog that contradicts the article still counts."""
    verdict = apply_authority_rule(
        _verdict(VerdictResult.CONTRADICTED, "web_1"),
        locator_domains={"web_1": "somenewsblog.in"},
    )
    assert verdict.result is VerdictResult.CONTRADICTED
    assert "unapproved_source" not in verdict.flags


def test_verified_with_an_unmappable_locator_is_downgraded() -> None:
    """A citation we cannot attribute to a domain cannot clear a claim."""
    verdict = apply_authority_rule(
        _verdict(VerdictResult.VERIFIED, "web_9"),
        locator_domains={"web_1": "pib.gov.in"},
    )
    assert verdict.result is VerdictResult.UNSUPPORTED
    assert "unapproved_source" in verdict.flags
