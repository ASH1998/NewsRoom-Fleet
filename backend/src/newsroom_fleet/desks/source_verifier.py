"""Source Verifier desk (fixture implementation).

Permitted evidence: the claim plus its cited, *clean* sources. Quarantined
sources arrive as metadata-only notices — their content never enters this desk.
Determines whether the named source supports the claim, and nothing more.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from newsroom_fleet.desks._common import extract_quoted_span, new_verdict, normalize
from newsroom_fleet.desks.base import SourceEvidenceView
from newsroom_fleet.domain.contracts import (
    ClaimType,
    Desk,
    EvidenceRef,
    Verdict,
    VerdictResult,
)

_NUMBER_RE = re.compile(r"\d+(?:-\d+)?(?:\.\d+)?")


class FixtureSourceVerifier:
    agent_version = "fixture-source-verifier-1.0.0"

    async def review(self, view: SourceEvidenceView) -> Verdict:  # type: ignore[override]
        claim = view.claim
        if not claim.source_refs:
            return new_verdict(
                claim=claim,
                desk=Desk.SOURCE_VERIFIER,
                agent_version=self.agent_version,
                result=VerdictResult.ABSTAIN,
                confidence=1.0,
                needs_human=True,
                reason="claim cites no source for this desk to verify against",
            )

        if not view.cited_sources:
            # Quarantined evidence is unusable for verification.
            notices = ", ".join(
                f"{n.source_id} ({n.detector}, {n.policy_version})" for n in view.quarantined
            )
            return new_verdict(
                claim=claim,
                desk=Desk.SOURCE_VERIFIER,
                agent_version=self.agent_version,
                result=VerdictResult.UNSUPPORTED,
                confidence=1.0,
                needs_human=True,
                flags=["quarantined_source"],
                reason=f"sole cited source quarantined by intake screening: {notices}",
                evidence=[
                    EvidenceRef(
                        source_identity=f"screening:{n.source_id}",
                        locator=n.policy_version,
                        excerpt=f"detector={n.detector}; content withheld from reviewer context",
                        retrieved_at=datetime.now(UTC),
                    )
                    for n in view.quarantined
                ],
            )

        if claim.type is ClaimType.QUOTATION:
            return self._verify_quotation(view)
        return self._verify_attribution(view)

    def _verify_quotation(self, view: SourceEvidenceView) -> Verdict:
        claim = view.claim
        quote = extract_quoted_span(claim.text)
        if not quote:
            return new_verdict(
                claim=claim,
                desk=Desk.SOURCE_VERIFIER,
                agent_version=self.agent_version,
                result=VerdictResult.ABSTAIN,
                confidence=0.9,
                needs_human=True,
                reason="no quoted span found in a quotation claim",
            )
        needle = normalize(quote)
        for source in view.cited_sources:
            haystack = normalize(source.content)
            if needle in haystack:
                idx = haystack.index(needle)
                excerpt = source.content[max(0, idx - 40) : idx + len(quote) + 40]
                return new_verdict(
                    claim=claim,
                    desk=Desk.SOURCE_VERIFIER,
                    agent_version=self.agent_version,
                    result=VerdictResult.VERIFIED,
                    confidence=0.9,
                    reason=f"cited source '{source.source_id}' contains the quoted language",
                    evidence=[
                        EvidenceRef(
                            source_identity=source.source_id,
                            locator=f"{source.source_id}#quote",
                            excerpt=excerpt.strip(),
                            retrieved_at=datetime.now(UTC),
                        )
                    ],
                )
        first = view.cited_sources[0]
        return new_verdict(
            claim=claim,
            desk=Desk.SOURCE_VERIFIER,
            agent_version=self.agent_version,
            result=VerdictResult.UNSUPPORTED,
            confidence=0.8,
            needs_human=True,
            reason=(
                f"cited source '{first.source_id}' does not contain the quoted language "
                f"(or supports it only partially)"
            ),
            evidence=[
                EvidenceRef(
                    source_identity=first.source_id,
                    locator=f"{first.source_id}#transcript",
                    excerpt=first.content[:160].strip(),
                    retrieved_at=datetime.now(UTC),
                )
            ],
        )

    def _verify_attribution(self, view: SourceEvidenceView) -> Verdict:
        claim = view.claim
        claim_norm = normalize(claim.text)
        numbers = _NUMBER_RE.findall(claim_norm)
        entities = [e for e in claim.entities if e.lower() in claim_norm]
        for source in view.cited_sources:
            haystack = normalize(source.content)
            numbers_ok = all(n in haystack for n in numbers)
            entity_hits = [e for e in entities if normalize(e) in haystack]
            if numbers_ok and (entity_hits or not entities):
                return new_verdict(
                    claim=claim,
                    desk=Desk.SOURCE_VERIFIER,
                    agent_version=self.agent_version,
                    result=VerdictResult.VERIFIED,
                    confidence=0.85,
                    reason=f"cited source '{source.source_id}' corroborates the cited facts",
                    evidence=[
                        EvidenceRef(
                            source_identity=source.source_id,
                            locator=f"{source.source_id}#facts",
                            excerpt=source.content[:160].strip(),
                            retrieved_at=datetime.now(UTC),
                        )
                    ],
                )
        first = view.cited_sources[0]
        return new_verdict(
            claim=claim,
            desk=Desk.SOURCE_VERIFIER,
            agent_version=self.agent_version,
            result=VerdictResult.UNSUPPORTED,
            confidence=0.75,
            needs_human=True,
            reason=f"cited source '{first.source_id}' does not corroborate the claim's facts",
            evidence=[
                EvidenceRef(
                    source_identity=first.source_id,
                    locator=f"{first.source_id}#facts",
                    excerpt=first.content[:160].strip(),
                    retrieved_at=datetime.now(UTC),
                )
            ],
        )
