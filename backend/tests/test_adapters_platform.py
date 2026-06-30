"""
W7 — adapter credential resolution honors the Claritty-managed (platform) model.

load_credentials must resolve creds from the platform when CLARITTY_PLATFORM_URL
(or a CLARITTY_FAKE_CREDS_<SERVICE> override) is set, and fall back to the local
store otherwise. persist_refreshed must be a no-op on platform.
"""

import pytest

from backend.shared import adapters
from backend.shared.adapters import load_credentials, persist_refreshed, IntegrationNotConnected


def test_fake_creds_override_uses_platform_resolver(monkeypatch):
    # The SDK resolver short-circuits on CLARITTY_FAKE_CREDS_<ID> — exercises the
    # real platform path without a live platform.
    monkeypatch.setenv("CLARITTY_FAKE_CREDS_GMAIL", '{"access_token": "fake-token"}')
    monkeypatch.delenv("CLARITTY_PLATFORM_URL", raising=False)
    creds = load_credentials(None, "u1", "gmail")
    assert creds.get("access_token") == "fake-token"


def test_platform_mode_not_connected_raises(monkeypatch):
    # Platform configured but no creds reachable (no internal secret/endpoint) →
    # the resolver raises CredentialsNotAvailable → IntegrationNotConnected.
    monkeypatch.setenv("CLARITTY_PLATFORM_URL", "http://platform.invalid")
    monkeypatch.delenv("CLARITTY_FAKE_CREDS_GMAIL", raising=False)
    monkeypatch.delenv("CLARITY_INTERNAL_SECRET", raising=False)
    with pytest.raises(IntegrationNotConnected):
        load_credentials(None, "u1", "gmail")


def test_dev_mode_falls_back_to_local_store(monkeypatch):
    monkeypatch.delenv("CLARITTY_PLATFORM_URL", raising=False)
    monkeypatch.delenv("CLARITTY_FAKE_CREDS_GMAIL", raising=False)
    from backend.integrations import store
    monkeypatch.setattr(store, "get_credentials", lambda db, uid, svc: {"access_token": "local"})
    assert load_credentials(None, "u1", "gmail") == {"access_token": "local"}


def test_persist_refreshed_noop_on_platform(monkeypatch):
    monkeypatch.setenv("CLARITTY_PLATFORM_URL", "http://platform.invalid")
    called = {"n": 0}
    from backend.integrations import store
    monkeypatch.setattr(store, "merge_credentials", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    persist_refreshed(None, "u1", "gmail", {"access_token": "x"})
    assert called["n"] == 0  # platform owns token lifecycle


def test_persist_refreshed_writes_local_in_dev(monkeypatch):
    monkeypatch.delenv("CLARITTY_PLATFORM_URL", raising=False)
    monkeypatch.delenv("CLARITTY_FAKE_CREDS_GMAIL", raising=False)
    called = {"n": 0}
    from backend.integrations import store
    monkeypatch.setattr(store, "merge_credentials", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    persist_refreshed(None, "u1", "gmail", {"access_token": "x"})
    assert called["n"] == 1
