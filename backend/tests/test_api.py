"""API surface: identity-enforced gate, demo endpoints, audit trail."""

import pytest
from fastapi.testclient import TestClient

from newsroom_fleet.api.app import create_app
from newsroom_fleet.config import Settings
from newsroom_fleet.fixtures.loader import load_golden_article


@pytest.fixture
def client(tmp_path):
    settings = Settings(db_path=tmp_path / "api_test.sqlite3")
    with TestClient(create_app(settings)) as c:
        yield c


def test_health_and_masthead(client):
    assert client.get("/api/health").json()["status"] == "ok"
    desks = client.get("/api/masthead").json()["desks"]
    assert len(desks) == 6
    extractor = next(d for d in desks if d["desk"] == "claim_extractor")
    assert extractor["permissions"] == ["draft_text"]  # may see nothing else


def test_golden_demo_full_flow(client):
    # One command reproduces the planted article and expected verdicts.
    view = client.post("/api/demo/golden").json()
    article_id = view["article"]["article_id"]
    assert view["state"] == "human_review"

    # Failed publish attempt: reporter is denied server-side.
    denied = client.post(
        f"/api/articles/{article_id}/publish", json={"actor": "j.reyes", "role": "reporter"}
    )
    assert denied.status_code == 403
    assert any("no publish authority" in d for d in denied.json()["detail"]["denials"])

    # Reporter cannot even record an editorial decision.
    denied_decision = client.post(
        f"/api/articles/{article_id}/decisions",
        json={
            "actor": "j.reyes",
            "role": "reporter",
            "disposition": "approve",
            "rationale": "trust me",
        },
    )
    assert denied_decision.status_code == 403

    # Editor alone cannot publish without resolving blockers.
    denied_editor = client.post(
        f"/api/articles/{article_id}/publish", json={"actor": "m.okafor", "role": "editor"}
    )
    assert denied_editor.status_code == 403

    blocking = [
        v["verdict_id"]
        for v in view["verdicts"]
        if v["needs_human"] and v["desk"] != "verdict_aggregator"
    ]
    safe_text = (
        "The Harborview city council voted 6-1 to approve the Riverbend deal. "
        "City unemployment stood at 4.9 percent in March. Delgado said she is "
        "still studying the job projections. Samuel Ortiz was charged with tax "
        "fraud in 2022; the case is unresolved."
    )
    created = client.post(
        f"/api/articles/{article_id}/decisions",
        json={
            "actor": "m.okafor",
            "role": "editor",
            "disposition": "approve",
            "rationale": "resolved all flags; quarantined memo never used",
            "revised_text": safe_text,
            "resolved_verdict_ids": blocking,
        },
    )
    assert created.status_code == 201
    decision_id = created.json()["decision_id"]

    published = client.post(
        f"/api/articles/{article_id}/publish",
        json={"actor": "m.okafor", "role": "editor", "decision_id": decision_id},
    )
    assert published.status_code == 200
    assert published.json()["state"] == "published"

    # Scheduled recheck: unchanged data first, then the upstream revision.
    assert (
        client.post(
            f"/api/articles/{article_id}/recheck", json={"actor": "svc", "role": "service"}
        ).json()["candidates"]
        == []
    )
    client.post("/api/demo/advance-data")
    recheck = client.post(
        f"/api/articles/{article_id}/recheck", json={"actor": "svc", "role": "service"}
    )
    candidates = recheck.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["current_value"] == "5.1"

    disposed = client.post(
        f"/api/articles/{article_id}/corrections/{candidates[0]['watcher_id']}/dispose",
        json={
            "actor": "m.okafor",
            "role": "editor",
            "accept": True,
            "rationale": "issue correction",
        },
    )
    assert disposed.status_code == 200
    assert disposed.json()["state"] == "published"

    # Audit trail covers the whole arc, in order of occurrence.
    events = client.get(f"/api/articles/{article_id}/audit").json()["events"]
    kinds = [e["event_type"] for e in events]
    assert kinds.index("publish_denied") < kinds.index("publish_approved")
    assert "source_quarantined" in kinds
    assert "watcher_candidate_created" in kinds


def test_submit_fresh_article_and_list(client):
    article = load_golden_article()
    response = client.post(
        "/api/articles",
        json={
            "title": article.title,
            "body": article.body,
            "author": article.author,
            "sources": [s.model_dump(mode="json") for s in article.sources],
        },
    )
    assert response.status_code == 201
    article_id = response.json()["article"]["article_id"]
    assert response.json()["state"] == "human_review"
    listed = client.get("/api/articles").json()["articles"]
    assert any(a["article_id"] == article_id for a in listed)
    assert client.get(f"/api/articles/{article_id}").status_code == 200
    assert client.get("/api/articles/art_missing").status_code == 404


def test_illegal_recheck_is_conflict(client):
    view = client.post("/api/demo/golden").json()
    article_id = view["article"]["article_id"]
    response = client.post(
        f"/api/articles/{article_id}/recheck", json={"actor": "svc", "role": "service"}
    )
    assert response.status_code == 409  # not published yet
    reporter = client.post(
        f"/api/articles/{article_id}/recheck", json={"actor": "r", "role": "reporter"}
    )
    assert reporter.status_code == 403
