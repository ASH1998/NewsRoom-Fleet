"""Which desks a claim must clear. Deterministic policy, never a model choice.

Routing is where least privilege is decided, so it stays in the domain layer
alongside the Masthead and the gate.

**Why this is not the model's job.** A live extractor once labelled "the council
voted 6-1" as *numeric* and "unemployment fell to 4.2 percent" as *attribution* —
both defensible readings of the prose, and both wrong for routing. The figure
went to the Source Verifier, which had no source to check, and the vote went to
the Data Checker, which had no adapter coverage. Every claim still blocked, so
nothing unsafe escaped, but the contradiction that makes the whole case — 4.2
against the authority's 4.9 — was never found.

So classification for routing purposes is done here, by signals read out of the
claim text itself: a cited source implicates the Source Verifier, a figure
implicates the Data Checker, legal-status wording implicates Standards. A model
cannot move a claim away from the desk most likely to block it, because it is
not consulted about that. Its type is used only when no signal fires at all.
"""

from __future__ import annotations

import re

from newsroom_fleet.domain.contracts import ClaimType, Desk, RiskTier

DESKS_BY_CLAIM_TYPE: dict[ClaimType, tuple[Desk, ...]] = {
    # A figure is settled against an approved adapter, not against prose.
    ClaimType.NUMERIC: (Desk.DATA_CHECKER,),
    # A quotation needs both "did the source say it" and "is quoting it fair".
    ClaimType.QUOTATION: (Desk.SOURCE_VERIFIER, Desk.STANDARDS_REVIEWER),
    ClaimType.ATTRIBUTION: (Desk.SOURCE_VERIFIER,),
    # Charged-vs-guilty wording is a standards question first.
    ClaimType.LEGAL_STATUS: (Desk.STANDARDS_REVIEWER,),
    ClaimType.GENERAL: (Desk.STANDARDS_REVIEWER,),
}

# Evidence signals. Order matters: the first match wins, most consequential
# first, because a sentence can carry several and the routing must be stable.
QUOTE_RE = re.compile(r"[\"“](.+?)[\"”]")
LEGAL_RE = re.compile(r"\b(charged|arrested|indicted|convicted|guilty|defraud\w*)\b", re.IGNORECASE)
DOC_RE = re.compile(
    r"\b(confirms?|memo|leaked|letter|minutes|voted|approved|report|records?|documents?|filing)\b",
    re.IGNORECASE,
)
NUMERIC_RE = re.compile(
    r"("
    r"\$\s?\d+[\d,]*(?:\.\d+)?"  # $12 million, $212
    r"|\d+(?:\.\d+)?\s*(?:percent|million|billion|%)"  # 4.2 percent
    r"|\d{1,3}(?:,\d{3})+"  # 812,000 — comma grouping marks a statistic, not a year
    r")",
    re.IGNORECASE,
)

#: Words that make an attributed document claim high-risk rather than routine.
DOCUMENT_HIGH_RISK = ("leaked", "memo")


def desks_for(claim_type: ClaimType) -> list[Desk]:
    return list(DESKS_BY_CLAIM_TYPE[claim_type])


def classify(text: str, source_refs: list[str]) -> tuple[ClaimType, list[Desk], RiskTier]:
    """Type, desks, and risk tier from signals in the claim text.

    Returns `GENERAL` when nothing fires, which is the caller's cue that a
    model's own classification may be worth falling back to.
    """
    if QUOTE_RE.search(text):
        return (
            ClaimType.QUOTATION,
            desks_for(ClaimType.QUOTATION),
            RiskTier.MEDIUM,
        )
    if LEGAL_RE.search(text):
        return ClaimType.LEGAL_STATUS, desks_for(ClaimType.LEGAL_STATUS), RiskTier.HIGH
    if source_refs and DOC_RE.search(text):
        tier = (
            RiskTier.HIGH
            if any(word in text.lower() for word in DOCUMENT_HIGH_RISK)
            else RiskTier.LOW
        )
        return ClaimType.ATTRIBUTION, desks_for(ClaimType.ATTRIBUTION), tier
    if NUMERIC_RE.search(text):
        return ClaimType.NUMERIC, desks_for(ClaimType.NUMERIC), RiskTier.MEDIUM
    return ClaimType.GENERAL, desks_for(ClaimType.GENERAL), RiskTier.LOW


def has_signal(text: str, source_refs: list[str]) -> bool:
    """True when the claim text itself determines its routing."""
    return classify(text, source_refs)[0] is not ClaimType.GENERAL
