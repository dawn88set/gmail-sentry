"""
B3 — Integration adapter layer (shared).

Typed, thin wrappers over the per-user encrypted credential store
(backend.integrations.store) + provider clients, so app code and the HITL
`/approve` path call `gmail.send(...)` / `slack.post_message(...)` instead of
re-authoring OAuth/HTTP plumbing per app.

This package's `__init__` defines the two outcomes every adapter must signal so
the route factory (backend/shared/item_routes.py) can map them to the correct
HTTP semantics the platform mandates:

- `IntegrationNotConnected` → HTTP 409 + a "connect this service" prompt.
  NEVER fake success when a service isn't connected (CLAUDE.md / INTEGRATIONS.md).
- `IntegrationError` (or any other raised exception) → HTTP 5xx; the item stays
  open for retry and the failure is recorded honestly.

Provider modules (gmail, gcal, gdrive, slack, crm, accounting) are added in B3
and import these symbols.
"""

from typing import Any, Dict, Optional


# Common provider error codes → plain-English hints. The platform/provider
# returns a terse machine code (e.g. Slack's `channel_not_found`); surfacing that
# raw — or worse, the whole JSON body — reads as "a json error" to the user. Map
# the ones users actually hit to an actionable sentence.
_SLACK_ERR_HINTS = {
    "channel_not_found": "Slack can’t find that channel/ID. Make sure it’s a channel ID (starts with C) or member ID (starts with U) — not a name — AND that it’s in the SAME workspace you connected (an ID from another workspace fails even if the bot is in it). Easiest: pick it from the channel list.",
    "not_in_channel": "the bot isn’t in that channel — /invite it there, then try again",
    "channel_is_archived": "that Slack channel is archived",
    "is_archived": "that Slack channel is archived",
    "invalid_auth": "Slack sign-in expired — reconnect Slack",
    "account_inactive": "the Slack account is inactive — reconnect Slack",
    "token_revoked": "Slack access was revoked — reconnect Slack",
    "missing_scope": "the Slack app is missing a permission — reconnect Slack to re-grant it",
    "restricted_action": "your Slack workspace policy blocked this action",
    "user_not_found": "that Slack member ID wasn’t found — copy it from Profile → More → Copy member ID",
    "rate_limited": "Slack is rate-limiting — wait a moment and retry",
}


import re

# Noise the platform prepends to a wrapped provider message — strip it so the
# user sees the actual reason, not the plumbing.
_ERR_NOISE_PREFIX = re.compile(
    r"^(integration tool execution failed|tool execution failed)\s*[:\-]\s*",
    re.IGNORECASE,
)


