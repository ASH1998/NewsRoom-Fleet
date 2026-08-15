"""Desk base types: bounded evidence views and the review protocol.

Each desk declares a distinct input view carrying *only* the evidence its
Masthead registration permits. Desks cannot import the repository, the full
article, or each other's verdicts — independence is structural, not by
convention. (Design report: "Independence must exist in code".)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from newsroom_fleet.adapters.authoritative import AuthoritativeAdapter
from newsroom_fleet.domain.contracts import Claim, Desk, Source, Verdict, WatcherResult
from newsroom_fleet.memory.store import CorrectionPrecedent, HouseRule


@dataclass(frozen=True)
class QuarantineNotice:
    """Metadata about a quarantined source. Content deliberately excluded."""

    source_id: str
    detector: str
    policy_version: str


@dataclass(frozen=True)
class SourceEvidenceView:
    """Source Verifier: the claim plus its cited (clean) sources. Nothing else."""

    claim: Claim
    cited_sources: tuple[Source, ...] = ()
    quarantined: tuple[QuarantineNotice, ...] = ()


@dataclass(frozen=True)
class DataEvidenceView:
    """Data Checker: the claim plus the approved authoritative adapter."""

    claim: Claim
    adapter: AuthoritativeAdapter


@dataclass(frozen=True)
class StandardsEvidenceView:
    """Standards Reviewer: the claim plus house rules and corrections precedents."""

    claim: Claim
    house_rules: tuple[HouseRule, ...] = ()
    precedents: tuple[CorrectionPrecedent, ...] = ()


@dataclass(frozen=True)
class AggregateEvidenceView:
    """Verdict Aggregator: signed reviewer verdicts only."""

    claim: Claim
    desk_verdicts: tuple[Verdict, ...] = ()


@dataclass(frozen=True)
class WatcherEvidenceView:
    """Corrections Watcher: the published snapshot plus the approved live source."""

    article_id: str
    claim_id: str
    claim_text: str
    adapter_key: str
    published_value: str
    published_locator: str


@dataclass(frozen=True)
class ExtractionOutput:
    claims: list[Claim]
    notes: str = ""


class ReviewDesk(Protocol):
    """Worker desk contract: consume a bounded view, emit one signed verdict."""

    agent_version: str

    async def review(self, view: object) -> Verdict: ...


class ClaimExtractor(Protocol):
    """Draft text in, atomic claims out. Never decides truth."""

    agent_version: str

    async def extract(self, article_id: str, body: str) -> ExtractionOutput: ...


class VerdictAggregator(Protocol):
    """Signed reviewer verdicts in, one summary verdict out. Never regenerates."""

    agent_version: str

    def aggregate(self, view: AggregateEvidenceView) -> Verdict: ...


class CorrectionsWatcher(Protocol):
    """Published snapshot + live adapter in, a correction candidate or None out."""

    agent_version: str

    def check(
        self,
        view: WatcherEvidenceView,
        *,
        adapter: AuthoritativeAdapter,
        precedent: CorrectionPrecedent | None,
    ) -> WatcherResult | None: ...


@dataclass(frozen=True)
class DeskSet:
    """The fleet's assembled desks.

    Fixture and live implementations satisfy identical protocols, so the
    orchestration layer is written once. `implementation` is surfaced in the
    Masthead screen so a judge can see which agents actually ran.
    """

    extractor: ClaimExtractor
    aggregator: VerdictAggregator
    watcher: CorrectionsWatcher
    workers: dict[Desk, ReviewDesk] = field(default_factory=dict)
    implementation: str = "fixture"

    def running_versions(self) -> dict[Desk, str]:
        """Agent version actually constructed for each desk in this process."""
        versions = {desk: impl.agent_version for desk, impl in self.workers.items()}
        versions[Desk.CLAIM_EXTRACTOR] = self.extractor.agent_version
        versions[Desk.VERDICT_AGGREGATOR] = self.aggregator.agent_version
        versions[Desk.CORRECTIONS_WATCHER] = self.watcher.agent_version
        return versions
