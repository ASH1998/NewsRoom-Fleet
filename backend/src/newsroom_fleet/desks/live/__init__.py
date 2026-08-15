"""Live desk assembly (ADK + Gemini).

The Verdict Aggregator stays deterministic in every mode. It is not a reviewer —
it resolves persisted state, and the report's invariant is that the publication
decision is a policy evaluation over that state, never a model recommendation.
Handing aggregation to a model would put a generative step between the verdicts
and the gate, which is precisely the thing this architecture refuses to do.
"""

from __future__ import annotations

import logging

from newsroom_fleet.config import Settings
from newsroom_fleet.desks.base import DeskSet
from newsroom_fleet.desks.live.extractor import LiveClaimExtractor
from newsroom_fleet.desks.live.reviewers import (
    LiveDataChecker,
    LiveSourceVerifier,
    LiveStandardsReviewer,
)
from newsroom_fleet.desks.live.watcher import LiveCorrectionsWatcher
from newsroom_fleet.domain.contracts import Desk

log = logging.getLogger(__name__)

__all__ = ["live_desk_set"]


def live_desk_set(settings: Settings, *, fallback: DeskSet) -> DeskSet:
    model = settings.gemini_model
    return DeskSet(
        extractor=LiveClaimExtractor(model),
        aggregator=fallback.aggregator,  # deterministic by design, see module docstring
        watcher=LiveCorrectionsWatcher(model),
        workers={
            Desk.SOURCE_VERIFIER: LiveSourceVerifier(model),
            Desk.DATA_CHECKER: LiveDataChecker(model),
            Desk.STANDARDS_REVIEWER: LiveStandardsReviewer(model),
        },
        implementation="live",
    )
