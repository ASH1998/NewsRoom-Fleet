"""Bounded PII classification at intake (Gemma).

Gemma is used for exactly one narrow, testable job: decide whether an intake
artifact contains personal data from a fixed category list. It does not verify
claims, it does not write verdicts, and it cannot clear anything — its only
possible effect on the pipeline is to *add* a quarantine that the primary
screener missed. That asymmetry is the point: a second model earns its place by
catching more, never by overriding the first.

Scope is deliberately small so it can be scored: five categories, one label set,
a strict JSON response, and abstention when the model output does not parse.
An abstention leaves the primary screener's disposition untouched and is
recorded in the detector detail, so a silent classifier outage cannot read as
"no PII found".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from newsroom_fleet.domain.contracts import SecurityDisposition, SecurityResult
from newsroom_fleet.security.screening import Screener

log = logging.getLogger(__name__)

#: The whole classification surface. Anything outside these is out of scope.
PII_CATEGORIES = (
    "government_id",  # SSN, passport, driver's licence, tax id
    "financial_account",  # card numbers, bank accounts, routing numbers
    "contact_details",  # home address, personal phone, personal email
    "health_information",  # diagnoses, treatment, medical records
    "credentials",  # passwords, API keys, access tokens
)

CLASSIFIER_VERSION = "gemma-pii-1.0.0"

# Bound the request: intake artifacts can be long, and the classifier is a
# screening pass, not a document reader.
MAX_CHARS = 6000

_PROMPT = """You are a privacy screening classifier for a newsroom intake system.
Decide whether the ARTIFACT contains personal data belonging to a private individual.

Allowed categories (use only these):
{categories}

Rules:
- A public official's name, job title, or official statement is NOT personal data.
- A company name, public dataset, or published statistic is NOT personal data.
- Report a category only if concrete personal data is actually present.
- If nothing qualifies, return an empty category list.

Reply with one line of JSON and nothing else:
{{"has_pii": true|false, "categories": ["..."], "evidence": "<=15 words quoted from the artifact"}}

ARTIFACT:
{artifact}
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_JSON_BLOCKS = re.compile(r"\{.*?\}", re.DOTALL)


@dataclass(frozen=True)
class PIIFinding:
    has_pii: bool
    categories: tuple[str, ...] = ()
    evidence: str = ""
    abstained: bool = False
    detail: str = ""


ABSTAIN = PIIFinding(has_pii=False, abstained=True, detail="classifier unavailable")


@dataclass
class GemmaPIIClassifier:
    """Gemma 3 via the Google GenAI SDK.

    Gemma does not support system instructions or response schemas, so the
    contract is enforced on our side: one prompt, one line of JSON, strict
    parsing, and abstention on anything else.
    """

    project: str | None = None
    location: str = "us-central1"
    model: str = "gemma-3-12b-it"
    api_key: str | None = None
    # Mirrors the Gemini desks: requests are not retained by Google unless an
    # operator opts in for debugging.
    store: bool = False
    version: str = CLASSIFIER_VERSION
    _client: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        import os

        from google import genai

        from newsroom_fleet.desks.live._agent import client_kwargs_for

        api_key = self.api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            self._client = genai.Client(api_key=api_key, **client_kwargs_for(self.store))
        elif self.project:
            # Vertex path: `model` must name a deployed Model Garden endpoint.
            self._client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                **client_kwargs_for(self.store),
            )
        else:
            raise ValueError("Gemma needs GOOGLE_API_KEY or a GCP project")

    def classify(self, text: str) -> PIIFinding:
        artifact = text[:MAX_CHARS]
        try:
            response = self._client.models.generate_content(  # type: ignore[union-attr]
                model=self.model,
                contents=_PROMPT.format(
                    categories="\n".join(f"- {c}" for c in PII_CATEGORIES),
                    artifact=artifact,
                ),
                # Gemma 4 (a4b) is a thinking model: it spends tokens reasoning
                # before the answer, so a tight cap yields thought parts only
                # and response.text comes back empty. A PII hit reasons harder
                # than a clean pass — 1024 tokens still truncated mid-thought.
                config={"temperature": 0.0, "max_output_tokens": 4096},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Gemma PII classification failed (%s)", exc)
            return PIIFinding(
                has_pii=False, abstained=True, detail=f"classifier error: {type(exc).__name__}"
            )
        return self._parse(getattr(response, "text", "") or "")

    def _parse(self, raw: str) -> PIIFinding:
        # Greedy span first (the prompt asks for one object); fall back to each
        # brace block so reasoning preamble around the JSON cannot break parsing.
        data: dict | None = None
        candidates = [*_JSON_RE.findall(raw), *_JSON_BLOCKS.findall(raw)]
        for candidate in candidates:
            try:
                data = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if data is None:
            return PIIFinding(
                has_pii=False, abstained=True, detail="classifier returned unparseable output"
            )

        # Out-of-vocabulary labels are dropped rather than trusted; a finding
        # with no in-scope category is not a finding.
        categories = tuple(
            c for c in data.get("categories", []) if isinstance(c, str) and c in PII_CATEGORIES
        )
        has_pii = bool(data.get("has_pii")) and bool(categories)
        return PIIFinding(
            has_pii=has_pii,
            categories=categories,
            evidence=str(data.get("evidence", ""))[:200],
            detail="classified" if has_pii else "no in-scope personal data detected",
        )


class PIIAwareScreener:
    """Primary screener, then a bounded Gemma pass over anything it called clean."""

    def __init__(self, *, inner: Screener, classifier: GemmaPIIClassifier) -> None:
        self._inner = inner
        self._classifier = classifier
        self.policy_version = f"{inner.policy_version}+{classifier.version}"

    def screen_text(
        self, *, article_id: str, source_id: str | None, content: str
    ) -> SecurityResult:
        result = self._inner.screen_text(
            article_id=article_id, source_id=source_id, content=content
        )
        # The classifier only ever escalates. A already-quarantined or blocked
        # artifact is left exactly as the primary screener judged it.
        if result.disposition is not SecurityDisposition.CLEAN:
            return result

        finding = self._classifier.classify(content)
        if not finding.has_pii:
            note = "abstained" if finding.abstained else "clean"
            return result.model_copy(
                update={
                    "policy_version": self.policy_version,
                    "detector_detail": (
                        f"{result.detector_detail}; PII pass ({self._classifier.version}): "
                        f"{note} — {finding.detail}"
                    ),
                }
            )
        return result.model_copy(
            update={
                "disposition": SecurityDisposition.QUARANTINED,
                "detector": "sensitive_data",
                "policy_version": self.policy_version,
                "detector_detail": (
                    f"{self._classifier.version} flagged {', '.join(finding.categories)}"
                    + (f" — evidence: {finding.evidence}" if finding.evidence else "")
                ),
            }
        )
