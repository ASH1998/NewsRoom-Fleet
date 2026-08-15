"""Grounded-evidence rules that must hold without any network call."""

from __future__ import annotations

from newsroom_fleet.desks.live.grounding import (
    GroundedEvidence,
    GroundingSource,
    _domain_of,
)
from newsroom_fleet.domain.contracts import SecurityDisposition


class _Web:
    """Stand-in for a grounding chunk's `web` object."""

    def __init__(self, uri: str = "", title: str = "", domain: str = "") -> None:
        self.uri, self.title, self.domain = uri, title, domain


def _source(ref: str = "web_1", domain: str = "pib.gov.in") -> GroundingSource:
    return GroundingSource(ref=ref, uri=f"https://example/{ref}", domain=domain, title="t")


def test_prose_without_grounding_chunks_is_not_research() -> None:
    """The model answering from memory reads like a finding and cites nothing."""
    evidence = GroundedEvidence(text="The rate was 6.4 percent.", sources=())
    assert not evidence.usable


def test_quarantined_research_is_unusable() -> None:
    evidence = GroundedEvidence(
        text="",
        sources=(_source(),),
        disposition=SecurityDisposition.QUARANTINED,
        screening_detail="prompt_injection",
    )
    assert not evidence.usable


def test_screened_and_grounded_research_is_usable() -> None:
    evidence = GroundedEvidence(text="The rate was 6.4 percent.", sources=(_source(),))
    assert evidence.usable


def test_handles_map_to_publishers_and_uris() -> None:
    evidence = GroundedEvidence(
        text="finding",
        sources=(_source("web_1", "pib.gov.in"), _source("web_2", "affairscloud.com")),
    )
    # Short handles are what the model cites; long redirect URIs defeat verbatim copying.
    assert evidence.allowed_locators() == {
        "web_1": "pib.gov.in",
        "web_2": "affairscloud.com",
    }
    assert evidence.uri_for()["web_2"] == "https://example/web_2"
    assert evidence.domains() == ("pib.gov.in", "affairscloud.com")


def test_domain_is_read_from_whichever_field_google_populated() -> None:
    # The Gemini API puts the publishing domain in `title` and leaves `domain` empty.
    assert _domain_of(_Web(uri="https://vertexaisearch/x", title="pib.gov.in")) == "pib.gov.in"
    assert _domain_of(_Web(uri="https://vertexaisearch/x", domain="RBI.org.in")) == "rbi.org.in"
    # A human-readable title is not a domain; fall back to parsing the URI.
    assert _domain_of(_Web(uri="https://data.gov.in/report", title="Annual Report 2024")) == (
        "data.gov.in"
    )
