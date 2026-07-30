"""
Slack adapter — real chat.postMessage via a bot token (API-key credential).

We use chat.postMessage (not an incoming webhook) deliberately: it returns the
message `ts`, a genuine external id, so the HITL `/approve` path has a real id to
record. An incoming webhook returns no id and so can't satisfy the
"never fake success" contract.

Credential shape (stored encrypted via the generic Connect flow, authKind=apikey):
    {"bot_token": "xoxb-..."}   (also accepts "token" / "api_key")

Usage from a publish callable:
    from backend.shared.adapters import slack
    def _post(db, user_id, item):
        return slack.post_message(db, user_id,
                                  channel=item.payload["channel"], text=item.body)
    # returns {"external_id": "<ts>", "account": "<channel id>"}
"""
import json
from typing import Any, Dict

import httpx

from backend.shared.adapters import (
    IntegrationNotConnected,
    IntegrationError,
    load_credentials,
    execute_tool,
    friendly_tool_error,
    _use_executor,
)

SERVICE = "slack"
API = "https://slack.com/api"


def _token(db, user_id: str) -> str:
    creds = load_credentials(db, user_id, SERVICE)  # raises IntegrationNotConnected
    token = creds.get("bot_token") or creds.get("token") or creds.get("api_key")
    if not token:
        raise IntegrationNotConnected(SERVICE, "No Slack bot token stored.")
    return token


def _call(db, user_id: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    token = _token(db, user_id)
    try:
        resp = httpx.post(
            f"{API}/{method}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise IntegrationError(SERVICE, f"{method} failed: {e}")
    # Slack returns 200 with {"ok": false, "error": "..."} for logical errors.
    if not data.get("ok"):
        raise IntegrationError(SERVICE, friendly_tool_error(SERVICE, 0, json.dumps(data)))
    return data


def post_message(db, user_id: str, *, channel: str, text: str) -> Dict[str, Any]:
    """Post a message; returns {"external_id": <ts>, "account": <channel id>}."""
    if not channel:
        raise IntegrationError(SERVICE, "channel is required")

    # Managed/platform path: the platform executor's `post_message` tool holds the
    # token and posts server-side; the app never sees the bot token.
    if _use_executor():
        res = execute_tool(SERVICE, "post_message", user_id, {"channel": channel, "text": text or ""})
        ts = res.get("ts") or res.get("external_id")
        if not ts:
            raise IntegrationError(SERVICE, "Slack executor returned no ts")
        return {"external_id": ts, "account": res.get("channel")}

    # Self-host path: post directly with the locally-stored bot token.
    data = _call(db, user_id, "chat.postMessage", {"channel": channel, "text": text or ""})
    ts = data.get("ts")
    if not ts:
        raise IntegrationError(SERVICE, "postMessage returned no ts")
    return {"external_id": ts, "account": data.get("channel")}


def connected_workspace(db, user_id: str) -> Dict[str, str]:
    """Best-effort `{team, team_id, url}` for the CONNECTED Slack workspace via
    `auth.test`, so the user can SEE which workspace alerts post to. A channel id
    from a *different* workspace fails with `channel_not_found` even when the bot is
    a member there — surfacing the connected workspace name is how the user spots
    that mismatch. Returns `{}` when unavailable (best-effort, never raises)."""
    def _shape(data: Dict[str, Any]) -> Dict[str, str]:
        return {
            "team": str(data.get("team") or data.get("team_name") or ""),
            "team_id": str(data.get("team_id") or ""),
            "url": str(data.get("url") or ""),
        }

    try:
        if _use_executor():
            # The platform executor tool id isn't guaranteed; try both spellings.
            for tool in ("auth_test", "auth.test"):
                try:
                    res = execute_tool(SERVICE, tool, user_id, {})
                    shaped = _shape(res if isinstance(res, dict) else {})
                    if shaped["team"] or shaped["team_id"]:
                        return shaped
                except IntegrationNotConnected:
                    return {}
                except IntegrationError:
                    continue
            return {}
        return _shape(_call(db, user_id, "auth.test", {}))
    except (IntegrationNotConnected, IntegrationError):
        return {}


def test_connection(db, user_id: str) -> Dict[str, Any]:
    """Liveness check via auth.test."""
    try:
        data = _call(db, user_id, "auth.test", {})
    except IntegrationNotConnected as e:
        return {"ok": False, "detail": str(e)}
    except IntegrationError as e:
        return {"ok": False, "detail": str(e)}
    return {"ok": True, "account": data.get("team")}
