"""Editorial memory: approved standards guidance and corrections precedents.

Memory Bank-shaped store with hard provenance. Only *approved* guidance enters
memory — unreviewed model output never silently becomes institutional memory.
File-backed now; Vertex AI Memory Bank slots behind MemoryStore later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class HouseRule:
    rule_id: str
    title: str
    pattern_terms: tuple[str, ...]  # all terms must appear for the rule to fire
    banned_terms: tuple[str, ...] = ()  # at least one banned term must appear
    severity: str = "high"
    guidance: str = ""


@dataclass(frozen=True)
class CorrectionPrecedent:
    precedent_id: str
    style_template: str  # uses {prior}, {current}, {authority}
    approved_by: str
    approved_at: datetime
    provenance: str  # where this precedent came from


@dataclass
class MemoryStore:
    house_rules: list[HouseRule] = field(default_factory=list)
    precedents: list[CorrectionPrecedent] = field(default_factory=list)

    def correction_style(self) -> CorrectionPrecedent | None:
        return self.precedents[0] if self.precedents else None


def load_memory(path: Path) -> MemoryStore:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rules = [
        HouseRule(
            rule_id=r["rule_id"],
            title=r["title"],
            pattern_terms=tuple(r["pattern_terms"]),
            banned_terms=tuple(r.get("banned_terms", ())),
            severity=r.get("severity", "high"),
            guidance=r.get("guidance", ""),
        )
        for r in raw["house_rules"]
    ]
    precedents = [
        CorrectionPrecedent(
            precedent_id=p["precedent_id"],
            style_template=p["style_template"],
            approved_by=p["approved_by"],
            approved_at=datetime.fromisoformat(p["approved_at"]).astimezone(UTC),
            provenance=p["provenance"],
        )
        for p in raw["corrections_precedents"]
    ]
    return MemoryStore(house_rules=rules, precedents=precedents)
