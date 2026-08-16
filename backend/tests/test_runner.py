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


async def test_review_all_paces_claims_one_at_a_time_by_default(repo):
    """Bounded claim concurrency: no overlap at the default of one, overlap
    allowed when the limit is raised. A live fleet that fires every claim at
    once saturates the event loop and trips API rate limits — found live on a
    12-claim user submission."""
    from newsroom_fleet.adapters.authoritative import load_fixture_adapter
    from newsroom_fleet.config import FIXTURES_DIR
    from newsroom_fleet.desks.factory import fixture_desk_set
    from newsroom_fleet.fixtures.loader import load_golden_article
    from newsroom_fleet.memory.store import load_memory
    from newsroom_fleet.orchestration.router import PolicyRouter, RoutingContext

    active = 0
    peak = 0

    class PacingDesk:
        agent_version = "pacing-1"

        async def review(self, view):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return healthy_verdict(view.claim)

    article = load_golden_article()
    ctx = RoutingContext(
        article=article,
        security_results=[],
        adapter=load_fixture_adapter(FIXTURES_DIR / "authoritative_data.json", "v1"),
        memory=load_memory(FIXTURES_DIR / "house_rules.json"),
    )
    desks = fixture_desk_set()
    desks.workers[Desk.STANDARDS_REVIEWER] = PacingDesk()

    sequential = PolicyRouter(repo, DeskRunner(repo, RunnerConfig()), desks)
    claims = [
        make_claim().model_copy(update={"claim_id": "clm_01"}),
        make_claim().model_copy(update={"claim_id": "clm_02"}),
    ]
    verdicts = await sequential.review_all(claims, ctx)
    assert peak == 1  # one claim at a time
    assert len(verdicts) == 4  # worker + aggregate per claim

    peak = 0
    parallel = PolicyRouter(repo, DeskRunner(repo, RunnerConfig()), desks, max_concurrent_claims=2)
    wider = [c.model_copy(update={"claim_id": c.claim_id + "b"}) for c in claims]
    await parallel.review_all(wider, ctx)
    assert peak == 2  # the knob opens the gate when throughput matters
