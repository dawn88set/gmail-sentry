"""
What Sentry actually did — the app's record of its own work.

The app runs every five minutes and performs most of its value invisibly. It
files a conversation, retires an alert because the user answered from their
phone, notices a thread has gone quiet, reclassifies a prospect as a client
(which silently changes both where their mail is filed and how long silence is
tolerated). None of that was visible anywhere: the only time-ordered surface in
the product was a list of scan runs saying "20 scanned · 4 flagged", which
describes the machine rather than the mailbox.

Software that works while you aren't looking has to be able to say what it did,
or it can't be trusted and can't be corrected.

Two rules shape everything here.

**Record changes, not runs.** A scan that finds nothing writes nothing. 288
"scanned, nothing new" rows a day would bury the handful of events that matter,
and the point of the feed is that every line in it is worth reading. Scan cadence
already has a home on the dashboard.

**Write the sentence at record time.** Each row carries the copy it renders as,
plus a denormalised counterparty/folder. A folder renamed next month must not
retroactively rewrite what happened in this one, and the feed must not break
when the thing an event refers to is deleted.

`record()` deliberately does NOT commit — it's called inside transactions that
must stay atomic (an event claiming a thread was filed has to roll back with the
filing that failed). It also never raises: a bookkeeping failure must not take
down a scan.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend import models

logger = logging.getLogger(__name__)

#: The event vocabulary. Kept in one place because the frontend groups and
#: filters on these, and a typo'd kind would silently vanish from the feed.
KINDS = (
    "thread_filed",         # conversations labelled into a folder
    "filing_failed",        # Gmail refused the label — was invisible before
    "folder_proposed",      # a new folder is waiting for approval
    "folder_approved",
    "folder_rejected",
    "mail_flagged",         # an alert was raised
    "replies_drafted",      # N drafts written during one scan
    "reply_sent",           # the user approved and it really sent
    "nudge_sent",           # a follow-up chased a quiet thread
    "went_quiet",           # nobody has answered — where deals die
    "loop_closed",
    "alert_auto_closed",    # you replied from your phone, so we let it go
    "relationship_changed",  # changes filing + how long silence is normal
    "report_sent",
)

#: How the "this week" strip counts things. Each entry is (label, kinds, sum
#: the `count` column rather than the rows).
_SUMMARY = (
    ("filed", ("thread_filed",), True),
    ("flagged", ("mail_flagged",), False),
    ("drafted", ("replies_drafted",), True),
    ("sent", ("reply_sent", "nudge_sent"), False),
    ("went_quiet", ("went_quiet",), False),
)


def short_sender(sender: str) -> str:
    """A person's name out of a `"Name" <a@b.com>` header.

    Lives here rather than in each caller so the feed, the daily report and the
    notification all name the same person the same way — a report that says
    "Dana Levi" beside a feed that says "dana@acme.co" reads like two products.
    """
    s = (sender or "").split("<")[0].strip().strip('"')
    return s or (sender or "someone")


def record(
    db: Session,
    user_id: str,
    kind: str,
    title: str,
    *,
    detail: str = "",
    subject_type: str = "",
    subject_id: str = "",
    counterparty_email: str = "",
    folder_name: str = "",
    count: int = 0,
    meta: Optional[Dict[str, Any]] = None,
    at: Optional[datetime] = None,
) -> Optional[models.ActivityEvent]:
    """Append one event. Does not commit — the caller owns the transaction, so
    the event lands atomically with the change it describes.

    Never raises. This is bookkeeping; if it fails, the scan it was recording
    should still finish and the user should still get their mail triaged.
    """
    if not user_id or not kind:
        return None
    try:
        ev = models.ActivityEvent(
            user_id=user_id,
            at=at or datetime.utcnow(),
            kind=kind,
            title=(title or "")[:500],
            detail=(detail or "")[:2000],
            subject_type=subject_type or "",
            subject_id=subject_id or "",
            counterparty_email=(counterparty_email or "")[:320],
            folder_name=folder_name or "",
            count=int(count or 0),
            meta=meta or None,
        )
        db.add(ev)
        return ev
    except Exception as e:  # noqa: BLE001 — a lost log line is never worth a failed scan
        logger.warning(f"activity.record({kind}) failed: {type(e).__name__}: {e}")
        return None


def feed(
    db: Session,
    user_id: str,
    *,
    days: int = 14,
    limit: int = 120,
    kinds: Optional[List[str]] = None,
) -> List[models.ActivityEvent]:
    """This user's events, newest first, within a window."""
    q = db.query(models.ActivityEvent).filter(
        models.ActivityEvent.user_id == user_id,
        models.ActivityEvent.at >= datetime.utcnow() - timedelta(days=max(1, days)),
    )
    if kinds:
        q = q.filter(models.ActivityEvent.kind.in_(kinds))
    return q.order_by(models.ActivityEvent.at.desc()).limit(max(1, min(limit, 500))).all()


def summary(db: Session, user_id: str, *, days: int = 7) -> Dict[str, int]:
    """Counts for the "this week" strip.

    Some kinds carry a `count` (one row can mean "6 conversations filed"), so
    those are summed rather than tallied. Counting rows there would understate
    the work by roughly the size of a thread.
    """
    since = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (
        db.query(models.ActivityEvent)
        .filter(
            models.ActivityEvent.user_id == user_id,
            models.ActivityEvent.at >= since,
        )
        .all()
    )
    out = {label: 0 for label, _, _ in _SUMMARY}
    for label, kinds, use_count in _SUMMARY:
        for r in rows:
            if r.kind not in kinds:
                continue
            out[label] += max(1, int(r.count or 0)) if use_count else 1
    out["days"] = days
    out["total"] = len(rows)
    return out


def by_day(events: List[models.ActivityEvent]) -> List[Dict[str, Any]]:
    """Group an already-ordered feed into day buckets, preserving order.

    Done server-side so the app and the daily report describe a "day" the same
    way, rather than one of them re-deriving it in the browser's timezone.
    """
    groups: List[Dict[str, Any]] = []
    for ev in events:
        day = ev.at.date().isoformat() if ev.at else ""
        if not groups or groups[-1]["day"] != day:
            groups.append({"day": day, "label": _day_label(ev.at), "events": []})
        groups[-1]["events"].append(ev.to_dict())
    return groups


def _day_label(when: Optional[datetime]) -> str:
    if not when:
        return ""
    today = datetime.utcnow().date()
    delta = (today - when.date()).days
    if delta <= 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if delta < 7:
        return when.strftime("%A")
    return when.strftime("%-d %B") if hasattr(when, "strftime") else ""
