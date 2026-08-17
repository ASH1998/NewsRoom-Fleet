"""Firestore repository — the cloud implementation behind the same protocol.

Storage layout mirrors SQLite: Pydantic models are persisted as JSON strings,
with only the lookup keys and state promoted to real fields. Two deliberate
constraints shape it:

**No composite indexes.** Every query uses a single equality filter and is
ordered in Python. A judge can point `NRF_REPOSITORY=firestore` at an empty
default database and it works immediately — no `firestore.indexes.json`, no
"this query requires an index" error mid-demo.

**Idempotency lives in the write.** `save_verdict` runs a transaction that
refuses to overwrite a healthy verdict for a (claim, desk) pair — the same rule
the SQLite `ON CONFLICT ... WHERE result = 'error'` clause encodes. That is what
makes Pub/Sub's at-least-once delivery safe: the guarantee is in storage, not in
the caller.
"""

from __future__ import annotations

import json
import time
from typing import Any

from newsroom_fleet.domain.contracts import (
    Article,
    Claim,
    ClaimSnapshot,
    Desk,
    EditorDecision,
    SecurityResult,
    Verdict,
    VerdictResult,
    WatcherResult,
    WatcherStatus,
)
from newsroom_fleet.domain.state_machine import PublicationState
from newsroom_fleet.persistence.events import AuditEvent


def _seq() -> int:
    """Monotonic-enough insertion order stamp (SQLite's rowid equivalent)."""
    return time.time_ns()


