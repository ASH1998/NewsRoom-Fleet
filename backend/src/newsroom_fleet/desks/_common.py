"""Shared verdict construction for fixture desks."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from newsroom_fleet.domain.contracts import Claim, Desk, Verdict, VerdictResult


def new_verdict(
    *,
    claim: Claim,
    desk: Desk,
    agent_version: str,
    result: VerdictResult,
    reason: str,
    confidence: float,
    needs_human: bool = False,
    flags: list[str] | None = None,
    evidence: list | None = None,
    error_detail: str | None = None,
) -> Verdict:
    return Verdict(
        verdict_id=f"vrd_{uuid4().hex[:12]}",
        article_id=claim.article_id,
        claim_id=claim.claim_id,
        desk=desk,
        agent_version=agent_version,
        result=result,
        confidence=confidence,
        needs_human=needs_human,
        reason=reason,
        flags=flags or [],
        evidence=evidence or [],
        error_detail=error_detail,
        created_at=datetime.now(UTC),
    )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_quoted_span(text: str) -> str | None:
    match = re.search(r"[\"“](.+?)[\"”]", text)
    return match.group(1) if match else None
