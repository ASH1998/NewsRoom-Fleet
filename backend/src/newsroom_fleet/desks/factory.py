"""Desk assembly: fixture desks, live (ADK + Gemini) desks, or a mix.

Fixture mode is not a stub — it is the deterministic implementation the
recorded demo runs on. Live mode swaps in ADK agents behind the identical
protocols, so the router, runner, gate, and audit trail are unchanged. If a
live desk cannot be constructed (missing SDK or project), that desk falls back
to its fixture implementation rather than silently disappearing from the fleet.
"""

from __future__ import annotations

import logging

from newsroom_fleet.config import MODE_LIVE, Settings
from newsroom_fleet.desks.aggregator import FixtureVerdictAggregator
from newsroom_fleet.desks.base import DeskSet
from newsroom_fleet.desks.data_checker import FixtureDataChecker
from newsroom_fleet.desks.extractor import FixtureClaimExtractor
from newsroom_fleet.desks.source_verifier import FixtureSourceVerifier
from newsroom_fleet.desks.standards_reviewer import FixtureStandardsReviewer
from newsroom_fleet.desks.watcher import FixtureCorrectionsWatcher
from newsroom_fleet.domain.contracts import Desk

log = logging.getLogger(__name__)


def fixture_desk_set() -> DeskSet:
    return DeskSet(
        extractor=FixtureClaimExtractor(),
        aggregator=FixtureVerdictAggregator(),
        watcher=FixtureCorrectionsWatcher(),
        workers={
            Desk.SOURCE_VERIFIER: FixtureSourceVerifier(),
            Desk.DATA_CHECKER: FixtureDataChecker(),
            Desk.STANDARDS_REVIEWER: FixtureStandardsReviewer(),
        },
        implementation="fixture",
    )


def build_desk_set(settings: Settings) -> DeskSet:
    if settings.mode != MODE_LIVE:
        return fixture_desk_set()

    fallback = fixture_desk_set()
    try:
        from newsroom_fleet.desks.live import live_desk_set
    except ImportError as exc:  # google-adk / google-genai not installed
        log.warning("live mode requested but the ADK stack is missing (%s); using fixtures", exc)
        return fallback
    try:
        return live_desk_set(settings, fallback=fallback)
    except Exception as exc:  # noqa: BLE001 — a bad live config must never break intake
        log.warning("live desk construction failed (%s); using fixtures", exc)
        return fallback
