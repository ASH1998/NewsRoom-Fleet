"""Policy router: minimum-evidence views per desk, concurrent independent review.

Routing uses the Masthead registrations to build each desk's bounded view. The
Source Verifier never sees the Data Checker's answer; quarantined sources reach
no reviewer — only screening metadata does. Claims are reviewed with bounded
concurrency (one at a time by default, so a live fleet paces its API calls and
the stream is legible); the desks within a claim run concurrently and fail
independently.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from newsroom_fleet.adapters.authoritative import AuthoritativeAdapter
from newsroom_fleet.desks.base import (
    AggregateEvidenceView,
    DataEvidenceView,
    DeskSet,
    QuarantineNotice,
    SourceEvidenceView,
    StandardsEvidenceView,
)
from newsroom_fleet.domain.contracts import (
    Article,
    Claim,
    Desk,
    SecurityDisposition,
    SecurityResult,
    Verdict,
)
from newsroom_fleet.memory.store import MemoryStore
from newsroom_fleet.observability.tracing import span
from newsroom_fleet.orchestration.queue import ReviewQueue, ReviewTask
from newsroom_fleet.orchestration.runner import DeskRunner
from newsroom_fleet.persistence.events import AuditEvent
from newsroom_fleet.persistence.repository import Repository

log = logging.getLogger(__name__)


@dataclass
class RoutingContext:
    article: Article
    security_results: list[SecurityResult]
    adapter: AuthoritativeAdapter
    memory: MemoryStore


class PolicyRouter:
    def __init__(
        self,
        repo: Repository,
        runner: DeskRunner,
        desks: DeskSet,
        *,
        max_concurrent_claims: int = 1,
    ) -> None:
        self._repo = repo
        self._runner = runner
        self._desks = desks.workers
        self._aggregator = desks.aggregator
        self._queue: ReviewQueue | None = None
        self._max_claims = max(1, max_concurrent_claims)

    def attach_queue(self, queue: ReviewQueue) -> None:
        """Route review work through a broker instead of the local event loop."""
        self._queue = queue

    def _source_view(self, claim: Claim, ctx: RoutingContext) -> SourceEvidenceView:
        verdicts_by_source = {
            r.source_id: r for r in ctx.security_results if r.source_id is not None
        }
        clean_sources: list = []
        quarantined: list[QuarantineNotice] = []
        for source_id in claim.source_refs:
            result = verdicts_by_source.get(source_id)
            if result and result.disposition is SecurityDisposition.CLEAN:
                source = next((s for s in ctx.article.sources if s.source_id == source_id), None)
                if source is not None:
                    clean_sources.append(source)
            elif result:
                quarantined.append(
                    QuarantineNotice(
                        source_id=source_id,
                        detector=result.detector,
                        policy_version=result.policy_version,
                    )
                )
        return SourceEvidenceView(
            claim=claim,
            cited_sources=tuple(clean_sources),
            quarantined=tuple(quarantined),
        )

    def _view_for(self, desk: Desk, claim: Claim, ctx: RoutingContext) -> object:
        match desk:
            case Desk.SOURCE_VERIFIER:
                return self._source_view(claim, ctx)
            case Desk.DATA_CHECKER:
                return DataEvidenceView(claim=claim, adapter=ctx.adapter)
            case Desk.STANDARDS_REVIEWER:
                return StandardsEvidenceView(
                    claim=claim,
                    house_rules=tuple(ctx.memory.house_rules),
                    precedents=tuple(ctx.memory.precedents),
                )
            case _:
                raise KeyError(f"no worker view for desk {desk}")

    async def review_claim(self, claim: Claim, ctx: RoutingContext) -> list[Verdict]:
        with span(
            "claim.review",
            **{
                "newsroom.article_id": claim.article_id,
                "newsroom.claim_id": claim.claim_id,
                "newsroom.claim_type": claim.type.value,
                "newsroom.risk_tier": claim.risk_tier.value,
                "newsroom.desks": ",".join(d.value for d in claim.required_desks),
            },
        ):
            return await self._review_claim(claim, ctx)

    async def _review_claim(self, claim: Claim, ctx: RoutingContext) -> list[Verdict]:
        self._repo.append_event(
            AuditEvent(
                event_type="claim_routed",
                article_id=claim.article_id,
                claim_id=claim.claim_id,
                actor="policy_router",
                payload={
                    "desks": [d.value for d in claim.required_desks],
                    "risk": claim.risk_tier.value,
                    "transport": self._queue.name if self._queue else "inprocess",
                },
            )
        )
        if self._queue is not None and self._dispatch(claim):
            # Verdicts arrive asynchronously via the push subscription; the
            # aggregate is recomputed as each one lands.
            return []

        verdicts = await asyncio.gather(
            *(
                self._runner.run_review(
                    self._desks[desk], desk, claim, self._view_for(desk, claim, ctx)
                )
                for desk in claim.required_desks
            )
        )
        return [*verdicts, self.aggregate_claim(claim)]

    def _dispatch(self, claim: Claim) -> bool:
        """Publish this claim's desk tasks. False means 'run it inline instead'.

        All-or-nothing per claim: a partial publish would leave the claim with
        some desks queued and some not, and the two paths would race to
        aggregate. A broker outage degrades to local execution and is audited —
        it never silently drops a desk.
        """
        assert self._queue is not None
        tasks = [
            ReviewTask(article_id=claim.article_id, claim_id=claim.claim_id, desk=desk)
            for desk in claim.required_desks
        ]
        published: list[str] = []
        for task in tasks:
            try:
                published.append(self._queue.publish(task))
            except Exception as exc:  # noqa: BLE001
                log.warning("publish failed for %s (%s); running inline", task.idempotency_key, exc)
                self._repo.append_event(
                    AuditEvent(
                        event_type="queue_degraded",
                        article_id=claim.article_id,
                        claim_id=claim.claim_id,
                        actor="policy_router",
                        payload={
                            "error": f"{type(exc).__name__}: {exc}",
                            "published_before_failure": len(published),
                            "fallback": "inprocess",
                        },
                    )
                )
                return False
        self._repo.append_event(
            AuditEvent(
                event_type="claim_dispatched",
                article_id=claim.article_id,
                claim_id=claim.claim_id,
                actor="policy_router",
                payload={
                    "queue": self._queue.name,
                    "message_ids": published,
                    "idempotency_keys": [t.idempotency_key for t in tasks],
                },
            )
        )
        return True

    async def run_task(self, claim: Claim, desk: Desk, ctx: RoutingContext) -> Verdict:
        """Execute one queued review task, then recompute the claim's aggregate."""
        verdict = await self._runner.run_review(
            self._desks[desk], desk, claim, self._view_for(desk, claim, ctx)
        )
        self.aggregate_claim(claim)
        return verdict

    def aggregate_claim(self, claim: Claim) -> Verdict:
        """Recompute the claim summary from *persisted* worker verdicts.

        Derived, never authoritative: the Editor Gate reads the worker verdicts
        themselves. Recomputing from storage is what lets desks finish in any
        order, on any machine, without the aggregator seeing partial state it
        would have to guess about — a missing desk is reported as missing.
        """
        workers = tuple(
            v
            for v in self._repo.get_article_verdicts(claim.article_id)
            if v.claim_id == claim.claim_id and v.desk is not Desk.VERDICT_AGGREGATOR
        )
        aggregate = self._aggregator.aggregate(
            AggregateEvidenceView(claim=claim, desk_verdicts=workers)
        )
        self._repo.save_verdict(aggregate)
        self._repo.append_event(
            AuditEvent(
                event_type="verdict_recorded",
                article_id=claim.article_id,
                claim_id=claim.claim_id,
                actor=Desk.VERDICT_AGGREGATOR.value,
                payload={
                    "result": aggregate.result.value,
                    "agent_version": aggregate.agent_version,
                    "desks_seen": [v.desk.value for v in workers],
                },
            )
        )
        return aggregate

    async def review_all(self, claims: list[Claim], ctx: RoutingContext) -> list[Verdict]:
        with span(
            "fleet.review_all",
            **{
                "newsroom.article_id": ctx.article.article_id,
                "newsroom.claim_count": len(claims),
                "newsroom.max_concurrent_claims": self._max_claims,
            },
        ):
            # Bounded, not all-at-once: a semaphore per call keeps live API
            # pressure predictable and makes the review stream followable.
            gate = asyncio.Semaphore(self._max_claims)

            async def bounded(claim: Claim) -> list[Verdict]:
                async with gate:
                    return await self.review_claim(claim, ctx)

            nested = await asyncio.gather(*(bounded(c) for c in claims))
        return [v for vs in nested for v in vs]
