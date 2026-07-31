"""
Open loops — what you owe people, and what you're waiting on.

This is the feature the ledger was built for. Gmail Sentry could already tell
you an email arrived; it could not tell you that you owe Sarah a quote, that
Mark went quiet nine days after you sent pricing, or that you already answered
from your phone. All three are reads over `thread_messages`.

## The states

    awaiting_you    they spoke last and it's your move
    awaiting_them   you spoke last; the clock is running on them
    going_cold      awaiting_them, past what's normal for this person
    snoozed         deliberately parked until a date
    done            the loop closed
    ignored         the user said this isn't a loop

`ball` is the raw ledger fact (who spoke last). `state` is that fact plus time
and intent. They're stored separately so a snooze doesn't destroy the underlying
truth.

## Aging is per-relationship, not a global constant

A lawyer who answers in three days should not be chased after one. A customer
who normally answers within two hours is already cold at two days. So
`stale_after_hours` comes from the counterparty's own median reply time (B2),
clamped, and tightened further by any explicit deadline the triage step
extracted. A single global "3 days" threshold would be wrong for nearly everyone.

## The boundary with Alert

A new message that needs a reply is an **Alert** for its first
`OWED_AFTER_HOURS`; after that the alert has done its job and the **thread**
becomes an owed follow-up. `list_followups` excludes threads whose latest
inbound still has a live alert, so `active alerts + owed + overdue waiting` is a
partition rather than three overlapping piles. Without that the headline count
double-counts and stops being trustworthy.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models
from backend.services import counterparty as cp_service
from backend.services import ledger

logger = logging.getLogger(__name__)

#: How long a fresh inbound message stays "an alert" before the thread becomes
#: an owed follow-up. Keeps the two lists disjoint.
OWED_AFTER_HOURS = 24

#: Bounds on per-relationship staleness. One day is the floor because nobody
#: wants to be chased the same morning; two weeks is the ceiling because past
#: that a thread is dead, not pending.
MIN_STALE_HOURS = 24
MAX_STALE_HOURS = 24 * 14
DEFAULT_STALE_HOURS = 72

#: States that still want the user's attention.
OPEN_STATES = ("awaiting_you", "awaiting_them", "going_cold")

AWAITING_YOU = "awaiting_you"
AWAITING_THEM = "awaiting_them"
GOING_COLD = "going_cold"
SNOOZED = "snoozed"
DONE = "done"
IGNORED = "ignored"


def stale_after_hours_for(cp: Optional[models.Counterparty], *, due_at: Optional[datetime] = None,
                          now: Optional[datetime] = None) -> int:
    """How long silence is normal for this person, in hours.

    Twice their median reply time: answering slower than usual is normal
    variance, twice as slow is a signal. Clamped, then tightened by an explicit
    deadline — if they said "by Friday", Friday is the deadline regardless of
    how leisurely they usually are.
    """
    base = DEFAULT_STALE_HOURS
    if cp is not None and cp.their_median_reply_h:
        base = int(round(float(cp.their_median_reply_h) * 2.0))
    hours = max(MIN_STALE_HOURS, min(MAX_STALE_HOURS, base))

    # A customer's silence costs more, so we notice it sooner.
    if cp is not None and (cp.relationship or "") == cp_service.CUSTOMER:
        hours = min(hours, 48)

    if due_at is not None:
        ref = now or ledger.utcnow()
        until_due = int((due_at - ref).total_seconds() // 3600)
        if until_due > 0:
            hours = min(hours, until_due)
    return max(1, hours)


#: Importance floor used when scoring risk. A counterparty scores 0 until the
#: ledger has enough history to rank them — on a fresh install that's everyone.
#: Multiplying straight through would make every loop risk 0 and leave the list
#: unordered, so an unranked person is treated as mildly important: a two-week
#: silence still outranks something that arrived this morning. Muted people
#: never reach here (sync_followups skips them), so a 0 here means "unknown",
#: not "known to be worthless".
UNRANKED_IMPORTANCE = 25


def risk_score(fu: models.FollowUp, *, now: Optional[datetime] = None) -> int:
    """0-100. Importance × how overdue it is.

    Ordering the list by this is what makes it useful: a two-day silence from a
    key customer should sit above a two-week silence from someone who never
    replies anyway.
    """
    ref = now or ledger.utcnow()
    clock = fu.state_changed_at or fu.last_activity_at or fu.created_at or ref
    stale = max(1, int(fu.stale_after_hours or DEFAULT_STALE_HOURS))
    elapsed_h = max(0.0, (ref - clock).total_seconds() / 3600.0)

    # 0 at fresh, 1.0 at the staleness threshold, 2.0 at double it.
    overdue = min(2.0, elapsed_h / float(stale))
    importance = max(int(fu.importance or 0), UNRANKED_IMPORTANCE)
    if fu.state == AWAITING_YOU:
        # You owe them: the deadline matters more than the drift.
        if fu.due_at:
            past_due = (ref - fu.due_at).total_seconds() / 3600.0
            overdue = max(overdue, min(2.0, 1.0 + past_due / 24.0) if past_due > 0 else overdue)
    return max(0, min(100, int(round(importance * (overdue / 2.0)))))


# ── deriving state from the ledger ──────────────────────────────────────────

def _thread_identity(db: Session, user_id: str, thread_id: str) -> Dict[str, str]:
    """Counterparty + subject for a thread, from its hydrated inbound messages."""
    rows = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.thread_id == thread_id,
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .all()
    )
    email = name = subject = ""
    for m in rows:
        if m.direction == "in" and m.counterparty_email and not email:
            email = m.counterparty_email
            raw = m.sender or ""
            name = raw.split("<")[0].strip().strip('"') if "<" in raw else ""
        if m.subject and not subject:
            subject = m.subject
        if not email and m.direction == "out" and m.counterparty_email:
            email = m.counterparty_email
    return {"email": email, "name": name, "subject": subject}


def _has_live_alert(db: Session, user_id: str, thread_id: str, *, now: datetime) -> bool:
    """Is this thread still being handled as a fresh ALERT?

    While it is, it must not also appear as an owed follow-up — that's the
    boundary that keeps the two lists a partition instead of a double count.
    """
    cutoff = now - timedelta(hours=OWED_AFTER_HOURS)
    return (
        db.query(models.Alert)
        .filter(
            models.Alert.user_id == user_id,
            models.Alert.thread_id == thread_id,
            models.Alert.status.in_(("new", "seen")),
            models.Alert.created_at >= cutoff,
        )
        .first()
        is not None
    )


def sync_followups(db: Session, user_id: str, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """Re-derive every open loop from the ledger. No Gmail calls, no LLM calls.

    Idempotent: safe to run on every scan and on demand.
    """
    ref = now or ledger.utcnow()
    balls = ledger.thread_ball(db, user_id)
    if not balls:
        return {"opened": 0, "closed": 0, "went_cold": 0, "reopened": 0}

    existing = {
        f.thread_id: f
        for f in db.query(models.FollowUp)
        .filter(models.FollowUp.user_id == user_id)
        .all()
    }
    counterparties = {
        c.email: c
        for c in db.query(models.Counterparty)
        .filter(models.Counterparty.user_id == user_id)
        .all()
    }

    stats = {"opened": 0, "closed": 0, "went_cold": 0, "reopened": 0}

    for thread_id, ball in balls.items():
        fu = existing.get(thread_id)

        # The user settled this thread by hand; don't resurrect it unless they
        # actually spoke again.
        if fu is not None and fu.state == IGNORED:
            continue

        ident = _thread_identity(db, user_id, thread_id)
        cp = counterparties.get(ident["email"]) if ident["email"] else None

        # Bulk mail is not a relationship you can owe a reply to.
        if ident["email"] and cp_service.is_bulk_sender(ident["email"]):
            continue
        if cp is not None and cp.muted:
            continue

        last_in, last_out = ball.get("last_in"), ball.get("last_out")
        last_activity = max([t for t in (last_in, last_out) if t], default=None)

        if fu is None:
            fu = models.FollowUp(
                user_id=user_id,
                thread_id=thread_id,
                created_at=ref,
                state_changed_at=ref,
            )
            db.add(fu)
            existing[thread_id] = fu
            stats["opened"] += 1

        prev_state = fu.state
        prev_ball = fu.ball

        fu.counterparty_email = ident["email"] or fu.counterparty_email
        if ident["name"]:
            fu.counterparty_name = ident["name"]
        if ident["subject"]:
            fu.subject = ident["subject"]
        fu.last_inbound_at = last_in
        fu.last_outbound_at = last_out
        fu.last_activity_at = last_activity
        fu.importance = int(cp.importance) if cp is not None else 0
        fu.stale_after_hours = stale_after_hours_for(cp, due_at=fu.due_at, now=ref)

        new_ball = ball["ball"]
        # The ball changing hands is what restarts the clock. Re-deriving the
        # same ball must NOT reset it, or nothing would ever age.
        if new_ball != prev_ball:
            fu.ball = new_ball
            fu.state_changed_at = last_activity or ref
            fu.nudge_count = 0 if new_ball == "you" else fu.nudge_count

        if fu.state == SNOOZED and fu.snoozed_until and fu.snoozed_until > ref:
            continue  # parked on purpose

        if new_ball == "you":
            # They spoke last. If we'd previously closed this because they never
            # replied, their reply reopens it.
            if fu.state in (DONE,):
                stats["reopened"] += 1
            if prev_state == AWAITING_THEM or prev_state == GOING_COLD:
                fu.closed_reason = "they_replied"
            fu.state = AWAITING_YOU
            fu.closed_at = None
        else:
            clock = fu.state_changed_at or last_out or ref
            elapsed_h = (ref - clock).total_seconds() / 3600.0
            if elapsed_h >= float(fu.stale_after_hours or DEFAULT_STALE_HOURS):
                if fu.state != GOING_COLD:
                    stats["went_cold"] += 1
                fu.state = GOING_COLD
            else:
                fu.state = AWAITING_THEM
            fu.closed_at = None

        fu.risk = risk_score(fu, now=ref)

    db.commit()
    return stats


def record_outbound(
    db: Session,
    user_id: str,
    *,
    thread_id: str,
    message_id: str,
    to_email: str = "",
    subject: str = "",
    sent_at: Optional[datetime] = None,
    alert_id: Optional[str] = None,
) -> Optional[models.FollowUp]:
    """Register a send this app just performed, and flip the loop to them.

    Called the moment a reply or nudge really lands, so the user sees "waiting on
    them, I'll check back Thursday" instead of the thread silently disappearing —
    which is what used to happen and is exactly how a quote goes unanswered for
    three weeks unnoticed.

    Best-effort: the mail is already sent, so nothing here may raise.
    """
    ts = sent_at or ledger.utcnow()
    try:
        ledger.record_sent_message(
            db, user_id,
            gmail_message_id=message_id,
            thread_id=thread_id,
            to_email=to_email,
            subject=subject,
            sent_at=ts,
        )

        fu = (
            db.query(models.FollowUp)
            .filter(
                models.FollowUp.user_id == user_id,
                models.FollowUp.thread_id == thread_id,
            )
            .first()
        )
        if fu is None:
            fu = models.FollowUp(
                user_id=user_id, thread_id=thread_id, created_at=ts,
            )
            db.add(fu)

        cp = cp_service.get(db, user_id, to_email) if to_email else None
        fu.counterparty_email = fu.counterparty_email or (cp.email if cp else "")
        fu.subject = fu.subject or subject or ""
        fu.ball = "them"
        fu.state = AWAITING_THEM
        fu.state_changed_at = ts
        fu.last_outbound_at = ts
        fu.last_activity_at = ts
        fu.snoozed_until = None
        fu.closed_at = None
        fu.closed_reason = ""
        fu.importance = int(cp.importance) if cp is not None else int(fu.importance or 0)
        fu.stale_after_hours = stale_after_hours_for(cp, due_at=None, now=ts)
        fu.risk = risk_score(fu, now=ts)

        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            db.rollback()
            return None

        if alert_id:
            alert = (
                db.query(models.Alert)
                .filter(models.Alert.id == alert_id, models.Alert.user_id == user_id)
                .first()
            )
            if alert is not None:
                alert.followup_id = fu.id
        db.commit()
        return fu
    except Exception as e:  # noqa: BLE001 — the send already succeeded
        logger.warning("follow-up bookkeeping failed for thread %s: %s", thread_id, e)
        db.rollback()
        return None


def close_alerts_replied_elsewhere(db: Session, user_id: str, *, now: Optional[datetime] = None) -> int:
    """Close alerts for threads the user has since answered anywhere.

    The user replies from the Gmail app on their phone; the ledger's `in:sent`
    sweep sees it within one interval. Without this the alert keeps demanding
    attention for something already handled, which is the fastest way to teach
    someone to ignore the app.
    """
    ref = now or ledger.utcnow()
    balls = ledger.thread_ball(db, user_id)
    if not balls:
        return 0

    open_alerts = (
        db.query(models.Alert)
        .filter(
            models.Alert.user_id == user_id,
            models.Alert.status.in_(("new", "seen")),
            models.Alert.thread_id.isnot(None),
        )
        .all()
    )
    closed = 0
    for alert in open_alerts:
        ball = balls.get(alert.thread_id or "")
        if not ball or ball.get("ball") != "them":
            continue
        last_out = ball.get("last_out")
        # Only if the outbound came AFTER the alert was raised — otherwise an
        # old reply in a long thread would close a genuinely new message.
        if last_out and alert.created_at and last_out >= alert.created_at:
            alert.status = "done"
            if alert.reply_status == "none":
                alert.reply_status = "sent"  # answered, just not through this app
            closed += 1
    if closed:
        db.commit()
    return closed


# ── reads ───────────────────────────────────────────────────────────────────

def list_followups(
    db: Session,
    user_id: str,
    *,
    state: str = "open",
    limit: int = 100,
    now: Optional[datetime] = None,
) -> List[models.FollowUp]:
    """Open loops, worst first.

    `state` accepts open | owed | waiting | cold | snoozed | done | all.
    Threads whose newest inbound is still a live alert are excluded from the
    owed views — see the module docstring on the Alert/FollowUp boundary.
    """
    ref = now or ledger.utcnow()
    q = db.query(models.FollowUp).filter(models.FollowUp.user_id == user_id)

    if state == "open":
        q = q.filter(models.FollowUp.state.in_(OPEN_STATES))
    elif state == "owed":
        q = q.filter(models.FollowUp.state == AWAITING_YOU)
    elif state == "waiting":
        q = q.filter(models.FollowUp.state.in_((AWAITING_THEM, GOING_COLD)))
    elif state == "cold":
        q = q.filter(models.FollowUp.state == GOING_COLD)
    elif state == "snoozed":
        q = q.filter(models.FollowUp.state == SNOOZED)
    elif state == "done":
        q = q.filter(models.FollowUp.state.in_((DONE, IGNORED)))
    # "all" → no filter

    rows = q.order_by(models.FollowUp.risk.desc(), models.FollowUp.state_changed_at.asc()).limit(limit * 2).all()

    if state in ("open", "owed"):
        rows = [
            f for f in rows
            if f.state != AWAITING_YOU or not _has_live_alert(db, user_id, f.thread_id, now=ref)
        ]
    return rows[:limit]


def counts(db: Session, user_id: str, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """The numbers the dashboard and widget show. Kept in one place so the app
    and the widget can never disagree about the headline figure."""
    ref = now or ledger.utcnow()
    owed = len(list_followups(db, user_id, state="owed", limit=500, now=ref))
    waiting = (
        db.query(models.FollowUp)
        .filter(models.FollowUp.user_id == user_id, models.FollowUp.state == AWAITING_THEM)
        .count()
    )
    cold = (
        db.query(models.FollowUp)
        .filter(models.FollowUp.user_id == user_id, models.FollowUp.state == GOING_COLD)
        .count()
    )
    return {"owed": owed, "waiting": waiting, "cold": cold, "open_loops": owed + waiting + cold}


def snooze(db: Session, fu: models.FollowUp, hours: int) -> models.FollowUp:
    hours = max(1, min(int(hours or 3), 24 * 14))
    fu.state = SNOOZED
    fu.snoozed_until = ledger.utcnow() + timedelta(hours=hours)
    db.commit()
    return fu


def mark_done(db: Session, fu: models.FollowUp, reason: str = "you_closed") -> models.FollowUp:
    fu.state = DONE
    fu.closed_reason = reason
    fu.closed_at = ledger.utcnow()
    db.commit()
    return fu


def mark_ignored(db: Session, fu: models.FollowUp) -> models.FollowUp:
    """"This isn't a follow-up." Sticky — the sweep won't resurrect it."""
    fu.state = IGNORED
    fu.closed_reason = "not_a_followup"
    fu.closed_at = ledger.utcnow()
    db.commit()
    return fu
