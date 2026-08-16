"""Live desk assembly (ADK + Gemini).

The Verdict Aggregator stays deterministic in every mode. It is not a reviewer —
it resolves persisted state, and the report's invariant is that the publication
decision is a policy evaluation over that state, never a model recommendation.
Handing aggregation to a model would put a generative step between the verdicts
and the gate, which is precisely the thing this architecture refuses to do.
"""

from __future__ import annotations

import logging

from newsroom_fleet.config import GROUNDING_SEARCH, Settings
from newsroom_fleet.desks.base import DeskSet
from newsroom_fleet.desks.live.extractor import LiveClaimExtractor
from newsroom_fleet.desks.live.reviewers import (
    LiveDataChecker,
    LiveSourceVerifier,
    LiveStandardsReviewer,
)
from newsroom_fleet.desks.live.watcher import LiveCorrectionsWatcher
from newsroom_fleet.domain.contracts import Desk
from newsroom_fleet.security.screening import Screener

log = logging.getLogger(__name__)

__all__ = ["live_desk_set"]


def live_desk_set(
    settings: Settings, *, fallback: DeskSet, screener: Screener | None = None
) -> DeskSet:
    model = settings.gemini_model
    # Opt out of Google's server-side request storage on every call unless the
    # operator explicitly enabled it for debugging (NRF_GEMINI_STORE=true).
    store = settings.gemini_store
    implementation = "live"

    data_checker: object = LiveDataChecker(model, store=store)
    source_verifier: object = LiveSourceVerifier(model, store=store)
    if settings.grounding == GROUNDING_SEARCH:
        from newsroom_fleet.desks.live.grounded_data_checker import GroundedDataChecker
        from newsroom_fleet.desks.live.grounded_source_verifier import GroundedSourceVerifier
        from newsroom_fleet.desks.live.grounding import GroundedResearcher

        # The researcher screens what it finds, so it needs the same screener
        # the intake gateway uses. It is not gaining evidence access — it is
        # gaining the sanitiser that keeps fetched pages out of a desk's
        # reasoning context. One researcher serves both grounded desks.
        researcher = GroundedResearcher(model, screener=screener, store=store)
        data_checker = GroundedDataChecker(
            model,
            researcher=researcher,
            approved_domains=settings.authoritative_domains,
            store=store,
        )
        # A claim that cites no source is still worth checking: the Source
        # Verifier researches it under the same approved-authority rule.
        source_verifier = GroundedSourceVerifier(
            model,
            researcher=researcher,
            approved_domains=settings.authoritative_domains,
            store=store,
        )
        implementation = "live+search"

    return DeskSet(
        extractor=LiveClaimExtractor(model, store=store),
        aggregator=fallback.aggregator,  # deterministic by design, see module docstring
        watcher=LiveCorrectionsWatcher(model, store=store),
        workers={
            Desk.SOURCE_VERIFIER: source_verifier,  # type: ignore[dict-item]
            Desk.DATA_CHECKER: data_checker,  # type: ignore[dict-item]
            Desk.STANDARDS_REVIEWER: LiveStandardsReviewer(model, store=store),
        },
        implementation=implementation,
    )
