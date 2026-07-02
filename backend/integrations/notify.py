"""
Multi-channel attention notifications — APP-OWNED, BROKER-ONLY.

Fans a formatted alert out to EVERY configured channel (Slack, Telegram, Discord,
Microsoft Teams, WhatsApp) via the platform broker (`execute_tool`), so the token
never touches app code. A channel is "active" when its destination is set on
SentryConfig (e.g. `slack_channel`, `telegram_chat_id`) AND the integration is
connected. Per-channel failures are isolated — one dead channel never blocks the
others, and a scan is never failed by a notification hiccup.

Destinations (channel id / chat id / phone) are non-secret routing and live on
SentryConfig; the credentials (bot token, SID, OAuth) live in the platform broker.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple

from backend.shared.adapters import (
    execute_tool,
    IntegrationNotConnected,
    IntegrationError,
)

logger = logging.getLogger(__name__)


def _slack(dest: str, text: str) -> Dict[str, Any]:
    return {"channel": dest, "text": text}


def _telegram(dest: str, text: str) -> Dict[str, Any]:
    return {"chat_id": dest, "text": text}


def _discord(dest: str, text: str) -> Dict[str, Any]:
    return {"channel_id": dest, "content": text}


def _teams(dest: str, text: str) -> Dict[str, Any]:
    return {"thread_id": dest, "content": text}


def _whatsapp(dest: str, text: str) -> Dict[str, Any]:
    return {"to": dest, "body": text}


# (label, broker service id, tool, SentryConfig destination attr, arg builder)
CHANNELS: List[Tuple[str, str, str, str, Callable[[str, str], Dict[str, Any]]]] = [
    ("slack", "slack", "post_message", "slack_channel", _slack),
    ("telegram", "telegram", "send_message", "telegram_chat_id", _telegram),
    ("discord", "discord", "send_message", "discord_channel_id", _discord),
    ("whatsapp", "twilio", "send_whatsapp", "whatsapp_to", _whatsapp),
    # Microsoft Teams deferred: its catalog tool is `teams.*` but the integration
    # id is `microsoft-teams`, which the manifest validator rejects. Re-add once
    # the platform catalog aligns the tool prefix with the integration id.
]


def configured_channels(cfg) -> List[str]:
    """Channel labels that have a destination set (for UI / status)."""
    return [
        label
        for (label, _svc, _tool, attr, _b) in CHANNELS
        if (getattr(cfg, attr, "") or "").strip()
    ]


def _send_one(user_id: str, service: str, tool: str, build, dest: str, text: str):
    """Send to one channel. Returns (ok, error) — the error carries the provider's
    real message (the broker surfaces it) so the UI can show why it failed."""
    try:
        execute_tool(service, tool, user_id, build(dest, text))
        return True, ""
    except IntegrationNotConnected:
        return False, "not connected — connect/reconnect this channel"
    except IntegrationError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def notify_all(db, user_id: str, cfg, text: str) -> List[Dict[str, Any]]:
    """Send `text` to every configured channel. Returns a per-channel result list
    ``[{channel, ok, error}]``. Never raises — channels are best-effort + isolated."""
    results: List[Dict[str, Any]] = []
    for label, service, tool, attr, build in CHANNELS:
        dest = (getattr(cfg, attr, "") or "").strip()
        if not dest:
            continue
        ok, err = _send_one(user_id, service, tool, build, dest, text)
        if not ok:
            logger.info("%s send failed: %s", label, err)
        results.append({"channel": label, "ok": ok, "error": err})
    return results


def test_notify(db, user_id: str, cfg, only: str = "") -> List[Dict[str, Any]]:
    """Send a test message to configured channels (or just `only`) and return a
    detailed per-channel result so the user can verify each one + see any error."""
    text = "🔔 Gmail Sentry test — attention alerts will arrive here."
    results: List[Dict[str, Any]] = []
    for label, service, tool, attr, build in CHANNELS:
        if only and label != only:
            continue
        dest = (getattr(cfg, attr, "") or "").strip()
        if not dest:
            if only:  # explicitly asked for a channel with no destination
                results.append(
                    {"channel": label, "ok": False, "error": "no destination set", "configured": False}
                )
            continue
        ok, err = _send_one(user_id, service, tool, build, dest, text)
        results.append({"channel": label, "ok": ok, "error": err, "configured": True})
    return results
