"""
Tests for B3 — the integration adapter layer (backend/shared/adapters/).

Network-free: we monkeypatch the credential store so we exercise the
not-connected / validation signalling and the liveness registry without hitting
Gmail or Slack.
"""

import pytest

from backend.shared import adapters
from backend.shared.adapters import (
    IntegrationNotConnected,
    IntegrationError,
    load_credentials,
    run_liveness,
)
from backend.shared.adapters import gmail, slack


def _patch_creds(monkeypatch, value):
    from backend.integrations import store
    monkeypatch.setattr(store, "get_credentials", lambda db, uid, svc: value)


def test_load_credentials_raises_when_missing(monkeypatch):
    _patch_creds(monkeypatch, None)
    with pytest.raises(IntegrationNotConnected):
        load_credentials(None, "u1", "gmail")


def test_load_credentials_returns_dict(monkeypatch):
    _patch_creds(monkeypatch, {"access_token": "abc"})
    assert load_credentials(None, "u1", "gmail") == {"access_token": "abc"}


def test_slack_not_connected_without_token(monkeypatch):
    _patch_creds(monkeypatch, {})  # connected row but no token
    with pytest.raises(IntegrationNotConnected):
        slack.post_message(None, "u1", channel="#general", text="hi")


def test_slack_requires_channel(monkeypatch):
    _patch_creds(monkeypatch, {"bot_token": "xoxb-x"})
    with pytest.raises(IntegrationError):
        slack.post_message(None, "u1", channel="", text="hi")


def test_gmail_send_requires_recipient(monkeypatch):
    _patch_creds(monkeypatch, {"access_token": "abc"})
    with pytest.raises(IntegrationError):
        gmail.send(None, "u1", to="", subject="s", body="b")


def test_run_liveness_unknown_provider_returns_none():
    assert run_liveness(None, "u1", "definitely-not-a-provider") is None


def test_run_liveness_dispatches_to_adapter(monkeypatch):
    # Not connected -> slack.test_connection returns a friendly not-ok dict
    _patch_creds(monkeypatch, None)
    result = run_liveness(None, "u1", "slack")
    assert result == {"ok": False, "detail": "slack is not connected."}
