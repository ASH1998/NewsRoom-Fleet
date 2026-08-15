"""Long-horizon behavior: scheduled recheck, materiality, safe abstention."""

from newsroom_fleet.adapters.authoritative import UnavailableAdapter, load_fixture_adapter
from newsroom_fleet.config import FIXTURES_DIR
from newsroom_fleet.desks.base import WatcherEvidenceView
from newsroom_fleet.desks.watcher import FixtureCorrectionsWatcher
from newsroom_fleet.domain.contracts import (
    EditorDisposition,
    Materiality,
    Role,
    WatcherStatus,
)
from newsroom_fleet.fixtures.loader import load_golden_article
from newsroom_fleet.memory.store import load_memory


def snapshot_view() -> WatcherEvidenceView:
    return WatcherEvidenceView(
        article_id="art_x",
        claim_id="clm_02",
        claim_text="City unemployment stood at 4.9 percent in March.",
        adapter_key="harborview_unemployment_mar2025",
        published_value="4.9",
        published_locator="state-labor.example.gov/releases/2025-03#unemployment_rate",
    )


def memory():
    return load_memory(FIXTURES_DIR / "house_rules.json")


def test_material_change_drafts_candidate_in_outlet_style():
    adapter = load_fixture_adapter(FIXTURES_DIR / "authoritative_data.json", "v2")
    result = FixtureCorrectionsWatcher().check(
        snapshot_view(), adapter=adapter, precedent=memory().correction_style()
    )
    assert result is not None
    assert result.materiality is Materiality.MATERIAL
    assert result.status is WatcherStatus.PENDING_EDITOR_REVIEW
    # Outlet's stored precedent style, with provenance-tracked template.
    assert result.candidate_language.startswith("Correction:")
    assert "4.9 percent" in result.candidate_language
    assert "5.1" in result.candidate_language
    assert "State Labor Office" in result.candidate_language
    assert result.current_locator != result.prior_locator


def test_no_change_produces_no_candidate():
    adapter = load_fixture_adapter(FIXTURES_DIR / "authoritative_data.json", "v1")
    assert (
        FixtureCorrectionsWatcher().check(
            snapshot_view(), adapter=adapter, precedent=memory().correction_style()
        )
        is None
    )


def test_unavailable_source_abstains_without_false_candidate():
    assert (
        FixtureCorrectionsWatcher().check(
            snapshot_view(), adapter=UnavailableAdapter(), precedent=memory().correction_style()
        )
        is None
    )


async def test_full_recheck_flow_after_publish(service):
    article_id = await service.submit_article(load_golden_article(), actor="r")
    view = service.article_view(article_id)
    blocking = [
        v["verdict_id"]
        for v in view["verdicts"]
        if v["needs_human"] and v["desk"] != "verdict_aggregator"
    ]
    decision = service.record_decision(
        article_id,
        actor="ed",
        role=Role.EDITOR,
        disposition=EditorDisposition.APPROVE,
        rationale="safe version",
        revised_text="Unemployment stood at 4.9 percent in March; the vote was 6-1.",
        resolved_verdict_ids=blocking,
    )
    assert service.publish(
        article_id, actor="ed", role=Role.EDITOR, decision_id=decision.decision_id
    ).allowed

    # Recheck against unchanged data: no candidate, back to published.
    candidates = service.recheck(article_id, actor="svc-watcher")
    assert candidates == []
    assert service.article_view(article_id)["state"] == "published"

    # Upstream data changes; the watcher drafts a candidate, never auto-corrects.
    service.advance_authoritative_data()
    candidates = service.recheck(article_id, actor="svc-watcher")
    assert len(candidates) == 1
    assert candidates[0].current_value == "5.1"
    view = service.article_view(article_id)
    assert view["state"] == "correction_candidate"
    assert view["published_text"].startswith("Unemployment stood at 4.9")  # unchanged

    # Editor disposes the candidate; article returns to published.
    service.dispose_correction(
        article_id,
        candidates[0].watcher_id,
        actor="ed",
        role=Role.EDITOR,
        accept=True,
        rationale="issue correction per State Labor Office revision",
        corrected_text="Unemployment stood at 5.1 percent in March (revised); the vote was 6-1.",
    )
    view = service.article_view(article_id)
    assert view["state"] == "published"
    assert "5.1" in view["published_text"]
    assert view["watcher_results"][0]["status"] == WatcherStatus.DISPOSED.value

    # Trail shows the whole saga in order.
    event_types = [e.event_type for e in service.repo.get_events(article_id)]
    for expected in (
        "publish_approved",
        "snapshot_recorded",
        "recheck_triggered",
        "watcher_no_change",
        "watcher_candidate_created",
        "correction_disposed",
    ):
        assert expected in event_types, expected
    # The dataset swap is a system-scope event.
    system_events = [e.event_type for e in service.repo.get_events("system")]
    assert "authoritative_data_advanced" in system_events