def _looks_like_code(s: str) -> bool:
    """A short snake_case token (e.g. `channel_not_found`) is a provider error
    CODE we can map to a hint. A class name like `HttpException` or a full
    sentence is not — prefer the human `message` field in those cases."""
    return bool(re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", s or ""))


def _extract_error_code(text: str) -> str:
    """Pull the most useful error string out of a (possibly JSON) response body,
    so the caller shows a clean line instead of a raw JSON blob.

    Handles two shapes the platform actually returns:
      • Slack-native logical error: ``{"ok": false, "error": "channel_not_found"}``
        → the mappable code lives in ``error``.
      • Platform envelope: ``{"success": false, "error": "HttpException",
        "message": "<the real reason>"}`` → ``error`` is a useless class name;
        the human reason is in ``message``.
    """
    import json

    text = (text or "").strip()
    if not text:
        return ""
    try:
        body = json.loads(text)
    except Exception:  # noqa: BLE001 — not JSON, use the raw text (trimmed)
        return _ERR_NOISE_PREFIX.sub("", text)[:300]

    def _from(d: Dict[str, Any]) -> str:
        err = d.get("error")
        msg = d.get("message") or d.get("detail")
        # A real provider code (channel_not_found) is mappable → prefer it.
        if isinstance(err, str) and _looks_like_code(err):
            return err.strip()
        # Otherwise the human message wins over a class-name `error`.
        if isinstance(msg, str) and msg.strip():
            return _ERR_NOISE_PREFIX.sub("", msg.strip())
        if isinstance(err, str) and err.strip():
            return err.strip()
        return ""

    if isinstance(body, dict):
        got = _from(body)
        if got:
            return got
        result = body.get("result")
        if isinstance(result, dict):
            got = _from(result)
            if got:
                return got
    return _ERR_NOISE_PREFIX.sub("", text)[:300]


def friendly_tool_error(service: str, status: int, text: str) -> str:
    """A user-facing message for a failed integration tool call. Maps known
    provider codes to plain English; falls back to the raw code, then the status."""
    code = _extract_error_code(text)
    if service == "slack":
        # Exact-match first (Slack-native `{"error":"channel_not_found"}`)…
        hint = _SLACK_ERR_HINTS.get(code.lower())
        if hint:
            return hint
        # …then scan for a known code embedded in a wrapped message (the platform
        # nests it, e.g. "…conversations.list… failed: missing_scope").
        tokens = set(re.findall(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", (code or "").lower()))
        for known, hint in _SLACK_ERR_HINTS.items():
            if known in tokens:
                return hint
    if code:
        return code
    return f"HTTP {status}" if status else "the send failed"


class IntegrationNotConnected(Exception):
    """The user has not connected the service this action needs (→ 409)."""

    def __init__(self, service: str, message: Optional[str] = None):
        self.service = service
        super().__init__(message or f"{service} is not connected.")


class IntegrationError(Exception):
    """A connected integration call genuinely failed (→ 5xx, retryable)."""

    def __init__(self, service: str, message: str):
        self.service = service
        super().__init__(message)


def _platform_base() -> str:
    """The platform base URL, reading BOTH env spellings (two-t `CLARITTY_` and
    one-t `CLARITY_`). main.py and validate_startup.py already read both because
    the platform's injected spelling is inconsistent across deployments; the
    adapters MUST too. If they read only the two-t spelling and the deployment
    sets only the one-t one, every executor call raises NOT_CONNECTED and the app
    shows a false 'Connect Gmail' even though Gmail is connected."""
    import os

    return (
        os.environ.get("CLARITTY_PLATFORM_URL")
        or os.environ.get("CLARITY_PLATFORM_URL")
        or ""
    ).rstrip("/")


def _platform_mode(service: str) -> bool:
    """True when integration creds should come from the PLATFORM (managed model),
    not the app's local store: on-platform (`CLARITTY_PLATFORM_URL` set) or when a
    `CLARITTY_FAKE_CREDS_<SERVICE>` local override is present."""
    import os

    return bool(_platform_base()) or bool(
        os.environ.get(f"CLARITTY_FAKE_CREDS_{service.upper()}")
    )


def load_credentials(db, user_id: str, service: str) -> Dict[str, Any]:
    """Return the caller's decrypted credentials for `service`, or raise
    IntegrationNotConnected.

    Managed model (the platform-brokered default): when running on/with the
    platform, creds live in platform KMS — resolve them through the SDK platform
    resolver (`claritty_sdk.integrations.platform_creds.fetch_for_user`), which
    also honors the `CLARITTY_FAKE_CREDS_<SERVICE>` local override. This is what
    keeps honest-publish truthful on-platform: a 409 only when GENUINELY not
    connected, not a false 409 because creds aren't in the app DB.

    Self-host / dev fallback: read the app's local encrypted store
    (`backend.integrations.store`).
    """
    if _platform_mode(service):
        try:
            from claritty_sdk.integrations.platform_creds import (
                fetch_for_user,
                CredentialsNotAvailable,
            )
        except Exception:  # SDK resolver unavailable → fall back to local store
            fetch_for_user = None
        if fetch_for_user is not None:
            try:
                creds = fetch_for_user(service, user_id)
            except CredentialsNotAvailable as e:
                raise IntegrationNotConnected(service, str(e))
            data = getattr(creds, "data", None) or {}
            if not data:
                raise IntegrationNotConnected(service)
            return data

    # Self-host / dev: the app's own encrypted store.
    from backend.integrations import store

    creds = store.get_credentials(db, user_id, service)
    if not creds:
        raise IntegrationNotConnected(service)
    return creds


def resolve_app_id() -> str:
    """The platform app id used to scope integration connections to THIS app.

    The platform stores each credential under (user, app); a call that omits the
    app id falls back to appId=null in the platform's findConnected and comes back
    NOT_CONNECTED even though the user connected the integration — the "green
    badge but every action says connect" bug. Read both env spellings, then fall
    back to the parsed platform config (which the runtime may populate even when
    the raw env spelling differs). Empty string when genuinely unknown."""
    import os

    app_id = (
        os.environ.get("CLARITY_APP_ID")
        or os.environ.get("CLARITTY_APP_ID")
        or ""
    ).strip()
    if app_id:
        return app_id
    try:
        from backend.config import get_platform_config

        cfg_id = (get_platform_config().clarity_app_id or "").strip()
        # 'local-dev-app' is the config default, not a real platform id — don't
        # send it (it would scope to a nonexistent app).
        if cfg_id and cfg_id != "local-dev-app":
            return cfg_id
    except Exception:  # noqa: BLE001 — config import/shape is best-effort
        pass
    return ""


def _use_executor() -> bool:
    """Platform mode for ACTIONS: run the integration tool server-side via the
    platform executor (the decrypted token never touches the app). True when
    CLARITTY_PLATFORM_URL is set — i.e. there's a platform to delegate to (the
    Tier-2 local-dev env, or the hosted runtime). Reads both env spellings."""
    return bool(_platform_base())


def execute_tool(
    service: str, tool: str, user_id: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """Run an integration tool through the PLATFORM executor — the canonical,
    secure path: the platform holds the decrypted token and performs the call; the
    app only receives the result (it never holds the token). This is how Claritty
    manages integration *actions*; prefer it over fetching creds + calling the
    provider from app code.

    POSTs to ``${CLARITTY_PLATFORM_URL}/internal/integrations/tools/{service}/{tool}/execute``
    with the internal-dispatch secret. Maps NOT_CONNECTED (409) → IntegrationNotConnected
    and any other failure → IntegrationError, so honest-publish holds. Requires
    CLARITTY_PLATFORM_URL + CLARITY_INTERNAL_SECRET (Tier-2 local dev, or hosted).
    """
    import json
    import os
    import httpx

    base = _platform_base()  # reads BOTH env spellings (one-t / two-t)
    secret = (
        os.environ.get("CLARITY_INTERNAL_SECRET")
        or os.environ.get("CLARITTY_INTERNAL_SECRET")
        or ""
    )
    # The platform scopes each integration credential to (user, app). Send this
    # app's id so the platform's findConnected matches the app-scoped connection;
    # without it the lookup falls back to appId=null and reports NOT_CONNECTED even
    # after the user connected (the "connected badge but every scan says connect"
    # bug). resolve_app_id() covers both env spellings AND the parsed config.
    app_id = resolve_app_id()
    if not base:
        raise IntegrationNotConnected(
            service, "platform executor unavailable (CLARITTY_PLATFORM_URL / CLARITY_PLATFORM_URL unset)"
        )
    url = f"{base}/internal/integrations/tools/{service}/{tool}/execute"
    body = {"userId": user_id, "arguments": arguments}
    if app_id:
        body["appId"] = app_id
    try:
        resp = httpx.post(
            url,
            headers={"X-Claritty-Internal": secret},
            json=body,
            timeout=30,
        )
    except httpx.HTTPError as e:
        raise IntegrationError(service, f"{tool} executor call failed: {e}")
    if resp.status_code == 409:
        raise IntegrationNotConnected(service)
    if resp.status_code >= 400:
        # Humanize the provider error — never surface the raw JSON body.
        raise IntegrationError(
            service, friendly_tool_error(service, resp.status_code, resp.text)
        )
    try:
        data = resp.json()
    except Exception:
        raise IntegrationError(service, f"{tool} returned a non-JSON response")
    result = data.get("result", data) or {}
    # Some providers (notably Slack) return HTTP 200 with {"ok": false, "error": …}
    # for logical failures. Treat that as a real failure with a clean message,
    # rather than silently reporting success (which would fake a delivered alert).
    if isinstance(result, dict) and result.get("ok") is False and result.get("error"):
        raise IntegrationError(
            service, friendly_tool_error(service, 0, json.dumps(result))
        )
    return result


def persist_refreshed(db, user_id: str, service: str, updates: Dict[str, Any]) -> None:
    """Persist refreshed tokens after a provider call (self-host/dev only).

    On the platform the token lifecycle is owned by the platform credential
    store (KMS), so this is a no-op there — the local UserIntegration table is
    not the source of truth in the managed model.
    """
    if _platform_mode(service):
        return

    from backend.integrations import store

    clean = {k: v for k, v in updates.items() if v is not None}
    if clean:
        store.merge_credentials(db, user_id, service, clean, connected=True)


# Per-provider liveness checks. Maps a catalog integration id to the adapter
# module exposing `test_connection(db, user_id) -> {"ok": bool, ...}`. Lazily
# imported in run_liveness() to avoid the circular import (provider modules
# import this package). Add a provider here when its adapter ships.
_LIVENESS = {
    "gmail": "backend.shared.adapters.gmail",
    "slack": "backend.shared.adapters.slack",
}


def run_liveness(db, user_id: str, service: str):
    """Run a provider's liveness check, or return None if it has no adapter.

    Generic over providers instead of a hardcoded gmail branch, so any
    connection-health check works for every service that has an adapter.
    """
    import importlib

    mod_path = _LIVENESS.get(service)
    if not mod_path:
        return None
    mod = importlib.import_module(mod_path)
    check = getattr(mod, "test_connection", None)
    if check is None:
        return None
    return check(db, user_id)


__all__ = [
    "IntegrationNotConnected",
    "IntegrationError",
    "load_credentials",
    "persist_refreshed",
    "run_liveness",
    "execute_tool",
    "friendly_tool_error",
    "resolve_app_id",
    "_platform_base",
    "_use_executor",
]
