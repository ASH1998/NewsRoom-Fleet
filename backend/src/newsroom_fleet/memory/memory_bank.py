"""Vertex AI Agent Engine Memory Bank behind the MemoryStore interface.

The editorial rule is stricter than the platform's: **only approved guidance
becomes institutional memory.** Memory Bank's usual mode — generating memories
from conversation transcripts — is exactly what this must not do, because it
would let unreviewed model output silently become house style.

So writes happen at one place only: an editor accepting a correction candidate
calls `record_approved_precedent`, and the fact is stored with the approving
editor's identity and the article it came from. Reads are retrieval with
provenance; anything retrieved without a resolvable provenance line is dropped
rather than quietly presented to the Standards Reviewer as house policy.

Scope keys partition the bank per newsroom so one outlet's precedents cannot be
retrieved into another's review.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from newsroom_fleet.config import Settings
from newsroom_fleet.memory.store import CorrectionPrecedent, HouseRule, MemoryStore

log = logging.getLogger(__name__)

MEMORY_BANK_VERSION = "memory-bank-1.0.0"

_SCOPE_NEWSROOM = "newsroom_fleet"
_TOPIC_PRECEDENT = "corrections_precedent"
_TOPIC_HOUSE_RULE = "house_rule"


class MemoryBankStore(MemoryStore):
    """MemoryStore backed by Agent Engine Memory Bank.

    House rules and precedents are materialised into the in-memory lists on
    construction so the hot review path stays synchronous and offline — the
    Standards Reviewer must not make a network call per claim.
    """

    def __init__(
        self,
        *,
        project: str,
        location: str,
        engine: str,
        seed: MemoryStore,
        newsroom: str = "default",
    ) -> None:
        import vertexai

        self._client = vertexai.Client(project=project, location=location)
        self._engine = engine
        self._newsroom = newsroom
        self.version = MEMORY_BANK_VERSION

        remote_rules, remote_precedents = self._retrieve()
        # The file-backed rules are the newsroom's ratified standards; the bank
        # adds precedents accumulated in production. Seed wins on rule_id
        # collision — a remote memory can never silently redefine a ratified rule.
        seen = {r.rule_id for r in seed.house_rules}
        super().__init__(
            house_rules=[*seed.house_rules, *(r for r in remote_rules if r.rule_id not in seen)],
            precedents=[*remote_precedents, *seed.precedents],
        )

    # ------------------------------------------------------------------ scope
    def _scope(self) -> dict[str, str]:
        return {"app": _SCOPE_NEWSROOM, "newsroom": self._newsroom}

    # ------------------------------------------------------------------- read
    def _retrieve(self) -> tuple[list[HouseRule], list[CorrectionPrecedent]]:
        try:
            memories = self._client.agent_engines.retrieve_memories(
                name=self._engine,
                scope=self._scope(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Memory Bank retrieval failed (%s); using seeded memory only", exc)
            return [], []

        rules: list[HouseRule] = []
        precedents: list[CorrectionPrecedent] = []
        for memory in memories:
            fact = self._fact_text(memory)
            record = self._parse(fact)
            if record is None:
                continue
            if record.get("topic") == _TOPIC_PRECEDENT:
                precedents.append(self._to_precedent(record))
            elif record.get("topic") == _TOPIC_HOUSE_RULE:
                rules.append(self._to_rule(record))
        log.info("Memory Bank: %d rule(s), %d precedent(s)", len(rules), len(precedents))
        return rules, precedents

    @staticmethod
    def _fact_text(memory: object) -> str:
        # The SDK returns either a memory object or a wrapper carrying one.
        inner = getattr(memory, "memory", memory)
        return getattr(inner, "fact", "") or ""

    @staticmethod
    def _parse(fact: str) -> dict | None:
        """Facts are written as JSON by this system. Anything else is not ours."""
        try:
            record = json.loads(fact)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(record, dict):
            return None
        # Provenance is mandatory. An unattributed memory is not house policy.
        if not record.get("approved_by") or not record.get("provenance"):
            log.warning("dropping Memory Bank fact without provenance: %.80s", fact)
            return None
        return record

    @staticmethod
    def _to_precedent(record: dict) -> CorrectionPrecedent:
        approved_at = record.get("approved_at")
        return CorrectionPrecedent(
            precedent_id=record.get("precedent_id", "mb_precedent"),
            style_template=record["style_template"],
            approved_by=record["approved_by"],
            approved_at=(
                datetime.fromisoformat(approved_at).astimezone(UTC)
                if approved_at
                else datetime.now(UTC)
            ),
            provenance=f"memory_bank:{record['provenance']}",
        )

    @staticmethod
    def _to_rule(record: dict) -> HouseRule:
        return HouseRule(
            rule_id=record["rule_id"],
            title=record.get("title", record["rule_id"]),
            pattern_terms=tuple(record.get("pattern_terms", ())),
            banned_terms=tuple(record.get("banned_terms", ())),
            severity=record.get("severity", "high"),
            guidance=record.get("guidance", ""),
        )

    # ------------------------------------------------------------------ write
    def record_approved_precedent(
        self,
        *,
        style_template: str,
        approved_by: str,
        article_id: str,
        watcher_id: str,
    ) -> CorrectionPrecedent | None:
        """The only write path. Called when an editor *accepts* a correction.

        Returns the precedent that was stored, or None if the write failed —
        a memory that did not persist must not appear to have persisted.
        """
        precedent = CorrectionPrecedent(
            precedent_id=f"prec_{watcher_id}",
            style_template=style_template,
            approved_by=approved_by,
            approved_at=datetime.now(UTC),
            provenance=f"editor_decision:{article_id}/{watcher_id}",
        )
        fact = json.dumps(
            {
                "topic": _TOPIC_PRECEDENT,
                "precedent_id": precedent.precedent_id,
                "style_template": style_template,
                "approved_by": approved_by,
                "approved_at": precedent.approved_at.isoformat(),
                "provenance": precedent.provenance,
            }
        )
        try:
            self._client.agent_engines.create_memory(
                name=self._engine,
                fact=fact,
                scope=self._scope(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Memory Bank write failed (%s); precedent not persisted", exc)
            return None
        self.precedents.insert(0, precedent)
        return precedent


def load_memory_bank(settings: Settings, *, seed: MemoryStore) -> MemoryStore:
    engine = settings.memory_bank_engine
    if not engine:
        raise ValueError("Memory Bank requires NRF_MEMORY_BANK_ENGINE (agent engine resource name)")
    if not settings.gcp_project:
        raise ValueError("Memory Bank requires a GCP project (NRF_GCP_PROJECT)")
    return MemoryBankStore(
        project=settings.gcp_project,
        location=settings.gcp_location,
        engine=engine,
        seed=seed,
    )
