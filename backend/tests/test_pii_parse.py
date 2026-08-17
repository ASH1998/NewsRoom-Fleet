"""Parsing contract for the bounded Gemma PII pass.

Gemma is a thinking model and cannot be given a response schema, so the JSON
contract is enforced on our side. These tests pin the parse behaviour without
any network: the classifier is constructed unsafely on purpose (object.__new__)
so only `_parse` is exercised.
"""

from __future__ import annotations

from newsroom_fleet.security.pii import GemmaPIIClassifier


def _classifier() -> GemmaPIIClassifier:
    return object.__new__(GemmaPIIClassifier)


def test_clean_one_line_json_classifies():
    finding = _classifier()._parse(
        '{"has_pii": true, "categories": ["contact_details"], "evidence": "personal line"}'
    )
    assert finding.has_pii
    assert finding.categories == ("contact_details",)
    assert not finding.abstained


def test_json_wrapped_in_reasoning_preamble_still_parses():
    finding = _classifier()._parse(
        "Let me check the categories. The artifact lists a home phone number.\n"
        'Here is my answer: {"has_pii": true, "categories": ["contact_details"], '
        '"evidence": "her personal line 555-014-8892"} done.'
    )
    assert finding.has_pii
    assert finding.categories == ("contact_details",)


def test_out_of_vocabulary_categories_are_dropped():
    finding = _classifier()._parse(
        '{"has_pii": true, "categories": ["favourite_colour", "credentials"], "evidence": "key"}'
    )
    assert finding.categories == ("credentials",)


def test_has_pii_without_in_scope_category_is_not_a_finding():
    finding = _classifier()._parse(
        '{"has_pii": true, "categories": ["favourite_colour"], "evidence": "blue"}'
    )
    assert not finding.has_pii


def test_garbage_output_abstains():
    finding = _classifier()._parse("I cannot answer that in JSON, sorry.")
    assert finding.abstained
    assert not finding.has_pii


def test_empty_categories_reports_clean():
    finding = _classifier()._parse('{"has_pii": false, "categories": [], "evidence": ""}')
    assert not finding.has_pii
    assert not finding.abstained
