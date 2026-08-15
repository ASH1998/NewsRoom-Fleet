"""The golden demo fixture, end to end through the real pipeline.

Every expected behavior from the design report appendix is asserted here.
"""

from newsroom_fleet.domain.contracts import (
    Desk,
    EditorDisposition,
    Role,
    SecurityDisposition,
    VerdictResult,
)
from newsroom_fleet.fixtures.loader import load_golden_article


def worker_verdicts(view: dict, claim_id: str) -> dict[str, dict]:
    return {
        v["desk"]: v
        for v in view["verdicts"]
        if v["claim_id"] == claim_id and v["desk"] != "verdict_aggregator"
    }


async def test_golden_article_fans_out_and_blocks(service):
    article = load_golden_article()
    article_id = await service.submit_article(article, actor="reporter:j.reyes")
    view = service.article_view(article_id)

    # Extraction: five atomic claims with stable IDs and routing hints.
    assert [c["claim_id"] for c in view["claims"]] == [
        "clm_01",
        "clm_02",
        "clm_03",
        "clm_04",
        "clm_05",
    ]
    types = {c["claim_id"]: c["type"] for c in view["claims"]}
    assert types == {
        "clm_01": "attribution",
        "clm_02": "numeric",
        "clm_03": "quotation",
        "clm_04": "legal_status",
        "clm_05": "attribution",
    }

    # Screening quarantined the injected memo before orchestration.
    memo = next(s for s in view["security_results"] if s["source_id"] == "leaked_memo")
    assert memo["disposition"] == SecurityDisposition.QUARANTINED.value
    assert memo["detector"] == "prompt_injection"

    # Each desk returns its contract with evidence locators and agent versions.
    assert (
        worker_verdicts(view, "clm_01")["source_verifier"]["result"] == VerdictResult.VERIFIED.value
    )

    clm02 = worker_verdicts(view, "clm_02")["data_checker"]
    assert clm02["result"] == VerdictResult.CONTRADICTED.value
    assert "4.9" in clm02["reason"] and clm02["evidence"][0]["locator"]

    clm03 = worker_verdicts(view, "clm_03")
    assert clm03["source_verifier"]["result"] == VerdictResult.UNSUPPORTED.value
    assert clm03["standards_reviewer"]["result"] == VerdictResult.VERIFIED.value

    clm04 = worker_verdicts(view, "clm_04")["standards_reviewer"]
    assert clm04["result"] == VerdictResult.UNSUPPORTED.value
    assert "legal_status_wording" in clm04["flags"]

    clm05 = worker_verdicts(view, "clm_05")["source_verifier"]
    assert clm05["result"] == VerdictResult.UNSUPPORTED.value
    assert "quarantined_source" in clm05["flags"]
    # The memo's content never entered reviewer context:
    assert "leaked_memo" not in (clm05["evidence"][0]["excerpt"] or "")

    # The fleet found problems, so the gate is closed.
    assert view["state"] == "human_review"
    assert set(view["gate"]["blocked_claim_ids"]) == {"clm_02", "clm_03", "clm_04", "clm_05"}


async def test_reporter_cannot_publish_even_when_gate_is_closed(service):
    article_id = await service.submit_article(load_golden_article(), actor="r")
    outcome = service.publish(article_id, actor="j.reyes", role=Role.REPORTER, decision_id=None)
    assert not outcome.allowed
    assert any("no publish authority" in d for d in outcome.denials)
    events = [e.event_type for e in service.repo.get_events(article_id)]
    assert "publish_denied" in events


async def test_editor_resolves_then_publishes_safe_version(service):
    article_id = await service.submit_article(load_golden_article(), actor="r")
    view = service.article_view(article_id)
    blocking = [
        v["verdict_id"]
        for v in view["verdicts"]
        if v["needs_human"] and v["desk"] != "verdict_aggregator"
    ]
    assert len(blocking) == 4

    safe_text = (
        "The Harborview city council voted 6-1 on Tuesday to approve the Riverbend "
        "development deal. City unemployment stood at 4.9 percent in March, according "
        "to the state labor office. Delgado said she is still studying the job "
        "projections. Developer Samuel Ortiz was charged with tax fraud in 2022; "
        "the case is unresolved. A purported internal memo could not be verified."
    )
    decision = service.record_decision(
        article_id,
        actor="m.okafor",
        role=Role.EDITOR,
        disposition=EditorDisposition.APPROVE,
        rationale="Wording fixed or cut per desk findings; memo never considered.",
        revised_text=safe_text,
        resolved_verdict_ids=blocking,
    )
    outcome = service.publish(
        article_id, actor="m.okafor", role=Role.EDITOR, decision_id=decision.decision_id
    )
    assert outcome.allowed, outcome.denials
    view = service.article_view(article_id)
    assert view["state"] == "published"
    assert view["published_text"] == safe_text
    # Published claim snapshot recorded for the watcher.
    assert (
        view["snapshots"]
        and view["snapshots"][0]["adapter_key"] == "harborview_unemployment_mar2025"
    )
    assert view["snapshots"][0]["published_value"] == "4.9"


async def test_worker_failure_becomes_needs_human_while_fleet_completes(settings, repo):
    from newsroom_fleet.orchestration.pipeline import FleetService
    from newsroom_fleet.security.screening import HeuristicScreener

    settings.fail_desk = Desk.STANDARDS_REVIEWER.value
    service = FleetService(settings, repo, HeuristicScreener())
    article_id = await service.submit_article(load_golden_article(), actor="r")
    view = service.article_view(article_id)

    clm04 = worker_verdicts(view, "clm_04")["standards_reviewer"]
    assert clm04["result"] == VerdictResult.ERROR.value
    assert clm04["needs_human"] is True
    # Other desks completed normally despite the crash.
    assert (
        worker_verdicts(view, "clm_02")["data_checker"]["result"]
        == VerdictResult.CONTRADICTED.value
    )
    events = [e for e in service.repo.get_events(article_id)]
    assert any(
        e.event_type == "worker_failed_needs_human" and e.claim_id == "clm_04" for e in events
    )

    # Recovery: clear the hook, re-review; only the failed verdict is recomputed.
    service.set_fail_desk(None)
    await service.re_review(article_id)
    view = service.article_view(article_id)
    clm04 = worker_verdicts(view, "clm_04")["standards_reviewer"]
    assert clm04["result"] == VerdictResult.UNSUPPORTED.value
    assert "legal_status_wording" in clm04["flags"]


async def test_reporter_cannot_record_editorial_decision(service):
    article_id = await service.submit_article(load_golden_article(), actor="r")
    import pytest

    from newsroom_fleet.orchestration.pipeline import IdentityDeniedError

    with pytest.raises(IdentityDeniedError):
        service.record_decision(
            article_id,
            actor="j.reyes",
            role=Role.REPORTER,
            disposition=EditorDisposition.APPROVE,
            rationale="let me through",
            revised_text=None,
            resolved_verdict_ids=[],
        )
