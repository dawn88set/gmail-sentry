"""
The Gmail Sentry daily report — the one moment of clarity that arrives without
the user opening anything.

It answers four questions, in the order a business owner actually cares about:

    what needs me now      urgent mail
    what do I owe people   threads where the ball is in their court
    what is going quiet    people who haven't answered — where deals die
    what got handled       mail filed away without being asked

The third one is the reason this exists. Unanswered mail announces itself;
silence doesn't. A prospect who stopped replying twelve days ago generates no
notification, appears in no inbox, and is invisible until the quarter closes
badly. This is where that becomes visible.

Fans a single plain-text report out to every configured channel (Slack,
Telegram, Discord, WhatsApp). To-reply items link straight to the in-app
Approve & Send screen (via notify.app_focus_link). When there's genuinely
nothing it sends nothing — a report of "0 urgent · 0 to reply" is just noise,
and a daily message that's usually empty gets muted.

Called by the `app.send_digest` tool + the `send-digest` workflow (fired by the
DAILY `sentry-digest` trigger on-platform). Locally, exercise it with
POST /api/workflows/send-digest/execute.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend import models
from backend.services.sentry import get_config
from backend.services import activity, followups
from backend.integrations import notify

logger = logging.getLogger(__name__)


#: One definition, so the report and the in-app activity feed name the same
#: person the same way.
_short_sender = activity.short_sender


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


def _relative_age(when: Optional[datetime]) -> str:
    """"3d" / "20h" — compact enough to sit inside a bullet."""
    if not when:
        return ""
    hours = max(0, int((datetime.utcnow() - when).total_seconds() // 3600))
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d" if days < 14 else f"{days // 7}w"


def build_digest_text(db: Session, user_id: str) -> str:
    """The report body, or "" when nothing needs attention (→ skip sending)."""
    alerts = _open_alerts(db, user_id)
    urgent = [a for a in alerts if a.tier == "urgent"]
    to_reply = [a for a in alerts if a.tier == "needs_reply"]

    owed = followups.list_followups(db, user_id, state="owed", limit=5)
    cold = followups.list_followups(db, user_id, state="cold", limit=5)
    counts = followups.counts(db, user_id)

    filed_today = (
        db.query(models.ThreadFolder)
        .filter(
            models.ThreadFolder.user_id == user_id,
            models.ThreadFolder.status == "filed",
            models.ThreadFolder.filed_at >= datetime.utcnow() - timedelta(hours=24),
        )
        .count()
    )
    pending_folders = (
        db.query(models.MailFolder)
        .filter(
            models.MailFolder.user_id == user_id,
            models.MailFolder.status == "proposed",
        )
        .count()
    )

    if not (urgent or to_reply or owed or cold):
        return ""

    headline = f"{len(urgent)} urgent · {len(to_reply)} to reply"
    if counts["owed"] or counts["cold"]:
        headline += f" · {counts['owed']} you owe · {counts['cold']} going cold"

    lines: List[str] = ["🗞 Your inbox report", headline]

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

    if owed:
        lines.append("")
        lines.append("↩️ You owe a reply")
        for f in owed:
            who = f.counterparty_name or f.counterparty_email or "someone"
            age = _relative_age(f.last_inbound_at)
            # Lead with the ask, not the subject — the point of a report is to
            # be actionable without opening anything.
            what = f.ask_summary or f.subject or "(no subject)"
            lines.append(f"• {who} — {what}" + (f" ({age})" if age else ""))
        if counts["owed"] > len(owed):
            lines.append(f"  …and {counts['owed'] - len(owed)} more")

    if cold:
        lines.append("")
        lines.append("🧊 Going quiet — no answer from them")
        for f in cold:
            who = f.counterparty_name or f.counterparty_email or "someone"
            age = _relative_age(f.last_outbound_at or f.last_activity_at)
            subject = f.subject or "(no subject)"
            lines.append(f"• {who} — {subject}" + (f" · silent {age}" if age else ""))
        if counts["cold"] > len(cold):
            lines.append(f"  …and {counts['cold'] - len(cold)} more")

    if filed_today or pending_folders:
        lines.append("")
        bits = []
        if filed_today:
            bits.append(f"filed {filed_today} conversation{'s' if filed_today != 1 else ''}")
        if pending_folders:
            bits.append(
                f"{pending_folders} folder{'s' if pending_folders != 1 else ''} waiting for your OK"
            )
        lines.append("📁 " + " · ".join(bits))

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
    ok = [r for r in results if r["ok"]]
    if ok:
        # The report is the app's only unprompted output. Someone who wasn't at
        # their desk should be able to see that it went, and where.
        channels = ", ".join(sorted({str(r.get("channel") or "a channel") for r in ok}))
        activity.record(
            db, user_id, "report_sent",
            "Sent your daily report",
            detail=f"Delivered to {channels}." if channels else "",
            count=len(ok),
        )
        db.commit()
    return {
        "ok": True,
        "sent": bool(ok),
        "channels": results,
    }
