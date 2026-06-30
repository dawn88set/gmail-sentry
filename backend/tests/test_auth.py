"""
W3 — auth hardening: get_current_user must be fail-closed in production.

In prod (ALB_AUTH_SECRET set) identity must come from the Claritty edge (verified
X-Claritty-Auth admission secret + X-User-Id); a forged X-User-Id or a Bearer
token must NOT be trusted. In local dev (no ALB secret) the conveniences remain.
"""

import pytest
from fastapi import HTTPException

from backend.main import get_current_user


def test_prod_requires_edge_admission_secret(monkeypatch):
    monkeypatch.setenv("ALB_AUTH_SECRET", "s3cret")

    # Forged X-User-Id without the admission secret → 403 (fail closed).
    with pytest.raises(HTTPException) as e:
        get_current_user(x_user_id="attacker", x_claritty_auth=None, authorization=None)
    assert e.value.status_code == 403

    # Wrong admission secret → 403.
    with pytest.raises(HTTPException) as e:
        get_current_user(x_user_id="u", x_claritty_auth="wrong", authorization=None)
    assert e.value.status_code == 403

    # Valid secret but no user → 401.
    with pytest.raises(HTTPException) as e:
        get_current_user(x_user_id=None, x_claritty_auth="s3cret", authorization=None)
    assert e.value.status_code == 401

    # A Bearer token is NOT identity in production → 403.
    with pytest.raises(HTTPException) as e:
        get_current_user(x_user_id=None, x_claritty_auth=None, authorization="Bearer u")
    assert e.value.status_code == 403

    # Valid edge stamp + user → returns the user.
    assert get_current_user(x_user_id="u1", x_claritty_auth="s3cret", authorization=None) == "u1"


def test_dev_conveniences_when_no_alb_secret(monkeypatch):
    monkeypatch.delenv("ALB_AUTH_SECRET", raising=False)
    monkeypatch.setenv("NODE_ENV", "development")

    assert get_current_user(x_user_id="u2", x_claritty_auth=None, authorization=None) == "u2"
    assert get_current_user(x_user_id=None, x_claritty_auth=None, authorization="Bearer u3") == "u3"
    assert get_current_user(x_user_id=None, x_claritty_auth=None, authorization=None) == "dev-user"


def test_no_secret_and_not_dev_rejects(monkeypatch):
    monkeypatch.delenv("ALB_AUTH_SECRET", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    with pytest.raises(HTTPException) as e:
        get_current_user(x_user_id=None, x_claritty_auth=None, authorization=None)
    assert e.value.status_code == 401
