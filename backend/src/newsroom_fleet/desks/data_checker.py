"""Data Checker desk (fixture implementation).

Permitted evidence: the claim plus the approved authoritative adapter. It
recomputes or retrieves structured numeric evidence — it never sees sources,
other verdicts, or the rest of the article.
"""

from __future__ import annotations

import re

from newsroom_fleet.desks._common import new_verdict
from newsroom_fleet.desks.base import DataEvidenceView
from newsroom_fleet.domain.contracts import Desk, EvidenceRef, Verdict, VerdictResult

_VALUE_RE = re.compile(r"\$?(\d+(?:\.\d+)?)\s*(percent|million|billion|%)?", re.IGNORECASE)

_UNIT_ALIASES = {
    "percent": "percent",
    "%": "percent",
    "million": "million_usd",
    "billion": "billion_usd",
}


class FixtureDataChecker:
    agent_version = "fixture-data-checker-1.0.0"

    async def review(self, view: DataEvidenceView) -> Verdict:  # type: ignore[override]
        claim = view.claim
        record = view.adapter.lookup(claim.text)
        if record is None:
            # Outside supported scope: abstain, never guess.
            return new_verdict(
                claim=claim,
                desk=Desk.DATA_CHECKER,
                agent_version=self.agent_version,
                result=VerdictResult.ABSTAIN,
                confidence=1.0,
                needs_human=True,
                reason="no authoritative adapter coverage for this claim's topic",
            )

        match = _VALUE_RE.search(claim.text)
        if not match:
            return new_verdict(
                claim=claim,
                desk=Desk.DATA_CHECKER,
                agent_version=self.agent_version,
                result=VerdictResult.ABSTAIN,
                confidence=0.9,
                needs_human=True,
                reason="numeric claim has no extractable value",
            )

        article_value = match.group(1)
        evidence = [
            EvidenceRef(
                source_identity=record.key,
                locator=record.locator,
                excerpt=f"{record.authority}: {record.value} {record.unit}",
                retrieved_at=record.retrieved_at,
            )
        ]
        if article_value == record.value:
            return new_verdict(
                claim=claim,
                desk=Desk.DATA_CHECKER,
                agent_version=self.agent_version,
                result=VerdictResult.VERIFIED,
                confidence=0.95,
                reason=f"matches {record.authority} figure ({record.value} {record.unit})",
                evidence=evidence,
            )
        return new_verdict(
            claim=claim,
            desk=Desk.DATA_CHECKER,
            agent_version=self.agent_version,
            result=VerdictResult.CONTRADICTED,
            confidence=0.95,
            needs_human=True,
            reason=(
                f"article asserts {article_value}, but {record.authority} reports "
                f"{record.value} {record.unit} (locator: {record.locator})"
            ),
            evidence=evidence,
        )
