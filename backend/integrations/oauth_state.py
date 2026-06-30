"""
Signed, time-limited OAuth state for CSRF protection — no DB table required.

The state binds the OAuth round-trip to a specific user + integration and is HMAC
signed, so a third party cannot forge a callback that attaches their account to
someone else's user id (the flaw in the old generated code, which used
state=user_id).
"""
import base64
import hashlib
import hmac
import json
import os
import time

_MAX_AGE_SECONDS = 600


def _secret() -> bytes:
    return (
        os.getenv("APP_ENCRYPTION_KEY")
        or os.getenv("ALB_AUTH_SECRET")
        or "dev-oauth-state-secret"
    ).encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_state(user_id: str, service: str) -> str:
    payload = {
        "uid": user_id,
        "svc": service,
        "n": _b64(os.urandom(9)),
        "ts": int(time.time()),
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def verify_state(state: str, user_id: str, service: str) -> bool:
    try:
        body, sig = state.split(".", 1)
        expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return False
        payload = json.loads(_unb64(body).decode())
        if payload.get("uid") != user_id or payload.get("svc") != service:
            return False
        if int(time.time()) - int(payload.get("ts", 0)) > _MAX_AGE_SECONDS:
            return False
        return True
    except Exception:
        return False
