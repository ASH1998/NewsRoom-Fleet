"""Versioned agent output contracts (design report: "Agent output contracts").

All desks emit these machine-readable schemas. Free-form explanation may accompany
a verdict, but it never replaces the structured fields used by routing and policy.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Role(StrEnum):
    REPORTER = "reporter"
    EDITOR = "editor"
    SERVICE = "service"


class Desk(StrEnum):
    CLAIM_EXTRACTOR = "claim_extractor"
    SOURCE_VERIFIER = "source_verifier"
    DATA_CHECKER = "data_checker"
    STANDARDS_REVIEWER = "standards_reviewer"
    VERDICT_AGGREGATOR = "verdict_aggregator"
    CORRECTIONS_WATCHER = "corrections_watcher"


class ClaimType(StrEnum):
    NUMERIC = "numeric"
    QUOTATION = "quotation"
    ATTRIBUTION = "attribution"
    LEGAL_STATUS = "legal_status"
    GENERAL = "general"


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerdictResult(StrEnum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    ABSTAIN = "abstain"
    ERROR = "error"


class SecurityDisposition(StrEnum):
    CLEAN = "clean"
    QUARANTINED = "quarantined"
    BLOCKED = "blocked"


class EditorDisposition(StrEnum):
    APPROVE = "approve"
    SEND_BACK = "send_back"


class Materiality(StrEnum):
    MATERIAL = "material"
    IMMATERIAL = "immaterial"


class WatcherStatus(StrEnum):
    PENDING_EDITOR_REVIEW = "pending_editor_review"
    DISPOSED = "disposed"


# --------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------


class Source(BaseModel):
    """Raw source material attached to a draft. Screened before any desk sees it."""

    source_id: str
    kind: str  # interview | document | memo | dataset | ...
    name: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Article(BaseModel):
    article_id: str
    title: str
    body: str
    author: str
    submitted_at: datetime
    sources: list[Source] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Claims
# --------------------------------------------------------------------------

# Inline citation token used by the deterministic extractor, e.g. "[source:memo_1]".
SOURCE_TOKEN_PREFIX = "[source:"


class Claim(BaseModel):
    """Atomic checkable claim. The extractor creates claims; it never decides truth."""

    claim_id: str
    article_id: str
    text: str
    span: tuple[int, int]  # character offsets into the article body
    type: ClaimType
    entities: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)  # source_ids cited inline
    risk_tier: RiskTier
    required_desks: list[Desk]
    extractor_version: str


# --------------------------------------------------------------------------
# Evidence & verdicts
# --------------------------------------------------------------------------


class EvidenceRef(BaseModel):
    """First-class evidence: where it lives, who supplied it, when it was retrieved."""

    source_identity: str  # adapter name or source_id
    locator: str  # e.g. "state-labor/mar2025#unemployment_rate"
    excerpt: str = ""
    retrieved_at: datetime


class Verdict(BaseModel):
    """Signed structured verdict. Without evidence, it cannot become VERIFIED."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = SCHEMA_VERSION
    verdict_id: str
    article_id: str
    claim_id: str
    desk: Desk
    agent_version: str
    result: VerdictResult
    confidence: float = Field(ge=0.0, le=1.0)
    needs_human: bool = False
    reason: str
    flags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    error_detail: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------
# Security screening
# --------------------------------------------------------------------------


class SecurityResult(BaseModel):
    """Model Armor-shaped screening verdict for the body or a single source."""

    model_config = ConfigDict(frozen=True)

    security_id: str
    article_id: str
    source_id: str | None  # None → the article body itself
    disposition: SecurityDisposition
    detector: str  # prompt_injection | sensitive_data | policy | none
    detector_detail: str
    policy_version: str
    source_hash: str  # sha256 of the screened content
    sanitized_ref: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------
# Editor decision
# --------------------------------------------------------------------------


class EditorDecision(BaseModel):
    """Human authority, recorded. Timestamp and identity are system-generated."""

    decision_id: str
    article_id: str
    actor: str
    role: Role
    disposition: EditorDisposition
    rationale: str
    revised_text: str | None = None
    resolved_verdict_ids: list[str] = Field(default_factory=list)
    created_at: datetime


# --------------------------------------------------------------------------
# Published snapshot & watcher
# --------------------------------------------------------------------------


class ClaimSnapshot(BaseModel):
    """Immutable snapshot of a published numeric claim, used by the watcher."""

    article_id: str
    claim_id: str
    claim_text: str
    adapter_key: str
    published_value: str
    locator: str
    recorded_at: datetime


class WatcherResult(BaseModel):
    """Correction or update candidate — drafted for an editor, never auto-published."""

    watcher_id: str
    article_id: str
    claim_id: str
    prior_value: str
    prior_locator: str
    current_value: str
    current_locator: str
    materiality: Materiality
    candidate_language: str
    status: WatcherStatus
    created_at: datetime
