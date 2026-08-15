"""Model Armor screener — the real detector behind the Screener protocol.

Every artifact (the draft body and each attached source) is sanitized *before*
any desk receives privileged context. A quarantined source's content never
enters a reviewer's evidence view; only its screening metadata does.

**Degradation fails safe, not open.** If the Model Armor API is unreachable, the
local heuristic screener runs instead and the result is stamped
`degraded=true` in the detector detail. Unscreened content is never treated as
clean — an outage in the security plane must not become an implicit "safe".
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import uuid4

from newsroom_fleet.domain.contracts import (
    SecurityDisposition,
    SecurityResult,
)
from newsroom_fleet.security.screening import HeuristicScreener

log = logging.getLogger(__name__)

# Model Armor filter keys -> (detector name, disposition).
# Injection and sensitive data quarantine the artifact so an editor can still
# see that it existed; abuse categories block it outright.
_FILTER_DISPOSITIONS: dict[str, tuple[str, SecurityDisposition]] = {
    "pi_and_jailbreak": ("prompt_injection", SecurityDisposition.QUARANTINED),
    "sdp": ("sensitive_data", SecurityDisposition.QUARANTINED),
    "malicious_uris": ("malicious_uri", SecurityDisposition.QUARANTINED),
    "rai": ("responsible_ai", SecurityDisposition.BLOCKED),
    "csam": ("csam", SecurityDisposition.BLOCKED),
}

# Checked in this order so the most editorially meaningful detector wins the
# label when an artifact trips several filters at once.
_FILTER_PRIORITY = ("csam", "rai", "pi_and_jailbreak", "sdp", "malicious_uris")


class ModelArmorScreener:
    def __init__(
        self,
        *,
        project: str | None,
        location: str,
        template_id: str | None,
        fallback: HeuristicScreener | None = None,
    ) -> None:
        if not project:
            raise ValueError("Model Armor requires a GCP project (NRF_GCP_PROJECT)")
        if not template_id:
            raise ValueError("Model Armor requires a template (NRF_MODEL_ARMOR_TEMPLATE)")

        from google.api_core.client_options import ClientOptions
        from google.cloud import modelarmor_v1

        self._types = modelarmor_v1
        self._client = modelarmor_v1.ModelArmorClient(
            client_options=ClientOptions(api_endpoint=f"modelarmor.{location}.rep.googleapis.com")
        )
        self._template = f"projects/{project}/locations/{location}/templates/{template_id}"
        self._fallback = fallback or HeuristicScreener()
        self.policy_version = f"model-armor/{template_id}"

    # ------------------------------------------------------------------ screen
    def screen_text(
        self, *, article_id: str, source_id: str | None, content: str
    ) -> SecurityResult:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if not content.strip():
            return self._result(
                article_id,
                source_id,
                SecurityDisposition.BLOCKED,
                "policy",
                "empty artifact blocked at intake",
                digest,
            )

        try:
            response = self._client.sanitize_user_prompt(
                request=self._types.SanitizeUserPromptRequest(
                    name=self._template,
                    user_prompt_data=self._types.DataItem(text=content),
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Model Armor call failed (%s); screening with local heuristic", exc)
            degraded = self._fallback.screen_text(
                article_id=article_id, source_id=source_id, content=content
            )
            return degraded.model_copy(
                update={
                    "policy_version": f"{self.policy_version}+degraded",
                    "detector_detail": (
                        f"Model Armor unreachable ({type(exc).__name__}); "
                        f"local heuristic verdict: {degraded.detector_detail}"
                    ),
                }
            )

        detector, disposition, detail = self._interpret(response)
        return self._result(article_id, source_id, disposition, detector, detail, digest)

    # --------------------------------------------------------------- internals
    def _interpret(self, response: object) -> tuple[str, SecurityDisposition, str]:
        result = getattr(response, "sanitization_result", None)
        filter_results = dict(getattr(result, "filter_results", {}) or {})

        for key in _FILTER_PRIORITY:
            entry = filter_results.get(key)
            if entry is None or not self._matched(entry):
                continue
            detector, disposition = _FILTER_DISPOSITIONS[key]
            return detector, disposition, f"Model Armor filter '{key}' reported a match"

        # An unknown-but-matching filter must not be read as clean.
        if self._state_name(getattr(result, "filter_match_state", None)) == "MATCH_FOUND":
            return (
                "unclassified_match",
                SecurityDisposition.QUARANTINED,
                "Model Armor reported a match under a filter this build does not map",
            )
        return "none", SecurityDisposition.CLEAN, "Model Armor: no filter matched"

    def _matched(self, entry: object) -> bool:
        """True when any nested filter result reports MATCH_FOUND.

        The response wraps each filter in a per-type result object whose field
        name varies by filter, so the check walks whatever is present rather
        than assuming one shape.
        """
        if self._state_name(getattr(entry, "match_state", None)) == "MATCH_FOUND":
            return True
        for name in (
            "pi_and_jailbreak_filter_result",
            "sdp_filter_result",
            "rai_filter_result",
            "malicious_uri_filter_result",
            "csam_filter_result",
        ):
            nested = getattr(entry, name, None)
            if nested is None:
                continue
            if self._state_name(getattr(nested, "match_state", None)) == "MATCH_FOUND":
                return True
            for sub in ("inspect_result", "deidentify_result"):
                deeper = getattr(nested, sub, None)
                if deeper is not None and (
                    self._state_name(getattr(deeper, "match_state", None)) == "MATCH_FOUND"
                ):
                    return True
        return False

    @staticmethod
    def _state_name(state: object) -> str:
        if state is None:
            return ""
        return getattr(state, "name", None) or str(state)

    def _result(
        self,
        article_id: str,
        source_id: str | None,
        disposition: SecurityDisposition,
        detector: str,
        detail: str,
        digest: str,
    ) -> SecurityResult:
        return SecurityResult(
            security_id=f"sec_{uuid4().hex[:12]}",
            article_id=article_id,
            source_id=source_id,
            disposition=disposition,
            detector=detector,
            detector_detail=detail,
            policy_version=self.policy_version,
            source_hash=digest,
            created_at=datetime.now(UTC),
        )
