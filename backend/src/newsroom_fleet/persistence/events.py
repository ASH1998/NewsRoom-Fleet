"""Append-only audit events — the Article Audit Trail.

Every intake, screening, routing, verdict, policy decision, and lifecycle
transition is recorded with provenance and latency. Events are inserted, never
updated: telemetry loss alerts, but it cannot grant approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from newsroom_fleet.observability.tracing import current_trace_id


@dataclass(frozen=True)
class AuditEvent:
    event_type: str  # e.g. intake_received, source_screened, verdict_recorded, publish_denied
    article_id: str
    actor: str  # desk name, role, or "system"
    claim_id: str | None = None
    latency_ms: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Joins this editorial record to its Cloud Trace waterfall. None when
    # tracing is off — the audit trail never depends on telemetry being up.
    trace_id: str | None = field(default_factory=current_trace_id)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ts"] = self.ts.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        data = dict(data)
        data["ts"] = datetime.fromisoformat(data["ts"]).astimezone(UTC)
        return cls(**data)
