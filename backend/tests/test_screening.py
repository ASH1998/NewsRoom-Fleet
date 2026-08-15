from newsroom_fleet.domain.contracts import SecurityDisposition
from newsroom_fleet.fixtures.loader import load_golden_article
from newsroom_fleet.security.screening import HeuristicScreener, screen_submission


def test_injected_memo_is_quarantined_before_any_desk():
    article = load_golden_article()
    screener = HeuristicScreener()
    results = screen_submission(screener, article.article_id, article.body, article.sources)
    by_source = {r.source_id: r for r in results if r.source_id}
    memo = by_source["leaked_memo"]
    assert memo.disposition is SecurityDisposition.QUARANTINED
    assert memo.detector == "prompt_injection"
    assert memo.policy_version
    assert len(memo.source_hash) == 64  # sha256 hex, provenance preserved


def test_clean_sources_and_body_pass():
    article = load_golden_article()
    screener = HeuristicScreener()
    results = screen_submission(screener, article.article_id, article.body, article.sources)
    assert results[0].disposition is SecurityDisposition.CLEAN  # body
    by_source = {r.source_id: r for r in results if r.source_id}
    assert by_source["council_minutes"].disposition is SecurityDisposition.CLEAN
    assert by_source["transcript_delgado"].disposition is SecurityDisposition.CLEAN


def test_sensitive_data_quarantined_and_empty_blocked():
    screener = HeuristicScreener()
    ssn = screener.screen_text(article_id="a", source_id=None, content="call 123-45-6789 now")
    assert ssn.disposition is SecurityDisposition.QUARANTINED
    assert ssn.detector == "sensitive_data"
    empty = screener.screen_text(article_id="a", source_id=None, content="   ")
    assert empty.disposition is SecurityDisposition.BLOCKED
