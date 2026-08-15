"""Authoritative data adapters.

The Data Checker and Corrections Watcher only trust these adapters — never the
article's own prose. Fixture mode ships a deterministic adapter backed by
`fixtures/authoritative_data.json`, versioned (`v1` / `v2`) so the demo can
simulate an upstream value changing after publication.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AuthoritativeRecord:
    key: str
    keywords: tuple[str, ...]  # entity/topic words that route a claim to this record
    value: str
    unit: str
    locator: str  # where the value lives at the authority
    authority: str  # e.g. "State Labor Office"
    retrieved_at: datetime

    def matches(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)


class AuthoritativeAdapter(Protocol):
    name: str

    def lookup(self, claim_text: str) -> AuthoritativeRecord | None:
        """Find the record covering a claim, or None when out of scope (abstain)."""

    def lookup_by_key(self, key: str) -> AuthoritativeRecord | None: ...


@dataclass
class FixtureAuthoritativeAdapter:
    """Deterministic adapter over a fixed dataset version. Zero network."""

    name: str
    records: list[AuthoritativeRecord] = field(default_factory=list)

    def lookup(self, claim_text: str) -> AuthoritativeRecord | None:
        for record in self.records:
            if record.matches(claim_text):
                return record
        return None

    def lookup_by_key(self, key: str) -> AuthoritativeRecord | None:
        for record in self.records:
            if record.key == key:
                return record
        return None


def load_fixture_adapter(
    path: Path, dataset: str, *, name: str | None = None
) -> FixtureAuthoritativeAdapter:
    raw = json.loads(path.read_text(encoding="utf-8"))
    version = raw["datasets"][dataset]
    records = [
        AuthoritativeRecord(
            key=r["key"],
            keywords=tuple(r["keywords"]),
            value=r["value"],
            unit=r["unit"],
            locator=r["locator"],
            authority=r["authority"],
            retrieved_at=datetime.fromisoformat(r["retrieved_at"]).astimezone(UTC),
        )
        for r in version["records"]
    ]
    return FixtureAuthoritativeAdapter(name=name or version["name"], records=records)


class UnavailableAdapter:
    """Simulates an unreachable authoritative source: the watcher must abstain
    and retain the prior snapshot rather than raise a false correction."""

    name = "unavailable-fixture"

    def lookup(self, claim_text: str) -> AuthoritativeRecord | None:
        return None

    def lookup_by_key(self, key: str) -> AuthoritativeRecord | None:
        return None
