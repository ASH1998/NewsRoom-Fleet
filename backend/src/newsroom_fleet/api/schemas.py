"""API request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from newsroom_fleet.domain.contracts import Desk, EditorDisposition, Role


class SourceIn(BaseModel):
    source_id: str
    kind: str
    name: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubmitArticleIn(BaseModel):
    title: str
    body: str
    author: str
    sources: list[SourceIn] = Field(default_factory=list)
    role: Role = Role.REPORTER


class DecisionIn(BaseModel):
    actor: str
    role: Role
    disposition: EditorDisposition
    rationale: str
    revised_text: str | None = None
    resolved_verdict_ids: list[str] = Field(default_factory=list)


class PublishIn(BaseModel):
    actor: str
    role: Role
    decision_id: str | None = None


class ActorIn(BaseModel):
    actor: str
    role: Role


class DisposeIn(BaseModel):
    actor: str
    role: Role
    accept: bool
    rationale: str = ""
    corrected_text: str | None = None


class DemoConfigIn(BaseModel):
    fail_desk: Desk | None = None
