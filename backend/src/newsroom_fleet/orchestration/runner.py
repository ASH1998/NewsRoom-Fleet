"""Async desk runner: timeout, bounded retries, idempotency, visible failure.

One worker's failure never blocks the fleet and never becomes an implicit
verification: after the retry budget, a signed ERROR verdict with
needs_human=True is persisted and audited. (Design report: "Make failure visible".)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from newsroom_fleet.domain.contracts import Claim, Desk, Verdict, VerdictResult
from newsroom_fleet.domain.masthead import registration_for
from newsroom_fleet.observability.tracing import span
from newsroom_fleet.persistence.events import AuditEvent
from newsroom_fleet.persistence.repository import Repository


@dataclass
class RunnerConfig:
    timeout_s: float = 5.0
    max_attempts: int = 2
    # Demo hook: crash every attempt of this desk so the trace shows graceful
    # degradation to NEEDS_HUMAN while the rest of the fleet completes.
    fail_desk: Desk | None = None


class DeskRunner:
    def __init__(self, repo: Repository, config: RunnerConfig) -> None:
        self._repo = repo
        self._config = config

    async def run_review(
        self, desk_impl: object, desk: Desk, claim: Claim, view: object
    ) -> Verdict:
        # Duplicate delivery protection: a persisted healthy verdict is returned
        # as-is; only a persisted ERROR verdict may be superseded by a new run.
        existing = self._repo.get_verdict(claim.claim_id, desk)
        if existing is not None and existing.result is not VerdictResult.ERROR:
            return existing

        last_error = "unknown"
        for attempt in range(1, self._config.max_attempts + 1):
            started = time.perf_counter()
            # One span per *attempt*, so the Cloud Trace waterfall shows the
            # timeout, the retry, and the escalation as separate bars.
            with span(
                f"desk.{desk.value}",
                **{
                    "newsroom.article_id": claim.article_id,
                    "newsroom.claim_id": claim.claim_id,
                    "newsroom.desk": desk.value,
                    "newsroom.attempt": attempt,
                },
            ) as current:
                try:
                    if self._config.fail_desk is desk:
                        raise RuntimeError("injected worker crash (demo hook NRF_FAIL_DESK)")
                    verdict: Verdict = await asyncio.wait_for(
                        desk_impl.review(view),
                        timeout=self._config.timeout_s,  # type: ignore[attr-defined]
                    )
                    latency = (time.perf_counter() - started) * 1000
                    current.set_attribute("newsroom.result", verdict.result.value)
                    self._repo.save_verdict(verdict)
                    self._repo.append_event(
                        AuditEvent(
                            event_type="verdict_recorded",
                            article_id=claim.article_id,
                            claim_id=claim.claim_id,
                            actor=desk.value,
                            latency_ms=round(latency, 1),
                            payload={
                                "result": verdict.result.value,
                                "attempt": attempt,
                                "agent_version": verdict.agent_version,
                                "idempotency_key": f"{claim.claim_id}:{desk.value}",
                            },
                        )
                    )
                    return verdict
                except TimeoutError:
                    last_error = f"timeout after {self._config.timeout_s}s"
                    current.set_attribute("newsroom.error", last_error)
                    self._repo.append_event(
                        AuditEvent(
                            event_type="desk_timeout",
                            article_id=claim.article_id,
                            claim_id=claim.claim_id,
                            actor=desk.value,
                            latency_ms=round((time.perf_counter() - started) * 1000, 1),
                            payload={"attempt": attempt},
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — any desk failure is a visible ERROR verdict
                    last_error = f"{type(exc).__name__}: {exc}"
                    current.record_exception(exc)
                    self._repo.append_event(
                        AuditEvent(
                            event_type="desk_error",
                            article_id=claim.article_id,
                            claim_id=claim.claim_id,
                            actor=desk.value,
                            latency_ms=round((time.perf_counter() - started) * 1000, 1),
                            payload={"attempt": attempt, "error": last_error},
                        )
                    )

        verdict = Verdict(
            verdict_id=f"vrd_{uuid4().hex[:12]}",
            article_id=claim.article_id,
            claim_id=claim.claim_id,
            desk=desk,
            agent_version=registration_for(desk).agent_version,
            result=VerdictResult.ERROR,
            confidence=0.0,
            needs_human=True,
            reason=f"{desk.value} failed after {self._config.max_attempts} attempt(s)",
            error_detail=last_error,
            created_at=datetime.now(UTC),
        )
        self._repo.save_verdict(verdict)
        self._repo.append_event(
            AuditEvent(
                event_type="worker_failed_needs_human",
                article_id=claim.article_id,
                claim_id=claim.claim_id,
                actor=desk.value,
                payload={"attempts": self._config.max_attempts, "error": last_error},
            )
        )
        return verdict