class FirestoreRepository:
    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        prefix: str = "newsroom_fleet",
    ) -> None:
        from google.cloud import firestore

        self._client = firestore.Client(project=project, database=database)
        self._prefix = prefix
        self._transaction_factory = self._client.transaction
        # Touch the backend now so bootstrap can fall back to SQLite on a
        # missing database or missing credentials, rather than failing later
        # in the middle of an article submission.
        next(self._col("articles").limit(1).stream(), None)

    # ------------------------------------------------------------------ util
    def _col(self, name: str):
        return self._client.collection(f"{self._prefix}_{name}")

    def _by_article(self, name: str, article_id: str) -> list[dict[str, Any]]:
        """Single equality filter only — deliberately index-free (see module doc)."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        docs = self._col(name).where(filter=FieldFilter("article_id", "==", article_id)).stream()
        return [d.to_dict() for d in docs]

    @staticmethod
    def _ordered(rows: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda r: tuple(r.get(k) or 0 for k in keys))

    # -------------------------------------------------------------- articles
    def save_article(self, article: Article, state: PublicationState) -> None:
        ref = self._col("articles").document(article.article_id)
        existing = ref.get()
        ref.set(
            {
                "article_id": article.article_id,
                "state": state.value,
                "json": article.model_dump_json(),
                "seq": existing.to_dict().get("seq") if existing.exists else _seq(),
            },
            merge=True,
        )

    def get_article(self, article_id: str) -> tuple[Article, PublicationState, str | None] | None:
        doc = self._col("articles").document(article_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        return (
            Article.model_validate_json(data["json"]),
            PublicationState(data["state"]),
            data.get("published_text"),
        )

    def list_articles(self) -> list[str]:
        rows = [d.to_dict() for d in self._col("articles").stream()]
        return [r["article_id"] for r in self._ordered(rows, "seq")]

    def set_state(self, article_id: str, state: PublicationState) -> None:
        self._col("articles").document(article_id).update({"state": state.value})

    def set_published_text(self, article_id: str, text: str) -> None:
        self._col("articles").document(article_id).update({"published_text": text})

    # ---------------------------------------------------------------- claims
    def save_claims(self, claims: list[Claim]) -> None:
        batch = self._client.batch()
        for claim in claims:
            batch.set(
                self._col("claims").document(f"{claim.article_id}__{claim.claim_id}"),
                {
                    "article_id": claim.article_id,
                    "claim_id": claim.claim_id,
                    "json": claim.model_dump_json(),
                },
            )
        batch.commit()

    def get_claims(self, article_id: str) -> list[Claim]:
        rows = sorted(self._by_article("claims", article_id), key=lambda r: r["claim_id"])
        return [Claim.model_validate_json(r["json"]) for r in rows]

    # --------------------------------------------------------------- verdicts
    def save_verdict(self, verdict_: Verdict) -> bool:
        """True if written. False when a healthy verdict already holds the slot.

        Transactional so concurrent Pub/Sub deliveries of the same task cannot
        both write. The aggregator's summary is derived, not a reviewer result,
        so it is always recomputed.
        """
        from google.cloud import firestore

        ref = self._col("verdicts").document(
            f"{verdict_.article_id}__{verdict_.claim_id}__{verdict_.desk.value}"
        )
        payload = {
            "article_id": verdict_.article_id,
            "claim_id": verdict_.claim_id,
            "desk": verdict_.desk.value,
            "result": verdict_.result.value,
            "json": verdict_.model_dump_json(),
        }

        @firestore.transactional
        def _write(transaction) -> bool:
            snapshot = ref.get(transaction=transaction)
            if snapshot.exists:
                current = snapshot.to_dict()
                superseding_error = current.get("result") == VerdictResult.ERROR.value
                derived = verdict_.desk is Desk.VERDICT_AGGREGATOR
                if not superseding_error and not derived:
                    return False
            transaction.set(ref, payload)
            return True

        return _write(self._transaction_factory())

    def get_verdict(self, article_id: str, claim_id: str, desk: str) -> Verdict | None:
        desk_value = desk.value if isinstance(desk, Desk) else str(desk)
        doc = self._col("verdicts").document(f"{article_id}__{claim_id}__{desk_value}").get()
        return Verdict.model_validate_json(doc.to_dict()["json"]) if doc.exists else None

    def get_article_verdicts(self, article_id: str) -> list[Verdict]:
        rows = sorted(
            self._by_article("verdicts", article_id),
            key=lambda r: (r["claim_id"], r["desk"]),
        )
        return [Verdict.model_validate_json(r["json"]) for r in rows]

    # -------------------------------------------------------- security results
    def save_security_results(self, results: list[SecurityResult]) -> None:
        batch = self._client.batch()
        for result in results:
            batch.set(
                self._col("security").document(result.security_id),
                {
                    "article_id": result.article_id,
                    "source_id": result.source_id,
                    "json": result.model_dump_json(),
                    "seq": _seq(),
                },
            )
        batch.commit()

    def get_security_results(self, article_id: str) -> list[SecurityResult]:
        rows = self._ordered(self._by_article("security", article_id), "seq")
        return [SecurityResult.model_validate_json(r["json"]) for r in rows]

    # -------------------------------------------------------------- decisions
    def save_decision(self, decision: EditorDecision) -> None:
        self._col("decisions").document(decision.decision_id).set(
            {
                "article_id": decision.article_id,
                "json": decision.model_dump_json(),
                "seq": _seq(),
            }
        )

    def get_decision(self, decision_id: str) -> EditorDecision | None:
        doc = self._col("decisions").document(decision_id).get()
        return EditorDecision.model_validate_json(doc.to_dict()["json"]) if doc.exists else None

    def get_decisions(self, article_id: str) -> list[EditorDecision]:
        rows = self._ordered(self._by_article("decisions", article_id), "seq")
        return [EditorDecision.model_validate_json(r["json"]) for r in rows]

    # -------------------------------------------------------------- snapshots
    def save_snapshot(self, snapshot: ClaimSnapshot) -> None:
        self._col("snapshots").document(f"{snapshot.article_id}__{snapshot.claim_id}").set(
            {
                "article_id": snapshot.article_id,
                "claim_id": snapshot.claim_id,
                "json": snapshot.model_dump_json(),
            }
        )

    def get_snapshots(self, article_id: str) -> list[ClaimSnapshot]:
        rows = sorted(self._by_article("snapshots", article_id), key=lambda r: r["claim_id"])
        return [ClaimSnapshot.model_validate_json(r["json"]) for r in rows]

    # ---------------------------------------------------------- watcher results
    def save_watcher_result(self, result: WatcherResult) -> None:
        self._col("watcher").document(result.watcher_id).set(
            {
                "article_id": result.article_id,
                "claim_id": result.claim_id,
                "status": result.status.value,
                "json": result.model_dump_json(),
                "seq": _seq(),
            }
        )

    def get_watcher_results(self, article_id: str) -> list[WatcherResult]:
        rows = self._ordered(self._by_article("watcher", article_id), "seq")
        return [WatcherResult.model_validate_json(r["json"]) for r in rows]

    def dispose_watcher_result(self, watcher_id: str) -> None:
        ref = self._col("watcher").document(watcher_id)
        doc = ref.get()
        if not doc.exists:
            return
        result = WatcherResult.model_validate_json(doc.to_dict()["json"])
        disposed = result.model_copy(update={"status": WatcherStatus.DISPOSED})
        ref.update({"status": disposed.status.value, "json": disposed.model_dump_json()})

    # ----------------------------------------------------------------- events
    def append_event(self, event: AuditEvent) -> None:
        # Append-only: a fresh document per event, never an update.
        self._col("events").document(event.event_id).set(
            {
                "article_id": event.article_id,
                "claim_id": event.claim_id,
                "ts": event.ts.isoformat(),
                "seq": _seq(),
                "json": json.dumps(event.to_dict()),
            }
        )

    def get_events(self, article_id: str) -> list[AuditEvent]:
        rows = sorted(self._by_article("events", article_id), key=lambda r: (r["ts"], r["seq"]))
        return [AuditEvent.from_dict(json.loads(r["json"])) for r in rows]

    # ------------------------------------------------------------------- demo
    def reset(self) -> None:
        for name in (
            "articles",
            "claims",
            "verdicts",
            "security",
            "decisions",
            "snapshots",
            "watcher",
            "events",
        ):
            collection = self._col(name)
            while True:
                docs = list(collection.limit(400).stream())
                if not docs:
                    break
                batch = self._client.batch()
                for doc in docs:
                    batch.delete(doc.reference)
                batch.commit()

    def close(self) -> None:
        self._client.close()
