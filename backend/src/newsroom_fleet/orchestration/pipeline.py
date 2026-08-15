"""FleetService: the end-to-end pipeline over durable state.

Intake → screen (quarantine before orchestration) → extract claims → route
minimum evidence → review concurrently → aggregate → evaluate the Editor Gate
over persisted verdicts. Publishing is a server-side, identity-enforced policy
decision; the watcher resumes published claims from persisted snapshots.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from newsroom_fleet.adapters.authoritative import (
    AuthoritativeAdapter,
    load_fixture_adapter,
)
from newsroom_fleet.config import FIXTURES_DIR, Settings
from newsroom_fleet.desks.base import DeskSet, WatcherEvidenceView
from newsroom_fleet.desks.factory import fixture_desk_set
from newsroom_fleet.domain.contracts import (
    Article,
    ClaimSnapshot,
    ClaimType,
    Desk,
    EditorDecision,
    EditorDisposition,
    Role,
    SecurityDisposition,
    Verdict,
    WatcherResult,
)
from newsroom_fleet.domain.policy import PublishDecision, decide_publish, evaluate_gate
from newsroom_fleet.domain.state_machine import PublicationState, transition
from newsroom_fleet.fixtures.loader import load_golden_article
from newsroom_fleet.memory.store import MemoryStore, load_memory
from newsroom_fleet.observability.tracing import span
from newsroom_fleet.orchestration.queue import ReviewQueue, ReviewTask
from newsroom_fleet.orchestration.router import PolicyRouter, RoutingContext
from newsroom_fleet.orchestration.runner import DeskRunner, RunnerConfig
from newsroom_fleet.persistence.events import AuditEvent
from newsroom_fleet.persistence.repository import Repository
from newsroom_fleet.security.screening import Screener, screen_submission


class SubmissionRejectedError(Exception):
    pass


class ArticleNotFoundError(Exception):
    pass


class IdentityDeniedError(Exception):
    pass


class NotPublishableError(Exception):
    def __init__(self, decision: PublishDecision) -> None:
        super().__init__("; ".join(decision.denials))
        self.decision = decision


class FleetService:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        screener: Screener,
        memory: MemoryStore | None = None,
        desks: DeskSet | None = None,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.screener = screener
        self.memory = memory or load_memory(FIXTURES_DIR / "house_rules.json")
        self.desks = desks or fixture_desk_set()
        self._extractor = self.desks.extractor
        self._watcher = self.desks.watcher
        self._adapter_version = settings.authoritative_dataset
        self.adapter = self._load_adapter(self._adapter_version)
        self.runner = DeskRunner(
            repo,
            RunnerConfig(
                timeout_s=settings.desk_timeout_s,
                max_attempts=settings.desk_max_attempts,
                fail_desk=Desk(settings.fail_desk) if settings.fail_desk else None,
            ),
        )
        self.router = PolicyRouter(repo, self.runner, self.desks)

    # ------------------------------------------------------------ plumbing
    def attach_queue(self, queue: ReviewQueue) -> None:
        """Move review execution onto a broker. Everything else is unchanged:
        same bounded views, same idempotency keys, same gate."""
        self.router.attach_queue(queue)

    async def handle_review_task(self, task: ReviewTask) -> Verdict:
        """Execute one queued (claim, desk) task and re-evaluate the gate.

        Rebuilding the routing context from durable state — rather than
        trusting anything in the message — is what keeps the evidence boundary
        intact across the network hop: the message names a claim and a desk, and
        the router still decides what that desk is allowed to see.
        """
        article, _, _ = self._require_article(task.article_id)
        claim = next(
            (c for c in self.repo.get_claims(task.article_id) if c.claim_id == task.claim_id),
            None,
        )
        if claim is None:
            raise ArticleNotFoundError(f"{task.article_id}/{task.claim_id}")
        if task.desk not in claim.required_desks:
            raise IdentityDeniedError(
                f"{task.desk.value} is not a required desk for {task.claim_id}"
            )
        ctx = RoutingContext(
            article=article,
            security_results=self.repo.get_security_results(task.article_id),
            adapter=self.adapter,
            memory=self.memory,
        )
        verdict = await self.router.run_task(claim, task.desk, ctx)
        self._refresh_gate(task.article_id)
        return verdict

    def _load_adapter(self, version: str) -> AuthoritativeAdapter:
        return load_fixture_adapter(FIXTURES_DIR / "authoritative_data.json", version)

    def _audit(self, event_type: str, article_id: str, actor: str = "system", **payload) -> None:
        self.repo.append_event(
            AuditEvent(event_type=event_type, article_id=article_id, actor=actor, payload=payload)
        )

    def _transition(self, article_id: str, target: PublicationState) -> PublicationState:
        row = self.repo.get_article(article_id)
        if row is None:
            raise ArticleNotFoundError(article_id)
        _, current, _ = row
        new_state = transition(current, target)  # raises on illegal transition
        self.repo.set_state(article_id, new_state)
        self._audit(
            "state_transition",
            article_id,
            **{"from": current.value, "to": new_state.value},
        )
        return new_state

    def _require_article(self, article_id: str) -> tuple[Article, PublicationState, str | None]:
        row = self.repo.get_article(article_id)
        if row is None:
            raise ArticleNotFoundError(article_id)
        return row

    # ------------------------------------------------------------- pipeline
    async def submit_article(self, article: Article, actor: str) -> str:
        with span(
            "intake.submit",
            **{
                "newsroom.article_id": article.article_id,
                "newsroom.actor": actor,
                "newsroom.source_count": len(article.sources),
            },
        ):
            return await self._submit_article(article, actor)

    async def _submit_article(self, article: Article, actor: str) -> str:
        self.repo.save_article(article, PublicationState.DRAFT)
        self._audit("intake_received", article.article_id, actor=actor, title=article.title)

        # Screening happens before any orchestration; quarantined content is
        # never routed to a desk.
        with span("intake.screen", **{"newsroom.article_id": article.article_id}):
            security = screen_submission(
                self.screener, article.article_id, article.body, article.sources
            )
        self.repo.save_security_results(security)
        for result in security:
            self._audit(
                "source_screened" if result.source_id else "body_screened",
                article.article_id,
                actor="intake_gateway",
                source_id=result.source_id,
                disposition=result.disposition.value,
                detector=result.detector,
                policy_version=result.policy_version,
                source_hash=result.source_hash,
            )
            if result.disposition is not SecurityDisposition.CLEAN:
                self._audit(
                    "source_quarantined" if result.source_id else "body_rejected",
                    article.article_id,
                    actor="intake_gateway",
                    source_id=result.source_id,
                    detector=result.detector,
                )

        body_result = security[0]
        if body_result.disposition is SecurityDisposition.BLOCKED:
            raise SubmissionRejectedError(body_result.detector_detail)

        self._transition(article.article_id, PublicationState.REVIEWING)

        with span(
            "extract.claims",
            **{
                "newsroom.article_id": article.article_id,
                "newsroom.agent_version": self._extractor.agent_version,
            },
        ) as current:
            extraction = await self._extractor.extract(article.article_id, article.body)
            current.set_attribute("newsroom.claim_count", len(extraction.claims))
        self.repo.save_claims(extraction.claims)
        self._audit(
            "claims_extracted",
            article.article_id,
            actor=Desk.CLAIM_EXTRACTOR.value,
            claims=[
                {
                    "claim_id": c.claim_id,
                    "type": c.type.value,
                    "desks": [d.value for d in c.required_desks],
                }
                for c in extraction.claims
            ],
            agent_version=self._extractor.agent_version,
        )

        ctx = RoutingContext(
            article=article,
            security_results=security,
            adapter=self.adapter,
            memory=self.memory,
        )
        await self.router.review_all(extraction.claims, ctx)
        self._refresh_gate(article.article_id)
        return article.article_id

    def _refresh_gate(self, article_id: str) -> PublicationState:
        with span("gate.evaluate", **{"newsroom.article_id": article_id}) as current_span:
            state = self._refresh_gate_inner(article_id)
            current_span.set_attribute("newsroom.gate_state", state.value)
            return state

    def _outstanding_desks(self, article_id: str) -> int:
        """Required (claim, desk) pairs with no persisted verdict yet.

        Non-zero only while queued review tasks are still in flight. It is a
        progress signal, never an approval signal: a claim with no verdict is
        already NEEDS_HUMAN as far as the gate is concerned.
        """
        recorded = {(v.claim_id, v.desk) for v in self.repo.get_article_verdicts(article_id)}
        return sum(
            1
            for claim in self.repo.get_claims(article_id)
            for desk in claim.required_desks
            if (claim.claim_id, desk) not in recorded
        )

    def _refresh_gate_inner(self, article_id: str) -> PublicationState:
        _, current, _ = self._require_article(article_id)
        claims = self.repo.get_claims(article_id)
        verdicts = self.repo.get_article_verdicts(article_id)
        gate = evaluate_gate(article_id, claims, verdicts)
        outstanding = self._outstanding_desks(article_id)

        # REVIEWING means "claim tasks are active" (report state table). While
        # queued tasks are outstanding the article stays REVIEWING rather than
        # flapping into HUMAN_REVIEW on every partially-delivered verdict.
        settled = outstanding == 0
        if (
            settled
            and current
            in (
                PublicationState.REVIEWING,
                PublicationState.HUMAN_REVIEW,
                PublicationState.EDITOR_READY,
            )
            and gate.state is not current
        ):
            self._transition(article_id, gate.state)
        self._audit(
            "editor_gate_evaluated",
            article_id,
            actor="editor_gate",
            state=gate.state.value,
            blocked_claims=gate.blocked_claim_ids,
            outstanding_desks=outstanding,
        )
        return gate.state

    async def re_review(self, article_id: str) -> None:
        """HUMAN_REVIEW -> REVIEWING: retry failed desks (ERROR verdicts only)."""
        article, current, _ = self._require_article(article_id)
        if current is not PublicationState.HUMAN_REVIEW:
            return
        self._transition(article_id, PublicationState.REVIEWING)
        security = self.repo.get_security_results(article_id)
        claims = self.repo.get_claims(article_id)
        ctx = RoutingContext(
            article=article, security_results=security, adapter=self.adapter, memory=self.memory
        )
        await self.router.review_all(claims, ctx)
        self._refresh_gate(article_id)

    # ------------------------------------------------------------ authority
    def record_decision(
        self,
        article_id: str,
        *,
        actor: str,
        role: Role,
        disposition: EditorDisposition,
        rationale: str,
        revised_text: str | None,
        resolved_verdict_ids: list[str],
    ) -> EditorDecision:
        self._require_article(article_id)
        # Identity policy: only an editor records editorial decisions.
        if role is not Role.EDITOR:
            self._audit(
                "decision_denied",
                article_id,
                actor=actor,
                role=role.value,
                reason="reporter cannot record editorial decisions",
            )
            raise IdentityDeniedError("reporter cannot record editorial decisions")

        known = {v.verdict_id for v in self.repo.get_article_verdicts(article_id)}
        decision = EditorDecision(
            decision_id=f"dec_{uuid4().hex[:12]}",
            article_id=article_id,
            actor=actor,
            role=role,
            disposition=disposition,
            rationale=rationale,
            revised_text=revised_text,
            resolved_verdict_ids=[v for v in resolved_verdict_ids if v in known],
            created_at=datetime.now(UTC),
        )
        self.repo.save_decision(decision)
        self._audit(
            "editor_decision_recorded",
            article_id,
            actor=actor,
            decision_id=decision.decision_id,
            disposition=disposition.value,
            resolved=decision.resolved_verdict_ids,
        )
        return decision

    def publish(
        self, article_id: str, *, actor: str, role: Role, decision_id: str | None
    ) -> PublishDecision:
        with span(
            "gate.publish",
            **{
                "newsroom.article_id": article_id,
                "newsroom.actor": actor,
                "newsroom.role": role.value,
            },
        ) as current_span:
            outcome = self._publish(article_id, actor=actor, role=role, decision_id=decision_id)
            current_span.set_attribute("newsroom.publish_allowed", outcome.allowed)
            if outcome.denials:
                current_span.set_attribute("newsroom.denials", "; ".join(outcome.denials))
            return outcome

    def _publish(
        self, article_id: str, *, actor: str, role: Role, decision_id: str | None
    ) -> PublishDecision:
        article, current, _ = self._require_article(article_id)
        decision = self.repo.get_decision(decision_id) if decision_id else None
        gate = evaluate_gate(
            article_id, self.repo.get_claims(article_id), self.repo.get_article_verdicts(article_id)
        )
        outcome = decide_publish(role=role, gate=gate, editor_decision=decision)

        if current in (
            PublicationState.PUBLISHED,
            PublicationState.RECHECK_PENDING,
            PublicationState.CORRECTION_CANDIDATE,
            PublicationState.EDITOR_APPROVED,
        ):
            outcome = PublishDecision(
                allowed=False, denials=[*outcome.denials, f"state is {current.value}"]
            )

        if not outcome.allowed:
            self._audit(
                "publish_denied", article_id, actor=actor, role=role.value, denials=outcome.denials
            )
            return outcome

        # Deterministic policy satisfied: advance the state machine stepwise.
        if current is PublicationState.HUMAN_REVIEW:
            self._transition(article_id, PublicationState.EDITOR_READY)
        self._transition(article_id, PublicationState.EDITOR_APPROVED)
        self._transition(article_id, PublicationState.PUBLISHED)

        safe_text = (decision.revised_text if decision else None) or article.body
        self.repo.set_published_text(article_id, safe_text)
        self._snapshot_numeric_claims(article_id)
        self._audit(
            "publish_approved",
            article_id,
            actor=actor,
            decision_id=decision.decision_id if decision else None,
        )
        return outcome

    def _snapshot_numeric_claims(self, article_id: str) -> None:
        claims = self.repo.get_claims(article_id)
        for claim in claims:
            if claim.type is not ClaimType.NUMERIC:
                continue
            record = self.adapter.lookup(claim.text)
            if record is None:
                continue
            snapshot = ClaimSnapshot(
                article_id=article_id,
                claim_id=claim.claim_id,
                claim_text=claim.text,
                adapter_key=record.key,
                published_value=record.value,
                locator=record.locator,
                recorded_at=datetime.now(UTC),
            )
            self.repo.save_snapshot(snapshot)
            self._audit(
                "snapshot_recorded",
                article_id,
                claim_id=claim.claim_id,
                adapter_key=record.key,
                value=record.value,
                locator=record.locator,
            )

    # -------------------------------------------------------------- watcher
    def recheck(self, article_id: str, *, actor: str) -> list[WatcherResult]:
        with span(
            "watcher.recheck",
            **{
                "newsroom.article_id": article_id,
                "newsroom.actor": actor,
                "newsroom.adapter": self.adapter.name,
            },
        ) as current_span:
            candidates = self._recheck(article_id, actor=actor)
            current_span.set_attribute("newsroom.candidate_count", len(candidates))
            return candidates

    def _recheck(self, article_id: str, *, actor: str) -> list[WatcherResult]:
        self._require_article(article_id)
        self._transition(article_id, PublicationState.RECHECK_PENDING)
        self._audit("recheck_triggered", article_id, actor=actor, adapter=self.adapter.name)

        candidates: list[WatcherResult] = []
        for snapshot in self.repo.get_snapshots(article_id):
            view = WatcherEvidenceView(
                article_id=snapshot.article_id,
                claim_id=snapshot.claim_id,
                claim_text=snapshot.claim_text,
                adapter_key=snapshot.adapter_key,
                published_value=snapshot.published_value,
                published_locator=snapshot.locator,
            )
            result = self._watcher.check(
                view, adapter=self.adapter, precedent=self.memory.correction_style()
            )
            if result is None:
                self._audit(
                    "watcher_no_change",
                    article_id,
                    actor=Desk.CORRECTIONS_WATCHER.value,
                    claim_id=snapshot.claim_id,
                    adapter_key=snapshot.adapter_key,
                )
                continue
            self.repo.save_watcher_result(result)
            candidates.append(result)
            self._audit(
                "watcher_candidate_created",
                article_id,
                actor=Desk.CORRECTIONS_WATCHER.value,
                claim_id=snapshot.claim_id,
                watcher_id=result.watcher_id,
                prior=result.prior_value,
                current=result.current_value,
            )

        self._transition(
            article_id,
            PublicationState.CORRECTION_CANDIDATE if candidates else PublicationState.PUBLISHED,
        )
        return candidates

    def dispose_correction(
        self,
        article_id: str,
        watcher_id: str,
        *,
        actor: str,
        role: Role,
        accept: bool,
        rationale: str,
        corrected_text: str | None = None,
    ) -> None:
        self._require_article(article_id)
        if role is not Role.EDITOR:
            raise IdentityDeniedError("only an editor disposes a correction candidate")
        decision = EditorDecision(
            decision_id=f"dec_{uuid4().hex[:12]}",
            article_id=article_id,
            actor=actor,
            role=role,
            disposition=EditorDisposition.APPROVE if accept else EditorDisposition.SEND_BACK,
            rationale=rationale,
            revised_text=corrected_text if accept else None,
            resolved_verdict_ids=[],
            created_at=datetime.now(UTC),
        )
        self.repo.save_decision(decision)
        self.repo.dispose_watcher_result(watcher_id)
        if accept and corrected_text:
            self.repo.set_published_text(article_id, corrected_text)
            self._snapshot_numeric_claims(article_id)
        self._transition(article_id, PublicationState.PUBLISHED)
        self._audit(
            "correction_disposed",
            article_id,
            actor=actor,
            watcher_id=watcher_id,
            accepted=accept,
        )
        if accept:
            self._remember_correction(article_id, watcher_id, actor)

    def _remember_correction(self, article_id: str, watcher_id: str, actor: str) -> None:
        """An editor-accepted correction is the *only* thing that becomes memory.

        Unreviewed model output never enters the corrections ledger; the write
        is attributed to the approving editor and the decision it came from.
        """
        record = getattr(self.memory, "record_approved_precedent", None)
        if record is None:  # file-backed memory is read-only
            return
        candidate = next(
            (w for w in self.repo.get_watcher_results(article_id) if w.watcher_id == watcher_id),
            None,
        )
        if candidate is None:
            return
        stored = record(
            style_template=candidate.candidate_language,
            approved_by=actor,
            article_id=article_id,
            watcher_id=watcher_id,
        )
        self._audit(
            "precedent_remembered" if stored else "precedent_write_failed",
            article_id,
            actor=actor,
            watcher_id=watcher_id,
            precedent_id=stored.precedent_id if stored else None,
        )

    # ----------------------------------------------------------------- demo
    async def load_golden(self, *, reset: bool = True) -> str:
        if reset:
            self.repo.reset()
        article = load_golden_article()
        return await self.submit_article(article, actor="demo:golden")

    def set_fail_desk(self, desk: Desk | None) -> None:
        self.runner._config.fail_desk = desk
        self._audit("demo_fail_desk_set", "system", desk=desk.value if desk else None)

    def advance_authoritative_data(self) -> str:
        self._adapter_version = "v2" if self._adapter_version == "v1" else "v1"
        self.adapter = self._load_adapter(self._adapter_version)
        self._audit(
            "authoritative_data_advanced",
            "system",
            dataset=self._adapter_version,
            adapter=self.adapter.name,
        )
        return self._adapter_version

    # ----------------------------------------------------------------- views
    def article_view(self, article_id: str) -> dict:
        article, state, published_text = self._require_article(article_id)
        claims = self.repo.get_claims(article_id)
        verdicts = self.repo.get_article_verdicts(article_id)
        gate = evaluate_gate(article_id, claims, verdicts)
        gate_dump = json.loads(gate.model_dump_json())
        gate_dump["blocked_claim_ids"] = gate.blocked_claim_ids
        gate_dump["blocking_verdict_ids"] = gate.blocking_verdict_ids
        return {
            "article": json.loads(article.model_dump_json()),
            "state": state.value,
            "published_text": published_text,
            "claims": [json.loads(c.model_dump_json()) for c in claims],
            "verdicts": [json.loads(v.model_dump_json()) for v in verdicts],
            "security_results": [
                json.loads(s.model_dump_json()) for s in self.repo.get_security_results(article_id)
            ],
            "decisions": [
                json.loads(d.model_dump_json()) for d in self.repo.get_decisions(article_id)
            ],
            "snapshots": [
                json.loads(s.model_dump_json()) for s in self.repo.get_snapshots(article_id)
            ],
            "watcher_results": [
                json.loads(w.model_dump_json()) for w in self.repo.get_watcher_results(article_id)
            ],
            "gate": gate_dump,
        }
