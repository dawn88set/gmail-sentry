"""Setup/onboarding surface: which integrations this app needs, and whether the
current user has connected each one.

This powers the in-app **first-run setup checklist** + Integrations page so a
user who opens a freshly generated app immediately sees "Connect LinkedIn to
publish" instead of hitting a silent failure. It is read-only and NEVER returns
credentials — only the app's declared integrations and a boolean connected flag
derived from the platform's per-user credential store (the same store the
agent/tools read via ctx.integration()).

backend/main.py auto-includes `router`.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from backend.security import require_user

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache(maxsize=1)
def _required_integrations() -> List[Dict[str, str]]:
    """The integrations this app declares it needs, read once from intelligence.yaml.

    Returns a list of ``{"id", "name"}``. Empty when the app declares none (a
    self-contained app) or intelligence.yaml is absent (local seed dev) — both fine.
    """
    # The manifest (intelligence.yaml preferred, app.yaml legacy) is materialized
    # next to the backend package in generated apps.
    from backend.manifest_path import resolve_manifest_path

    path = resolve_manifest_path()
    if not path:
        return []
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read intelligence.yaml integrations: %s", exc)
        return []

    out: List[Dict[str, str]] = []
    for entry in manifest.get("integrations") or []:
        if isinstance(entry, str):
            out.append({"id": entry, "name": _humanize(entry)})
        elif isinstance(entry, dict) and entry.get("id"):
            out.append(
                {"id": entry["id"], "name": entry.get("name") or _humanize(entry["id"])}
            )
    return out


def _humanize(integration_id: str) -> str:
    return integration_id.replace("_", " ").replace("-", " ").title()


def _is_connected(integration_id: str, user_id: str) -> bool:
    """True only when the integration is connected for THIS (user, app) — the
    exact strict, app-scoped check `execute_tool` performs, via the broker's
    liveness endpoint (POST /internal/integrations/state with this app's id).

    Why not the old `platform_creds.fetch_for_user`: that probed the credential
    store at USER level (no app_id), so it reported "connected" whenever any
    user-level credential existed — e.g. a Slack connected on the platform's
    Integrations tab — even though no APP-SCOPED connection existed. The badge
    then said Connected while every send 409'd (`findConnected` is per-(user,app)).
    This lies no more: badge status now matches what a real send will do."""
    import httpx

    base = (os.environ.get("CLARITTY_PLATFORM_URL") or "").rstrip("/")
    secret = (
        os.environ.get("CLARITY_INTERNAL_SECRET")
        or os.environ.get("CLARITTY_INTERNAL_SECRET")
        or ""
    )
    app_id = os.environ.get("CLARITY_APP_ID") or os.environ.get("CLARITTY_APP_ID") or ""
    if not base:
        return False
    body: Dict[str, Any] = {"userId": user_id, "integrationCatalogId": integration_id}
    if app_id:
        body["appId"] = app_id
    try:
        resp = httpx.post(
            f"{base}/internal/integrations/state",
            headers={"X-Claritty-Internal": secret},
            json=body,
            timeout=15,
        )
        if resp.status_code >= 400:
            return False
        return bool(resp.json().get("connected"))
    except Exception as exc:  # noqa: BLE001 — transient errors ⇒ "unknown/not connected"
        logger.warning("connection probe for %s failed: %s", integration_id, exc)
        return False


@router.get("/api/integrations/required")
def required_integrations(user_id: str = Depends(require_user)) -> Dict[str, Any]:
    """List the app's required integrations with per-user connection status.

    Shape: ``{ integrations: [{id, name, connected}], all_connected: bool }``.
    The frontend setup checklist renders this; when ``all_connected`` is false
    it shows a connect prompt for each unconnected integration.
    """
    required = _required_integrations()
    items = [
        {**entry, "connected": _is_connected(entry["id"], user_id)}
        for entry in required
    ]
    # app_id lets the setup checklist scope the connect flow to THIS app
    # (per-app integration connections). None locally / when unset.
    app_id = None
    try:
        from backend.config import get_platform_config

        app_id = get_platform_config().clarity_app_id
    except Exception:  # pragma: no cover - config import/shape is best-effort
        app_id = None
    return {
        "integrations": items,
        "all_connected": all(i["connected"] for i in items) if items else True,
        "app_id": app_id,
    }
