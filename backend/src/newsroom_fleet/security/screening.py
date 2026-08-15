"""Intake screening (Model Armor-shaped interface, local heuristic implementation).

Screens the draft body and every attached source *before* any desk receives
privileged context. A quarantined source's content never reaches a reviewer —
only its screening metadata does. The Screener protocol is the seam where real
Model Armor slots in during the Google Cloud phase.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from newsroom_fleet.domain.contracts import (
    SecurityDisposition,
    SecurityResult,
    Source,
)

SCREENING_POLICY_VERSION = "heuristic-screening-1.0"

# Indirect prompt-injection markers. Ordered, case-insensitive.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore (all|any|previous|prior|your) (previous |prior )?instructions",
        r"disregard (all|any|previous|prior|your)",
        r"forget (all|any|previous|your) (previous |prior )?instructions",
        r"system prompt",
        r"you are now\b",
        r"new instructions?:",
        r"override (your |all )?(instructions|rules|policy|guidelines)",
        r"to any ai (assistant|reviewer|model|system)",
        r"mark (all|every|each|these) .{0,40} as (verified|approved|true|confirmed)",
        r"do not (mention|reveal|disclose) this",
        r"\bact as\b.{0,40}(editor|admin|system)",
    )
)

# Minimal sensitive-data markers. (Bounded local PII classification is the
# designated Gemma bonus task in the live phase.)
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b\d{3}-\d{2}-\d{4}\b",  # US SSN
        r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",  # payment card
    )
)


class Screener(Protocol):
    policy_version: str

    def screen_text(
        self, *, article_id: str, source_id: str | None, content: str
    ) -> SecurityResult:
        """Screen one artifact. Returns a signed result; never raises on content."""


class HeuristicScreener:
    """Deterministic fixture-mode screener. Same shape as Model Armor results."""

    policy_version: str = SCREENING_POLICY_VERSION

    def screen_text(
        self, *, article_id: str, source_id: str | None, content: str
    ) -> SecurityResult:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        detector = "none"
        detail = "no detectors matched"
        disposition = SecurityDisposition.CLEAN

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                detector = "prompt_injection"
                detail = f"matched injection marker: /{pattern.pattern}/"
                disposition = SecurityDisposition.QUARANTINED
                break

        if disposition is SecurityDisposition.CLEAN:
            for pattern in _SENSITIVE_PATTERNS:
                if pattern.search(content):
                    detector = "sensitive_data"
                    detail = f"matched sensitive-data marker: /{pattern.pattern}/"
                    disposition = SecurityDisposition.QUARANTINED
                    break

        if not content.strip():
            detector = "policy"
            detail = "empty artifact blocked at intake"
            disposition = SecurityDisposition.BLOCKED

        return SecurityResult(
            security_id=f"sec_{uuid4().hex[:12]}",
            article_id=article_id,
            source_id=source_id,
            disposition=disposition,
            detector=detector,
            detector_detail=detail,
            policy_version=self.policy_version,
            source_hash=digest,
            created_at=datetime.now(UTC),
        )


def screen_submission(
    screener: Screener, article_id: str, body: str, sources: list[Source]
) -> list[SecurityResult]:
    """Screen the body and every source, in order. Nothing is skipped."""
    results = [screener.screen_text(article_id=article_id, source_id=None, content=body)]
    results.extend(
        screener.screen_text(article_id=article_id, source_id=s.source_id, content=s.content)
        for s in sources
    )
    return results
