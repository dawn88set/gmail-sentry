"""
The Gmail Sentry digest — a scheduled "report" of what's waiting.

`run_digest` gathers the user's still-open alerts, groups them into urgent /
to-reply, and fans a single plain-text report out to every configured channel
(Slack, Telegram, Discord, WhatsApp). To-reply items link straight to the in-app
Approve & Send screen (via notify.app_focus_link). When the inbox is calm it
sends nothing — a report of "0 urgent · 0 to reply" is just noise.

Called by the `app.send_digest` tool + the `send-digest` workflow (fired by the
DAILY `sentry-digest` trigger on-platform). Locally, exercise it with
POST /api/workflows/send-digest/execute.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend import models
from backend.services.sentry import get_config
from backend.integrations import notify

logger = logging.getLogger(__name__)


def _short_sender(sender: str) -> str:
    """A compact display name from a "Name <a@b.com>" sender."""
    s = (sender or "").split("<")[0].strip().strip('"')
    return s or (sender or "someone")


def _open_alerts(db: Session, user_id: str, limit: int = 50) -> List[models.Alert]:
    now = datetime.utcnow()
    return (
        db.query(models.Alert)
        .filter(
            models.Alert.user_id == user_id,
            or_(
                models.Alert.status.in_(("new", "seen")),
                (models.Alert.status == "snoozed") & (models.Alert.snoozed_until <= now),
            ),
        )
        .order_by(models.Alert.created_at.desc())
        .limit(limit)
        .all()
    )


def build_digest_text(db: Session, user_id: str) -> str:
    """The report body, or "" when nothing needs attention (→ skip sending)."""
    alerts = _open_alerts(db, user_id)
    urgent = [a for a in alerts if a.tier == "urgent"]
    to_reply = [a for a in alerts if a.tier == "needs_reply"]
    if not urgent and not to_reply:
        return ""

    lines: List[str] = [
        "🗞 Your inbox report",
        f"{len(urgent)} urgent · {len(to_reply)} to reply",
    ]

    if urgent:
        lines.append("")
        lines.append("🔴 Urgent")
        for a in urgent[:5]:
            lines.append(f"• {a.subject or '(no subject)'} — {_short_sender(a.sender)}")
            if a.deep_link:
                lines.append(f"   {a.deep_link}")
        if len(urgent) > 5:
            lines.append(f"  …and {len(urgent) - 5} more")

    if to_reply:
        lines.append("")
        lines.append("🟡 To reply")
        for a in to_reply[:5]:
            ready = " · draft ready" if (a.reply_draft or "").strip() else ""
            lines.append(f"• {a.subject or '(no subject)'} — {_short_sender(a.sender)}{ready}")
            link = notify.app_focus_link(a.id) or a.deep_link or ""
            if link:
                lines.append(f"   👉 Approve & send: {link}")
        if len(to_reply) > 5:
            lines.append(f"  …and {len(to_reply) - 5} more")

    return "\n".join(lines).strip()


def _refresh_profile_if_stale(db: Session, user_id: str) -> None:
    """Keep the learned communication profile fresh — the daily digest is a natural,
    cheap once-a-day cadence. Best-effort; a failure never affects the report."""
    from datetime import timedelta
    from backend.services.learn import get_profile, learn_patterns

    try:
        prof = get_profile(db, user_id)
        if prof is None or not prof.refreshed_at or (
            datetime.utcnow() - prof.refreshed_at > timedelta(hours=20)
        ):
            learn_patterns(db, user_id)
    except Exception as e:  # noqa: BLE001 — learning is best-effort
        logger.info(f"profile refresh skipped ({type(e).__name__}: {e})")


def run_digest(db: Session, user_id: str) -> Dict[str, Any]:
    """Build + send the digest. Never raises (notify is best-effort + isolated).
    Returns a summary so the agent/workflow can report what happened."""
    _refresh_profile_if_stale(db, user_id)
    cfg = get_config(db, user_id)
    text = build_digest_text(db, user_id)
    if not text:
        return {"ok": True, "sent": False, "reason": "all_clear"}
    results = notify.notify_all(db, user_id, cfg, text)
    return {
        "ok": True,
        "sent": any(r["ok"] for r in results),
        "channels": results,
    }
