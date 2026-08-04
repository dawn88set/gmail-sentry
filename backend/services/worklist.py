"""
What your email needs from you today — one ranked list, not four inventories.

The app already knew all of this. It just never said it in one place. Today
showed alerts in one section, open loops in another, junk counts in a third and
a scan log in a fourth, leaving the user to assemble a plan out of four
different framings. That is inventory: *what you have*. Work is *what to do,
in what order, by when*.

Three things were computed and then thrown away visually:

  * the **ask** — `extract_ask` pulls "needs the revised quote before Friday"
    out of the mail, and only the Follow-ups screen ever showed it. The Alerts
    screen, where fresh urgent mail actually lands, showed the subject line.
  * the **deadline** — `resolve_due` parses real dates and refuses ambiguous
    ones, and `due_at` was rendered nowhere in the entire UI.
  * the **risk** — importance × overdue, used to sort and never shown.

So this merges the two lists that represent obligations into one, phrases each
row as the thing to do rather than the thing that arrived, and sorts by what
costs most to ignore.

It invents nothing. No ask means the subject; no deadline means no deadline
shown. A fabricated due date would be worse than none, because the whole point
is that the user can trust the ordering without checking it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from sqlalchemy.orm import Session

from backend import models
from backend.services import activity, counterparty, followups
from backend.services.ledger import utcnow

logger = logging.getLogger(__name__)

#: What the user is being asked to do. Three verbs, because a worklist with more
#: kinds than that stops being scannable.
REPLY = "reply"    # fresh mail waiting on an answer
OWE = "owe"        # a thread where the ball has been in your court a while
CHASE = "chase"    # they've gone quiet; the action is to nudge

#: Counted as "done" for the day. Deliberately only things that actually moved a
#: conversation — dismissing an alert is not work done.
DONE_KINDS = ("reply_sent", "nudge_sent", "loop_closed", "alert_auto_closed")


def _due_label(due: Optional[datetime], now: datetime) -> tuple[str, bool]:
    """("due Friday" | "2 days overdue" | "", overdue?). Empty when we don't
    actually know — never a guess."""
    if not due:
        return "", False
    delta = due - now
    hours = delta.total_seconds() / 3600
    if hours < -24:
        return f"{int(-hours // 24)} days overdue", True
    if hours < 0:
        return "overdue", True
    if hours < 12:
        return "due today", False
    if hours < 36:
        return "due tomorrow", False
    if hours < 24 * 7:
        return f"due {due.strftime('%A')}", False
    return f"due {due.strftime('%-d %b')}", False


def _waited(since: Optional[datetime], now: datetime, verb: str) -> str:
    if not since:
        return ""
    h = max(0, int((now - since).total_seconds() // 3600))
    if h < 1:
        return f"{verb} just now"
    if h < 24:
        return f"{verb} {h}h"
    d = h // 24
    return f"{verb} {d} day{'s' if d != 1 else ''}"


def _short(sender: str) -> str:
    return activity.short_sender(sender)


def _email_only(sender: str) -> str:
    """Bare address from a From header — `Dana Levi <dana@x.co>` → `dana@x.co`.

    Alerts store the raw header while follow-ups store the address, so a lookup
    keyed on one has to normalise the other or every alert row silently loses
    its company.
    """
    raw = (sender or "").strip()
    if "<" in raw and ">" in raw:
        raw = raw[raw.rfind("<") + 1 : raw.rfind(">")]
    return raw.strip().strip('"').lower()


def build(db: Session, user_id: str, *, limit: int = 12) -> Dict[str, Any]:
    """The ranked list, plus what's already been cleared today.

    The two sources are disjoint by construction: `list_followups` excludes
    threads whose newest inbound still has a live alert (see followups.py on the
    Alert/FollowUp boundary), so nothing appears twice and the count can be
    trusted.
    """
    now = utcnow()
    items: List[Dict[str, Any]] = []

    # Which company each correspondent belongs to. "Sam Ortiz" means nothing to
    # an owner with two hundred contacts; "Sam Ortiz · Northwind Ltd" is the
    # account they can picture, and it ties this list to the Accounts screen so
    # the two read as one product rather than two lists of the same mail. One
    # query, reused for every row.
    company_by_email = {
        (c.email or "").lower(): counterparty.company_of(c)
        for c in db.query(models.Counterparty)
        .filter(models.Counterparty.user_id == user_id)
        .all()
        if c.email
    }

    # 1. Fresh mail waiting on an answer.
    alerts = (
        db.query(models.Alert)
        .filter(
            models.Alert.user_id == user_id,
            models.Alert.tier.in_(("urgent", "needs_reply")),
            or_(
                models.Alert.status.in_(("new", "seen")),
                (models.Alert.status == "snoozed") & (models.Alert.snoozed_until <= now),
            ),
        )
        .order_by(models.Alert.created_at.desc())
        .limit(40)
        .all()
    )
    # The ask lives on the thread's loop, not the alert — carry it across so a
    # row reads "send the revised pricing", not "Re: Q3".
    asks = {
        f.thread_id: f
        for f in db.query(models.FollowUp)
        .filter(models.FollowUp.user_id == user_id)
        .all()
    }
    for a in alerts:
        loop = asks.get(a.thread_id or "")
        due = loop.due_at if loop else None
        due_label, overdue = _due_label(due, now)
        items.append({
            "id": f"alert:{a.id}",
            "kind": REPLY,
            "who": _short(a.sender or ""),
            "email": a.sender or "",
            "company": company_by_email.get(_email_only(a.sender or ""), ""),
            "headline": (loop.ask_summary if loop and loop.ask_summary else (a.subject or "(no subject)")),
            "subject": a.subject or "",
            "urgent": a.tier == "urgent",
            "due_at": due.isoformat() if due else None,
            "due_label": due_label,
            "overdue": overdue,
            "age_label": _waited(a.created_at, now, "arrived"),
            "reply_ready": bool((a.reply_draft or "").strip()) and a.reply_status != "sent",
            "thread_id": a.thread_id or "",
            "alert_id": a.id,
            "followup_id": loop.id if loop else "",
            "score": (200 if overdue else 0) + (60 if a.tier == "urgent" else 30)
                     + (int(loop.importance or 0) if loop else 0),
        })

    # 2. Threads where the ball has been in your court, and 3. ones gone quiet.
    for f in followups.list_followups(db, user_id, state="open", limit=40, now=now):
        chasing = f.state == followups.GOING_COLD
        due_label, overdue = _due_label(f.due_at, now)
        items.append({
            "id": f"loop:{f.id}",
            "kind": CHASE if chasing else OWE,
            "who": f.counterparty_name or f.counterparty_email or "someone",
            "email": f.counterparty_email or "",
            "company": company_by_email.get((f.counterparty_email or "").lower(), ""),
            "headline": f.ask_summary or f.subject or "(no subject)",
            "subject": f.subject or "",
            "urgent": False,
            "due_at": f.due_at.isoformat() if f.due_at else None,
            "due_label": due_label,
            "overdue": overdue,
            "age_label": _waited(
                f.last_outbound_at if chasing else f.last_inbound_at, now,
                "silent" if chasing else "waiting",
            ),
            "reply_ready": False,
            "thread_id": f.thread_id or "",
            "alert_id": "",
            "followup_id": f.id,
            "score": (200 if overdue else 0) + int(f.risk or 0),
        })

    items.sort(key=lambda i: (-i["score"], i["who"]))
    shown = items[:limit]

    # Something you can finish. An inbox is endless; a list you cleared is the
    # difference between a worklist and an anxiety list, and it's the one thing
    # the app never told anyone.
    done_today = (
        db.query(models.ActivityEvent)
        .filter(
            models.ActivityEvent.user_id == user_id,
            models.ActivityEvent.kind.in_(DONE_KINDS),
            models.ActivityEvent.at >= now - timedelta(hours=24),
        )
        .count()
    )

    return {
        "items": shown,
        "total": len(items),
        "done_today": done_today,
        # How much of this is one tap. A busy owner triages by "what can I
        # clear in two minutes" before anything else.
        "ready_to_send": sum(1 for i in shown if i["reply_ready"]),
        "overdue": sum(1 for i in items if i["overdue"]),
    }
