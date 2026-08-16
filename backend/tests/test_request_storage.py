"""Request-storage opt-out: every live Gemini call carries `store: false`.

The standard Gemini API stores GenerateContent requests by default "to help
with debugging". The field is a top-level body parameter the SDK does not yet
model, so it travels via `HttpOptions.extra_body`, which the client merges
into every request body. These tests need no network and no cloud extra —
`_agent` imports the ADK lazily.
"""

from __future__ import annotations

from newsroom_fleet.desks.live._agent import client_kwargs_for


def test_default_is_opt_out():
    assert client_kwargs_for(False) == {"http_options": {"extra_body": {"store": False}}}


def test_operator_can_opt_in_for_debugging():
    assert client_kwargs_for(True) == {"http_options": {"extra_body": {"store": True}}}


def test_setting_defaults_to_opt_out_and_reads_env(monkeypatch):
    from newsroom_fleet.config import Settings

    monkeypatch.delenv("NRF_GEMINI_STORE", raising=False)
    assert Settings.from_env().gemini_store is False

    monkeypatch.setenv("NRF_GEMINI_STORE", "true")
    assert Settings.from_env().gemini_store is True
