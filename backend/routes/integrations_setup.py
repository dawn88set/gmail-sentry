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
    """Whether the integration is connected — resilient, FAIL-OPEN across signals.

    The connection state has proven fragile to probe in isolation, so we never
    show "not connected" off a single check that can false-negative:

      1. app-scoped broker probe (`platform_creds.is_connected` → /state). This
         matches the send path exactly, BUT the SDK's copy fail-closes to False
         whenever `CLARITY_INTERNAL_SECRET` (one spelling only) is empty, while
         the send path reads both spellings — so it can report False for an
         integration that actually works (Gmail scans, but badge says off).
      2. user-level credential probe (`fetch_for_user`) as a fallback.

    Connected if EITHER says so. A wrong "connected" is recoverable (the Send-
    test button surfaces the real error); a wrong "disconnected" hides a working
    integration and blocks the user — the worse failure. So we bias to showing
    connected and let the actual send be the source of truth."""
    try:
        from claritty_sdk.integrations import platform_creds
    except Exception:  # noqa: BLE001 — SDK not importable in bare seed dev
        return False

    probe = getattr(platform_creds, "is_connected", None)
    if probe is not None:
        try:
            if probe(integration_id, user_id):
                return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("is_connected probe for %s failed: %s", integration_id, exc)

    # Fallback / cross-check: a user-level credential exists → treat as connected
    # rather than hide a working integration behind a probe false-negative.
    try:
        platform_creds.fetch_for_user(integration_id, user_id)
        return True
    except Exception:  # noqa: BLE001
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
