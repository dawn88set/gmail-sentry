"""
Tests for the platform executor path (Tier-2 / architecture realignment):
integration ACTIONS run server-side via execute_tool, and gmail.send delegates to
it in platform mode. Network-free (httpx.post mocked).
"""

import httpx
import pytest

from backend.shared.adapters import (
    execute_tool,
    IntegrationNotConnected,
    IntegrationError,
)
from backend.shared.adapters import gmail, slack


class FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _platform(monkeypatch):
    monkeypatch.setenv("CLARITTY_PLATFORM_URL", "http://platform.local")
    monkeypatch.setenv("CLARITY_INTERNAL_SECRET", "s3cret")


def test_execute_tool_success(monkeypatch):
    _platform(monkeypatch)
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["headers"] = kw.get("headers")
        captured["json"] = kw.get("json")
        return FakeResp(200, {"result": {"message_id": "m1"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = execute_tool("gmail", "send", "u1", {"to": "x@y.com"})
    assert out == {"message_id": "m1"}
    assert captured["url"] == "http://platform.local/internal/integrations/tools/gmail/send/execute"
    assert captured["headers"]["X-Claritty-Internal"] == "s3cret"
    assert captured["json"] == {"userId": "u1", "arguments": {"to": "x@y.com"}}


def test_execute_tool_not_connected_409(monkeypatch):
    _platform(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda url, **k: FakeResp(409, {"reason": "NOT_CONNECTED"}))
    with pytest.raises(IntegrationNotConnected):
        execute_tool("gmail", "send", "u1", {})


def test_execute_tool_failure_5xx(monkeypatch):
    _platform(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda url, **k: FakeResp(500, None, "boom"))
    with pytest.raises(IntegrationError):
        execute_tool("gmail", "send", "u1", {})


def test_execute_tool_no_platform_raises_not_connected(monkeypatch):
    monkeypatch.delenv("CLARITTY_PLATFORM_URL", raising=False)
    with pytest.raises(IntegrationNotConnected):
        execute_tool("gmail", "send", "u1", {})


def test_gmail_send_uses_executor_in_platform_mode(monkeypatch):
    _platform(monkeypatch)
    # If send used the executor, it must NOT touch GmailClient/load_credentials.
    monkeypatch.setattr(
        gmail, "execute_tool",
        lambda service, tool, user_id, args: {"message_id": "gmail_x", "account": "rep@co.com"},
    )
    out = gmail.send(None, "u1", to="buyer@acme.com", subject="Hi", body="...")
    assert out == {"external_id": "gmail_x", "account": "rep@co.com"}


def test_gmail_send_executor_no_id_is_failure(monkeypatch):
    _platform(monkeypatch)
    monkeypatch.setattr(gmail, "execute_tool", lambda *a, **k: {})
    with pytest.raises(IntegrationError):
        gmail.send(None, "u1", to="x@y.com", subject="s", body="b")


def test_slack_uses_executor_in_platform_mode(monkeypatch):
    _platform(monkeypatch)
    monkeypatch.setattr(
        slack, "execute_tool",
        lambda service, tool, user_id, args: {"ts": "1700.1", "channel": "C1"},
    )
    out = slack.post_message(None, "u1", channel="#general", text="hi")
    assert out == {"external_id": "1700.1", "account": "C1"}
