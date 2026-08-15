"""Standards Reviewer desk (fixture implementation).

Permitted evidence: the claim, house rules, and corrections precedents. Detects
legal-status, attribution, and standards risks. Its output is a *standards
risk* routed to an editor — explicitly not legal advice and not a libel verdict.
"""

from __future__ import annotations

from datetime import UTC, datetime

from newsroom_fleet.desks._common import new_verdict
from newsroom_fleet.desks.base import StandardsEvidenceView
from newsroom_fleet.domain.contracts import Desk, EvidenceRef, Verdict, VerdictResult
from newsroom_fleet.memory.store import HouseRule


def _rule_fires(rule: HouseRule, text: str) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in rule.pattern_terms) and (
        not rule.banned_terms or any(term.lower() in lowered for term in rule.banned_terms)
    )


class FixtureStandardsReviewer:
    agent_version = "fixture-standards-reviewer-1.0.0"

    async def review(self, view: StandardsEvidenceView) -> Verdict:  # type: ignore[override]
        claim = view.claim
        fired = [rule for rule in view.house_rules if _rule_fires(rule, claim.text)]

        high = [r for r in fired if r.severity == "high"]
        if high:
            rule = high[0]
            return new_verdict(
                claim=claim,
                desk=Desk.STANDARDS_REVIEWER,
                agent_version=self.agent_version,
                result=VerdictResult.UNSUPPORTED,
                confidence=0.9,
                needs_human=True,
                flags=[rule.rule_id, "legal_status_wording"],
                reason=f"high-risk wording — {rule.title}: {rule.guidance}",
                evidence=[
                    EvidenceRef(
                        source_identity=f"house_rule:{rule.rule_id}",
                        locator="memory/house_rules",
                        excerpt=rule.guidance,
                        retrieved_at=datetime.now(UTC),
                    )
                ],
            )

        scan_ref = EvidenceRef(
            source_identity="memory:house_rules",
            locator="memory/house_rules",
            excerpt=f"scanned {len(view.house_rules)} approved house rule(s)",
            retrieved_at=datetime.now(UTC),
        )
        if fired:  # medium-severity notes: recorded, non-blocking
            rule = fired[0]
            return new_verdict(
                claim=claim,
                desk=Desk.STANDARDS_REVIEWER,
                agent_version=self.agent_version,
                result=VerdictResult.VERIFIED,
                confidence=0.7,
                flags=[rule.rule_id],
                reason=f"no blocking violation; note — {rule.title}: {rule.guidance}",
                evidence=[scan_ref],
            )
        return new_verdict(
            claim=claim,
            desk=Desk.STANDARDS_REVIEWER,
            agent_version=self.agent_version,
            result=VerdictResult.VERIFIED,
            confidence=0.8,
            reason="no standards risks detected under approved house rules",
            evidence=[scan_ref],
        )
