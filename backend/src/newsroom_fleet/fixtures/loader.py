"""Fixture loading — the planted golden article and its expected outcomes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from newsroom_fleet.domain.contracts import Article, Source

FIXTURES_DIR = Path(__file__).resolve().parent


def load_golden_article() -> Article:
    raw = json.loads((FIXTURES_DIR / "golden_article.json").read_text(encoding="utf-8"))
    return Article(
        article_id=raw["article_id"],
        title=raw["title"],
        body=raw["body"],
        author=raw["author"],
        submitted_at=datetime.fromisoformat(raw["submitted_at"]).astimezone(UTC),
        sources=[Source(**s) for s in raw["sources"]],
    )


def golden_expectations() -> dict[str, str]:
    raw = json.loads((FIXTURES_DIR / "golden_article.json").read_text(encoding="utf-8"))
    return dict(raw["expected_outcomes"])
