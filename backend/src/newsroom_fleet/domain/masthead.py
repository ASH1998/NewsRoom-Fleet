"""The Masthead: registry of approved desks, versions, permissions, and schemas.

Permissions encode evidence boundaries in data. The router builds each desk's
evidence view from this registry — a desk physically cannot receive evidence its
registration does not permit. (Design report: "Make independence enforceable".)
"""

from __future__ import annotations

from dataclasses import dataclass

from newsroom_fleet.domain.contracts import SCHEMA_VERSION, Desk


@dataclass(frozen=True)
class DeskRegistration:
    desk: Desk
    agent_version: str
    schema_version: str
    permissions: frozenset[str]  # evidence kinds this desk may receive
    responsibility: str


# Evidence kinds referenced in permissions:
#   draft_text | cited_sources | quarantine_metadata | authoritative_adapter
#   house_rules | precedents | signed_verdicts | published_snapshot | live_adapter
MASTHEAD: tuple[DeskRegistration, ...] = (
    DeskRegistration(
        desk=Desk.CLAIM_EXTRACTOR,
        agent_version="fixture-extractor-1.0.0",
        schema_version=SCHEMA_VERSION,
        permissions=frozenset({"draft_text"}),
        responsibility="Create atomic, checkable claims without deciding truth.",
    ),
    DeskRegistration(
        desk=Desk.SOURCE_VERIFIER,
        agent_version="fixture-source-verifier-1.0.0",
        schema_version=SCHEMA_VERSION,
        permissions=frozenset({"cited_sources", "quarantine_metadata"}),
        responsibility="Determine whether the named source supports the claim.",
    ),
    DeskRegistration(
        desk=Desk.DATA_CHECKER,
        agent_version="fixture-data-checker-1.0.0",
        schema_version=SCHEMA_VERSION,
        permissions=frozenset({"authoritative_adapter"}),
        responsibility="Recompute or retrieve structured numeric evidence.",
    ),
    DeskRegistration(
        desk=Desk.STANDARDS_REVIEWER,
        agent_version="fixture-standards-reviewer-1.0.0",
        schema_version=SCHEMA_VERSION,
        permissions=frozenset({"house_rules", "precedents"}),
        responsibility="Detect legal-status, attribution, and standards risks.",
    ),
    DeskRegistration(
        desk=Desk.VERDICT_AGGREGATOR,
        agent_version="fixture-verdict-aggregator-1.0.0",
        schema_version=SCHEMA_VERSION,
        permissions=frozenset({"signed_verdicts"}),
        responsibility="Resolve state without rewriting reviewer evidence.",
    ),
    DeskRegistration(
        desk=Desk.CORRECTIONS_WATCHER,
        agent_version="fixture-corrections-watcher-1.0.0",
        schema_version=SCHEMA_VERSION,
        permissions=frozenset({"published_snapshot", "live_adapter", "precedents"}),
        responsibility="Draft a correction or update candidate.",
    ),
)


def registration_for(desk: Desk) -> DeskRegistration:
    for reg in MASTHEAD:
        if reg.desk is desk:
            return reg
    raise KeyError(f"desk not registered on the masthead: {desk}")


def masthead_view(running: dict[Desk, str] | None = None) -> list[dict[str, object]]:
    """Registry screen payload (proof artifact: signed version in every verdict).

    `running` maps each desk to the agent version actually constructed for this
    process, so the registry screen shows what is really reviewing — the
    fixture desk or its ADK counterpart — rather than a static claim.
    """
    running = running or {}
    return [
        {
            "desk": reg.desk.value,
            "agent_version": running.get(reg.desk, reg.agent_version),
            "registered_version": reg.agent_version,
            "schema_version": reg.schema_version,
            "permissions": sorted(reg.permissions),
            "responsibility": reg.responsibility,
        }
        for reg in MASTHEAD
    ]
