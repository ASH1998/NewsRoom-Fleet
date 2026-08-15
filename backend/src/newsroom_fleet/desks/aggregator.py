"""Verdict Aggregator desk (fixture implementation).

Permitted evidence: signed reviewer verdicts only. Resolves a per-claim summary
state for the UI and gate report — without rewriting reviewer evidence and
without erasing disagreement. Blocking worker verdicts stay on the record.
"""

from __future__ import annotations

from newsroom_fleet.desks._common import new_verdict
from newsroom_fleet.desks.base import AggregateEvidenceView
from newsroom_fleet.domain.contracts import Desk, Verdict, VerdictResult
from newsroom_fleet.domain.policy import usable_verified

_WORST_FIRST = (
    VerdictResult.CONTRADICTED,
    VerdictResult.ERROR,
    VerdictResult.UNSUPPORTED,
    VerdictResult.ABSTAIN,
)


class FixtureVerdictAggregator:
    agent_version = "fixture-verdict-aggregator-1.0.0"

    def aggregate(self, view: AggregateEvidenceView) -> Verdict:
        claim = view.claim
        workers = [v for v in view.desk_verdicts if v.desk is not Desk.VERDICT_AGGREGATOR]
        missing = [d.value for d in claim.required_desks if d not in {v.desk for v in workers}]
        flags = sorted({flag for v in workers for flag in v.flags})

        if not missing and workers and all(usable_verified(v) for v in workers):
            return new_verdict(
                claim=claim,
                desk=Desk.VERDICT_AGGREGATOR,
                agent_version=self.agent_version,
                result=VerdictResult.VERIFIED,
                confidence=min(v.confidence for v in workers),
                reason="all required desks concur with evidence",
                flags=flags,
                evidence=[ref for v in workers for ref in v.evidence][:4],
            )

        for result in _WORST_FIRST:
            hit = next((v for v in workers if v.result is result), None)
            if hit is not None:
                break
        else:
            hit = None

        parts = [*(f"{v.desk.value}: {v.result.value}" for v in workers)]
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        return new_verdict(
            claim=claim,
            desk=Desk.VERDICT_AGGREGATOR,
            agent_version=self.agent_version,
            result=hit.result if hit else VerdictResult.ABSTAIN,
            confidence=min((v.confidence for v in workers), default=1.0),
            needs_human=True,
            reason="disagreement/failure preserved for editor — " + "; ".join(parts),
            flags=flags,
            evidence=[ref for v in workers for ref in v.evidence][:4],
        )
