"""SQLite repository — the local implementation behind the Repository protocol.

Models are stored as JSON blobs (they are Pydantic models; schema columns are
kept only for lookup keys and state). Verdicts use
INSERT ... ON CONFLICT (claim_id, desk) DO UPDATE only over ERROR rows, which
encodes idempotency in the storage layer itself.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    published_text TEXT,
    json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    article_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    json TEXT NOT NULL,
    PRIMARY KEY (article_id, claim_id)
);
CREATE TABLE IF NOT EXISTS verdicts (
    article_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    desk TEXT NOT NULL,
    result TEXT NOT NULL,
    json TEXT NOT NULL,
    PRIMARY KEY (article_id, claim_id, desk)
);
CREATE TABLE IF NOT EXISTS security_results (
    security_id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    source_id TEXT,
    json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    article_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    json TEXT NOT NULL,
    PRIMARY KEY (article_id, claim_id)
);
CREATE TABLE IF NOT EXISTS watcher_results (
    watcher_id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL,
    json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    claim_id TEXT,
    ts TEXT NOT NULL,
    json TEXT NOT NULL
);
"""


class SQLiteRepository:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ util
    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    # -------------------------------------------------------------- articles
    def save_article(self, article: Article, state: PublicationState) -> None:
        self._execute(
            "INSERT INTO articles(article_id, state, json) VALUES (?, ?, ?) "
            "ON CONFLICT(article_id) DO UPDATE SET json=excluded.json, state=excluded.state",
            (article.article_id, state.value, article.model_dump_json()),
        )

    def get_article(self, article_id: str) -> tuple[Article, PublicationState, str | None] | None:
        rows = self._query(
            "SELECT json, state, published_text FROM articles WHERE article_id=?",
            (article_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return (
            Article.model_validate_json(row["json"]),
            PublicationState(row["state"]),
            row["published_text"],
        )

    def list_articles(self) -> list[str]:
        return [
            r["article_id"] for r in self._query("SELECT article_id FROM articles ORDER BY rowid")
        ]

    def set_state(self, article_id: str, state: PublicationState) -> None:
        self._execute("UPDATE articles SET state=? WHERE article_id=?", (state.value, article_id))

    def set_published_text(self, article_id: str, text: str) -> None:
        self._execute("UPDATE articles SET published_text=? WHERE article_id=?", (text, article_id))

    # ---------------------------------------------------------------- claims
    def save_claims(self, claims: list[Claim]) -> None:
        for claim in claims:
            self._execute(
                "INSERT INTO claims(article_id, claim_id, json) VALUES (?, ?, ?) "
                "ON CONFLICT(article_id, claim_id) DO UPDATE SET json=excluded.json",
                (claim.article_id, claim.claim_id, claim.model_dump_json()),
            )

    def get_claims(self, article_id: str) -> list[Claim]:
        return [
            Claim.model_validate_json(r["json"])
            for r in self._query(
                "SELECT json FROM claims WHERE article_id=? ORDER BY claim_id", (article_id,)
            )
        ]

    # --------------------------------------------------------------- verdicts
    def save_verdict(self, verdict_: Verdict) -> bool:
        """True if inserted/replaced; False if an equivalent healthy verdict already exists."""
        result = self._execute(
            """
            INSERT INTO verdicts(article_id, claim_id, desk, result, json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(article_id, claim_id, desk) DO UPDATE SET
                json=excluded.json, result=excluded.result
            WHERE verdicts.result = ? OR verdicts.desk = ?
            """,
            (
                verdict_.article_id,
                verdict_.claim_id,
                verdict_.desk.value,
                verdict_.result.value,
                verdict_.model_dump_json(),
                VerdictResult.ERROR.value,
                Desk.VERDICT_AGGREGATOR.value,  # derived summary: always recomputed
            ),
        )
        return result.rowcount > 0

    def get_verdict(self, article_id: str, claim_id: str, desk: str) -> Verdict | None:
        rows = self._query(
            "SELECT json FROM verdicts WHERE article_id=? AND claim_id=? AND desk=?",
            (article_id, claim_id, desk),
        )
        return Verdict.model_validate_json(rows[0]["json"]) if rows else None

    def get_article_verdicts(self, article_id: str) -> list[Verdict]:
        return [
            Verdict.model_validate_json(r["json"])
            for r in self._query(
                "SELECT json FROM verdicts WHERE article_id=? ORDER BY claim_id, desk",
                (article_id,),
            )
        ]

    # -------------------------------------------------------- security results
    def save_security_results(self, results: list[SecurityResult]) -> None:
        for result in results:
            self._execute(
                "INSERT OR REPLACE INTO security_results(security_id, article_id, source_id, json) "
                "VALUES (?, ?, ?, ?)",
                (result.security_id, result.article_id, result.source_id, result.model_dump_json()),
            )

    def get_security_results(self, article_id: str) -> list[SecurityResult]:
        return [
            SecurityResult.model_validate_json(r["json"])
            for r in self._query(
                "SELECT json FROM security_results WHERE article_id=? ORDER BY rowid", (article_id,)
            )
        ]

    # -------------------------------------------------------------- decisions
    def save_decision(self, decision: EditorDecision) -> None:
        self._execute(
            "INSERT INTO decisions(decision_id, article_id, json) VALUES (?, ?, ?)",
            (decision.decision_id, decision.article_id, decision.model_dump_json()),
        )

    def get_decision(self, decision_id: str) -> EditorDecision | None:
        rows = self._query("SELECT json FROM decisions WHERE decision_id=?", (decision_id,))
        return EditorDecision.model_validate_json(rows[0]["json"]) if rows else None

    def get_decisions(self, article_id: str) -> list[EditorDecision]:
        return [
            EditorDecision.model_validate_json(r["json"])
            for r in self._query(
                "SELECT json FROM decisions WHERE article_id=? ORDER BY rowid", (article_id,)
            )
        ]

    # -------------------------------------------------------------- snapshots
    def save_snapshot(self, snapshot: ClaimSnapshot) -> None:
        self._execute(
            "INSERT INTO snapshots(article_id, claim_id, json) VALUES (?, ?, ?) "
            "ON CONFLICT(article_id, claim_id) DO UPDATE SET json=excluded.json",
            (snapshot.article_id, snapshot.claim_id, snapshot.model_dump_json()),
        )

    def get_snapshots(self, article_id: str) -> list[ClaimSnapshot]:
        return [
            ClaimSnapshot.model_validate_json(r["json"])
            for r in self._query(
                "SELECT json FROM snapshots WHERE article_id=? ORDER BY claim_id", (article_id,)
            )
        ]

    # ---------------------------------------------------------- watcher results
    def save_watcher_result(self, result: WatcherResult) -> None:
        self._execute(
            "INSERT INTO watcher_results(watcher_id, article_id, claim_id, status, json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                result.watcher_id,
                result.article_id,
                result.claim_id,
                result.status.value,
                result.model_dump_json(),
            ),
        )

    def get_watcher_results(self, article_id: str) -> list[WatcherResult]:
        return [
            WatcherResult.model_validate_json(r["json"])
            for r in self._query(
                "SELECT json FROM watcher_results WHERE article_id=? ORDER BY rowid", (article_id,)
            )
        ]

    def dispose_watcher_result(self, watcher_id: str) -> None:
        rows = self._query("SELECT json FROM watcher_results WHERE watcher_id=?", (watcher_id,))
        if not rows:
            return
        result = WatcherResult.model_validate_json(rows[0]["json"])
        disposed = result.model_copy(update={"status": WatcherStatus.DISPOSED})
        self._execute(
            "UPDATE watcher_results SET status=?, json=? WHERE watcher_id=?",
            (disposed.status.value, disposed.model_dump_json(), watcher_id),
        )

    # ----------------------------------------------------------------- events
    def append_event(self, event: AuditEvent) -> None:
        self._execute(
            "INSERT INTO events(event_id, article_id, claim_id, ts, json) VALUES (?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.article_id,
                event.claim_id,
                event.ts.isoformat(),
                json.dumps(event.to_dict()),
            ),
        )

    def get_events(self, article_id: str) -> list[AuditEvent]:
        return [
            AuditEvent.from_dict(json.loads(r["json"]))
            for r in self._query(
                "SELECT json FROM events WHERE article_id=? ORDER BY ts, rowid", (article_id,)
            )
        ]

    # ------------------------------------------------------------------- demo
    def reset(self) -> None:
        with self._lock, self._conn:
            for table in (
                "articles",
                "claims",
                "verdicts",
                "security_results",
                "decisions",
                "snapshots",
                "watcher_results",
                "events",
            ):
                self._conn.execute(f"DELETE FROM {table}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
