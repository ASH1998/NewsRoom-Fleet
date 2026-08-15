"""Component assembly: settings in, a wired FleetService out.

Every cloud implementation is constructed here and nowhere else, so GCP SDK
imports stay behind their interfaces (Repository, Screener, MemoryStore,
ReviewQueue, ReviewDesk). Each cloud component degrades to its local
implementation with a logged warning rather than failing startup: a judge
cloning the repo must get a working newsroom with no credentials at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from newsroom_fleet.config import (
    FIXTURES_DIR,
    MEMORY_BANK,
    PII_GEMMA,
    QUEUE_PUBSUB,
    REPO_FIRESTORE,
    SCREENER_MODEL_ARMOR,
    Settings,
)
from newsroom_fleet.desks.factory import build_desk_set
from newsroom_fleet.memory.store import MemoryStore, load_memory
from newsroom_fleet.orchestration.pipeline import FleetService
from newsroom_fleet.persistence.repository import Repository
from newsroom_fleet.persistence.sqlite import SQLiteRepository
from newsroom_fleet.security.screening import HeuristicScreener, Screener

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fleet:
    """Everything the API layer needs, plus what actually got built."""

    settings: Settings
    service: FleetService
    repo: Repository
    resolved: dict[str, str]  # switch -> implementation that was really constructed


def _build_repository(settings: Settings, resolved: dict[str, str]) -> Repository:
    if settings.repository == REPO_FIRESTORE:
        try:
            from newsroom_fleet.persistence.firestore import FirestoreRepository

            repo = FirestoreRepository(
                project=settings.gcp_project,
                database=settings.firestore_database,
                prefix=settings.firestore_prefix,
            )
            resolved["repository"] = REPO_FIRESTORE
            return repo
        except Exception as exc:  # noqa: BLE001
            log.warning("Firestore unavailable (%s); falling back to SQLite", exc)
    resolved["repository"] = "sqlite"
    return SQLiteRepository(settings.db_path)


def _build_screener(settings: Settings, resolved: dict[str, str]) -> Screener:
    base: Screener = HeuristicScreener()
    resolved["screener"] = "heuristic"
    if settings.screener == SCREENER_MODEL_ARMOR:
        try:
            from newsroom_fleet.security.model_armor import ModelArmorScreener

            base = ModelArmorScreener(
                project=settings.gcp_project,
                location=settings.gcp_location,
                template_id=settings.model_armor_template,
                fallback=HeuristicScreener(),
            )
            resolved["screener"] = SCREENER_MODEL_ARMOR
        except Exception as exc:  # noqa: BLE001
            log.warning("Model Armor unavailable (%s); using heuristic screening", exc)

    resolved["pii_classifier"] = "off"
    if settings.pii_classifier == PII_GEMMA:
        try:
            from newsroom_fleet.security.pii import GemmaPIIClassifier, PIIAwareScreener

            base = PIIAwareScreener(
                inner=base,
                classifier=GemmaPIIClassifier(
                    project=settings.gcp_project,
                    location=settings.gcp_location,
                    model=settings.gemma_model,
                ),
            )
            resolved["pii_classifier"] = PII_GEMMA
        except Exception as exc:  # noqa: BLE001
            log.warning("Gemma PII classifier unavailable (%s); intake PII pass disabled", exc)
    return base


def _build_memory(settings: Settings, resolved: dict[str, str]) -> MemoryStore:
    seed = load_memory(FIXTURES_DIR / "house_rules.json")
    if settings.memory_backend == MEMORY_BANK:
        try:
            from newsroom_fleet.memory.memory_bank import load_memory_bank

            store = load_memory_bank(settings, seed=seed)
            resolved["memory"] = MEMORY_BANK
            return store
        except Exception as exc:  # noqa: BLE001
            log.warning("Memory Bank unavailable (%s); using file-backed memory", exc)
    resolved["memory"] = "file"
    return seed


def build_fleet(settings: Settings | None = None) -> Fleet:
    settings = settings or Settings.from_env()
    resolved: dict[str, str] = {}

    from newsroom_fleet.observability.tracing import configure_tracing

    resolved["tracing"] = configure_tracing(settings)

    repo = _build_repository(settings, resolved)
    screener = _build_screener(settings, resolved)
    memory = _build_memory(settings, resolved)
    desks = build_desk_set(settings, screener=screener)
    resolved["mode"] = desks.implementation
    resolved["grounding"] = "search" if desks.implementation.endswith("+search") else "off"

    service = FleetService(settings, repo, screener, memory=memory, desks=desks)

    resolved["queue"] = "inprocess"
    if settings.queue == QUEUE_PUBSUB:
        try:
            from newsroom_fleet.orchestration.pubsub import PubSubReviewQueue

            service.attach_queue(
                PubSubReviewQueue(
                    project=settings.gcp_project,
                    topic=settings.pubsub_topic,
                    dead_letter_topic=settings.pubsub_dead_letter_topic,
                )
            )
            resolved["queue"] = QUEUE_PUBSUB
        except Exception as exc:  # noqa: BLE001
            log.warning("Pub/Sub unavailable (%s); reviews run in-process", exc)

    return Fleet(settings=settings, service=service, repo=repo, resolved=resolved)
