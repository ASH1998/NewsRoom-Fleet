"""Failure visibility: timeout/retry/idempotency, worker failure -> NEEDS_HUMAN."""

import asyncio
from datetime import UTC, datetime

from newsroom_fleet.domain.contracts import (
    Claim,
    ClaimType,
    Desk,
    EvidenceRef,
    RiskTier,
    Verdict,
    VerdictResult,
)
from newsroom_fleet.orchestration.runner import DeskRunner, RunnerConfig


def make_claim(article_id: str = "art_run") -> Claim:
    return Claim(
        claim_id="clm_01",
        article_id=article_id,
        text="Some claim.",
        span=(0, 10),
        type=ClaimType.GENERAL,
        risk_tier=RiskTier.LOW,
        required_desks=[Desk.STANDARDS_REVIEWER],
        extractor_version="test",
    )


def healthy_verdict(claim: Claim) -> Verdict:
    return Verdict(
        verdict_id="vrd_healthy",
        article_id=claim.article_id,
        claim_id=claim.claim_id,
        desk=Desk.STANDARDS_REVIEWER,
        agent_version="test",
        result=VerdictResult.VERIFIED,
        confidence=0.9,
        needs_human=False,
        reason="ok",
        evidence=[
            EvidenceRef(
                source_identity="x", locator="x#1", excerpt="", retrieved_at=datetime.now(UTC)
            )
        ],
        created_at=datetime.now(UTC),
    )


class CrashingDesk:
    agent_version = "crash-1"

    async def review(self, view):
        raise RuntimeError("boom")


class SlowDesk:
    agent_version = "slow-1"

    async def review(self, view):
        await asyncio.sleep(5)


class CountingDesk:
    agent_version = "count-1"

    def __init__(self, claim):
        self.calls = 0
        self._claim = claim

    async def review(self, view):
        self.calls += 1
        return healthy_verdict(self._claim)


async def test_crashing_desk_retries_then_error_verdict(repo):
    runner = DeskRunner(repo, RunnerConfig(timeout_s=1.0, max_attempts=2))
    claim = make_claim()
    verdict = await runner.run_review(CrashingDesk(), Desk.STANDARDS_REVIEWER, claim, object())
    assert verdict.result is VerdictResult.ERROR
    assert verdict.needs_human is True
    events = repo.get_events(claim.article_id)
    assert [e.event_type for e in events].count("desk_error") == 2
    assert events[-1].event_type == "worker_failed_needs_human"


async def test_slow_desk_times_out_within_budget(repo):
    runner = DeskRunner(repo, RunnerConfig(timeout_s=0.05, max_attempts=2))
    verdict = await runner.run_review(SlowDesk(), Desk.STANDARDS_REVIEWER, make_claim(), object())
    assert verdict.result is VerdictResult.ERROR
    assert "timeout" in (verdict.error_detail or "")


async def test_duplicate_delivery_is_idempotent(repo):
    claim = make_claim()
    runner = DeskRunner(repo, RunnerConfig())
    desk = CountingDesk(claim)
    first = await runner.run_review(desk, Desk.STANDARDS_REVIEWER, claim, object())
    second = await runner.run_review(desk, Desk.STANDARDS_REVIEWER, claim, object())
    assert desk.calls == 1  # second delivery served from persistence
    assert first.verdict_id == second.verdict_id
    assert len(repo.get_article_verdicts(claim.article_id)) == 1


async def test_error_verdict_can_be_replaced_by_healthy_run(repo):
    claim = make_claim()
    failing = DeskRunner(repo, RunnerConfig(fail_desk=Desk.STANDARDS_REVIEWER))
    error_verdict = await failing.run_review(
        CountingDesk(claim), Desk.STANDARDS_REVIEWER, claim, object()
    )
    assert error_verdict.result is VerdictResult.ERROR

    healthy = DeskRunner(repo, RunnerConfig())
    recovered = await healthy.run_review(
        CountingDesk(claim), Desk.STANDARDS_REVIEWER, claim, object()
    )
    assert recovered.result is VerdictResult.VERIFIED
    assert (
        repo.get_verdict(claim.article_id, claim.claim_id, Desk.STANDARDS_REVIEWER).result
        is VerdictResult.VERIFIED
    )
    assert len(repo.get_article_verdicts(claim.article_id)) == 1  # single persisted result per key
