"""Refreshing the Gmail token: before it dies, and kept once it exists.

Two faults this fixes, both in the path this app owns (on the platform the
broker holds the credentials and we have no refresh token to refresh):

  * `token_expiry` was written on every refresh and read by nothing, so expiry
    was only ever discovered by being told 401 — a guaranteed wasted round trip
    on the first call after the hour, paid again by every operation, because
    each one builds a fresh client.
  * a refreshed token was persisted only on an operation's success path, so a
    token fetched for a call that then failed was thrown away and the next call
    refreshed again.
"""
from datetime import datetime, timedelta

import pytest

from backend.integrations.gmail_client import GmailClient, GmailNotConnected


def _creds(expiry=None, **kw):
    d = {
        "access_token": "at-old",
        "refresh_token": "rt",
        "client_id": "cid",
        "client_secret": "sec",
    }
    if expiry is not None:
        d["token_expiry"] = expiry
    d.update(kw)
    return d


# ── knowing the token is dead before spending a request on it ───────────────


def test_a_token_past_its_expiry_is_known_to_be_dead():
    c = GmailClient(_creds(expiry=(datetime.utcnow() - timedelta(minutes=5)).isoformat()))
    assert c._access_token_expired() is True


def test_a_fresh_token_is_not_refreshed():
    c = GmailClient(_creds(expiry=(datetime.utcnow() + timedelta(minutes=30)).isoformat()))
    assert c._access_token_expired() is False


def test_it_refreshes_a_minute_early_rather_than_mid_flight():
    """A token that dies during a request costs a wasted call and a retry."""
    c = GmailClient(_creds(expiry=(datetime.utcnow() + timedelta(seconds=30)).isoformat()))
    assert c._access_token_expired() is True


def test_an_expiry_we_cannot_read_is_not_assumed_dead():
    """Guessing "expired" would refresh on every single call."""
    assert GmailClient(_creds(expiry="not-a-date"))._access_token_expired() is False
    assert GmailClient(_creds())._access_token_expired() is False


def test_a_timezone_aware_expiry_is_understood():
    aware = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
    assert GmailClient(_creds(expiry=aware))._access_token_expired() is False


# ── keeping the token once it exists ────────────────────────────────────────


def test_a_refreshed_token_is_persisted_immediately(monkeypatch):
    saved = []
    c = GmailClient(_creds(), on_refresh=lambda creds: saved.append(creds["access_token"]))

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "at-new", "expires_in": 3600}

    monkeypatch.setattr("backend.integrations.gmail_client.httpx.post", lambda *a, **k: _Resp())
    c._refresh()

    assert saved == ["at-new"]          # kept at the moment of refresh…
    assert c.credentials["access_token"] == "at-new"


def test_persisting_can_never_fail_the_call_it_happened_during(monkeypatch):
    def _explode(_creds):
        raise RuntimeError("database is down")

    c = GmailClient(_creds(), on_refresh=_explode)

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "at-new", "expires_in": 3600}

    monkeypatch.setattr("backend.integrations.gmail_client.httpx.post", lambda *a, **k: _Resp())
    c._refresh()                        # must not raise

    assert c.credentials["access_token"] == "at-new"


def test_no_refresh_token_says_reconnect_rather_than_failing_obscurely():
    c = GmailClient({"access_token": "at"})
    with pytest.raises(GmailNotConnected) as e:
        c._refresh()
    assert "reconnect" in str(e.value).lower()
