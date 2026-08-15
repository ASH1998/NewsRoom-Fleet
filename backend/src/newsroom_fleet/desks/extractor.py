"""Claim Extractor desk (fixture implementation).

Permitted evidence: draft text only. Creates atomic, checkable claims and never
decides truth. Deterministic sentence splitting + claim typing; the live phase
swaps in an ADK/Gemini extractor behind the same contract.

Known fixture-mode limitation: quoted spans containing sentence-final
punctuation (.!?) split early. Fresh demo copy should avoid periods inside quotes.
"""

from __future__ import annotations

import re

from newsroom_fleet.desks.base import ExtractionOutput
from newsroom_fleet.domain.contracts import Claim
from newsroom_fleet.domain.routing import classify as _classify

# A sentence, its closing punctuation, an optional closing quote, and any
# trailing inline citation tokens belong together. Decimal numbers (\d.\d) do
# not terminate a sentence.
_SENTENCE_RE = re.compile(r"(?:\d\.\d|[^.!?])+[.!?]+\s*(?:\[[^\]]*\]\s*)*")
_TOKEN_RE = re.compile(r"\[source:([A-Za-z0-9_-]+)\]")
_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")


def _entities(sentence: str) -> list[str]:
    return sorted(set(_ENTITY_RE.findall(sentence)))


class FixtureClaimExtractor:
    agent_version = "fixture-extractor-1.0.0"

    async def extract(self, article_id: str, body: str) -> ExtractionOutput:
        claims: list[Claim] = []
        for idx, match in enumerate(_SENTENCE_RE.finditer(body), start=1):
            raw_span = match.group(0)
            source_refs = _TOKEN_RE.findall(raw_span)
            text = _TOKEN_RE.sub("", raw_span).strip()
            if not text:
                continue
            start = match.start() + (len(raw_span) - len(raw_span.lstrip()))
            span = (start, start + len(text))
            claim_type, desks, tier = _classify(text, source_refs)
            claims.append(
                Claim(
                    claim_id=f"clm_{idx:02d}",
                    article_id=article_id,
                    text=text,
                    span=span,
                    type=claim_type,
                    entities=_entities(text),
                    source_refs=source_refs,
                    risk_tier=tier,
                    required_desks=desks,
                    extractor_version=self.agent_version,
                )
            )
        return ExtractionOutput(claims=claims)
