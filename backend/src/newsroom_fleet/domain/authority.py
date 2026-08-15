"""Which sources a newsroom will let clear a claim.

Once desks can search the open web, "verified" needs a boundary or it means
nothing. A blog that agrees with the reporter is not corroboration.

The rule is asymmetric, in the same way the Gemma PII pass and the quarantine
rule are asymmetric:

* **Any** source may raise a problem. A random page that contradicts the article
  is grounds to escalate to an editor — it costs nothing to check and the
  downside of ignoring it is publishing something wrong.
* **Only an approved authority** may clear one. A `VERIFIED` verdict has to rest
  on a source the newsroom would defend in print.

This list is the web-scale version of the approved authoritative adapter. It is
editorial policy, so it lives in `domain/` next to the gate rather than in
runtime config — though a deployment can extend it via
`NRF_AUTHORITATIVE_DOMAINS` for outlets with their own approved sources.
"""

from __future__ import annotations

#: Suffix-matched. A domain qualifies if it equals one of these or ends with it
#: preceded by a dot, so `pib.gov.in` matches `.gov.in` and `mospi.gov.in` does
#: too, while `notgov.in` matches neither.
DEFAULT_AUTHORITATIVE_SUFFIXES: tuple[str, ...] = (
    # Government and official statistics
    ".gov",
    ".gov.in",
    ".nic.in",
    ".gov.uk",
    ".gov.au",
    ".govt.nz",
    ".gc.ca",
    ".go.jp",
    ".gouv.fr",
    ".europa.eu",
    ".int",
    # Intergovernmental bodies
    "who.int",
    "un.org",
    "imf.org",
    "worldbank.org",
    "oecd.org",
    # Central banks and regulators commonly cited by local newsrooms
    "rbi.org.in",
    "sebi.gov.in",
    "federalreserve.gov",
    "ecb.europa.eu",
)


def normalise(domain: str) -> str:
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.rstrip(".")


def is_approved(domain: str, extra: tuple[str, ...] = ()) -> bool:
    """True when a domain is one the newsroom will let clear a claim."""
    candidate = normalise(domain)
    if not candidate:
        return False
    for suffix in (*DEFAULT_AUTHORITATIVE_SUFFIXES, *(normalise(e) for e in extra)):
        if not suffix:
            continue
        bare = suffix.lstrip(".")
        if candidate == bare or candidate.endswith("." + bare):
            return True
    return False


def approved_among(domains: tuple[str, ...], extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return tuple(d for d in domains if is_approved(d, extra))
