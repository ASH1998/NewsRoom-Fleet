"""Live Corrections Watcher: deterministic decision, model-drafted language.

The split is deliberate. *Whether* a published claim needs a correction is a
comparison between a stored snapshot and an approved adapter — deterministic
code, because a model that could decide materiality could also decide a
correction was unnecessary. *How* the correction reads is a house-style writing
task, and that is what Gemini does here, conditioned on the approved precedent
retrieved from memory.

If the drafting call fails, the deterministic template language stands. A
model outage delays nothing and suppresses no correction.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from newsroom_fleet.adapters.authoritative import AuthoritativeAdapter
from newsroom_fleet.desks.base import WatcherEvidenceView
from newsroom_fleet.desks.live._agent import DeskAgent
from newsroom_fleet.desks.watcher import FixtureCorrectionsWatcher
from newsroom_fleet.domain.contracts import WatcherResult
from newsroom_fleet.memory.store import CorrectionPrecedent

log = logging.getLogger(__name__)

_INSTRUCTION = """You write correction notices for a local newspaper.

You are given a published figure, the authoritative source's current figure, and
one previously approved correction from this newsroom that shows the house style.

Write a single correction sentence in that same style. State what was previously
reported, state the current figure, and name the authority. Do not apologise, do
not editorialise, do not speculate about why the figure changed, and do not
invent any detail that is not in the input.

The correction is a candidate for an editor to approve. It is never published as
written, so never phrase it as though it already has been.
"""


class _CorrectionDraft(BaseModel):
    candidate_language: str = Field(description="One sentence in the newsroom's house style.")


class LiveCorrectionsWatcher:
    agent_version = "adk-corrections-watcher-1.0.0"

    def __init__(self, model: str) -> None:
        self._deterministic = FixtureCorrectionsWatcher()
        self._agent = DeskAgent(
            name="corrections_watcher",
            model=model,
            instruction=_INSTRUCTION,
            output_schema=_CorrectionDraft,
            temperature=0.2,
        )

    def check(
        self,
        view: WatcherEvidenceView,
        *,
        adapter: AuthoritativeAdapter,
        precedent: CorrectionPrecedent | None,
    ) -> WatcherResult | None:
        result = self._deterministic.check(view, adapter=adapter, precedent=precedent)
        if result is None:
            return None  # no material change, or source unavailable — nothing to phrase

        record = adapter.lookup_by_key(view.adapter_key)
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # no loop in this thread: safe to drive the agent synchronously
        else:
            # Called from inside an event loop (the watcher contract is sync).
            # Ship the deterministic wording rather than block the loop.
            log.debug("event loop active; skipping model drafting")
            return result

        try:
            draft = asyncio.run(
                self._agent.run(
                    {
                        "claim_text": view.claim_text,
                        "published_value": view.published_value,
                        "current_value": result.current_value,
                        "authority": record.authority if record else "the authoritative source",
                        "unit": record.unit if record else "",
                        "house_style_example": precedent.style_template if precedent else None,
                        "house_style_provenance": precedent.provenance if precedent else None,
                    },
                    _CorrectionDraft,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("correction drafting failed (%s); using house template", exc)
            return result

        language = draft.candidate_language.strip()
        if not language:
            return result
        return result.model_copy(update={"candidate_language": language})
