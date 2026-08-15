"""Corrections Watcher desk (fixture implementation).

Permitted evidence: the published claim snapshot plus the approved live
adapter. Drafts a correction candidate *in the outlet's stored style* when a
material change appears. Never auto-corrects, never auto-publishes. When the
authoritative source is unavailable, it abstains and retains the prior snapshot
— no false correction candidate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from newsroom_fleet.adapters.authoritative import AuthoritativeAdapter
from newsroom_fleet.desks.base import WatcherEvidenceView
from newsroom_fleet.domain.contracts import (
    Materiality,
    WatcherResult,
    WatcherStatus,
)
from newsroom_fleet.memory.store import CorrectionPrecedent


class FixtureCorrectionsWatcher:
    agent_version = "fixture-corrections-watcher-1.0.0"

    def check(
        self,
        view: WatcherEvidenceView,
        *,
        adapter: AuthoritativeAdapter,
        precedent: CorrectionPrecedent | None,
    ) -> WatcherResult | None:
        """Return a candidate only for a material change; None means 'no action'."""
        record = adapter.lookup_by_key(view.adapter_key)
        if record is None:
            return None  # source unavailable / out of scope -> abstain, retain snapshot
        if record.value == view.published_value:
            return None  # no material change

        template = (
            precedent.style_template
            if precedent
            else "Correction: previously reported {prior}; {authority} now reports {current}."
        )
        candidate = template.format(
            prior=f"{view.published_value} percent",
            current=f"{record.value} {record.unit}",
            authority=record.authority,
        )
        return WatcherResult(
            watcher_id=f"wat_{uuid4().hex[:12]}",
            article_id=view.article_id,
            claim_id=view.claim_id,
            prior_value=view.published_value,
            prior_locator=view.published_locator,
            current_value=record.value,
            current_locator=record.locator,
            materiality=Materiality.MATERIAL,
            candidate_language=candidate,
            status=WatcherStatus.PENDING_EDITOR_REVIEW,
            created_at=datetime.now(UTC),
        )
