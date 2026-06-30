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


def _platform_mode(service: str) -> bool:
    """True when integration creds should come from the PLATFORM (managed model),
    not the app's local store: on-platform (`CLARITTY_PLATFORM_URL` set) or when a
    `CLARITTY_FAKE_CREDS_<SERVICE>` local override is present."""
    import os

    return bool(os.environ.get("CLARITTY_PLATFORM_URL")) or bool(
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


def _use_executor() -> bool:
    """Platform mode for ACTIONS: run the integration tool server-side via the
    platform executor (the decrypted token never touches the app). True when
    CLARITTY_PLATFORM_URL is set — i.e. there's a platform to delegate to (the
    Tier-2 local-dev env, or the hosted runtime)."""
    import os

    return bool(os.environ.get("CLARITTY_PLATFORM_URL"))


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
    import os
    import httpx

    base = (os.environ.get("CLARITTY_PLATFORM_URL") or "").rstrip("/")
    secret = (
        os.environ.get("CLARITY_INTERNAL_SECRET")
        or os.environ.get("CLARITTY_INTERNAL_SECRET")
        or ""
    )
    # The platform scopes each integration credential to (user, app). Send this
    # app's id so the platform's findConnected matches the app-scoped connection;
    # without it the lookup falls back to appId=null and reports NOT_CONNECTED even
    # after the user connected. Read both spellings (one-t/two-t) defensively.
    app_id = (
        os.environ.get("CLARITY_APP_ID")
        or os.environ.get("CLARITTY_APP_ID")
        or ""
    )
    if not base:
        raise IntegrationNotConnected(
            service, "platform executor unavailable (CLARITTY_PLATFORM_URL unset)"
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
        raise IntegrationError(
            service, f"{tool} failed: HTTP {resp.status_code} {resp.text[:200]}"
        )
    try:
        data = resp.json()
    except Exception:
        raise IntegrationError(service, f"{tool} returned a non-JSON response")
    return data.get("result", data) or {}


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

    Lets backend/integrations/routes.py `/test` work for every provider with an
    adapter instead of a hardcoded gmail branch.
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
    "_use_executor",
]
