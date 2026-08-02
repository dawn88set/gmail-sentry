"""
True statements about how the user's mail actually works.

The app already knows things about a business that its owner has never seen
written down: that they answer clients in two hours and prospects in a day, that
four relationships account for most of their inbox, that three deals have gone
silent. That knowledge lived only inside ranking maths and never surfaced.

**Every number here is a countable fact.** No modelled hours-saved, no imputed
money value, no "you're 12% faster this month". The temptation to dress this up
is strong and the cost is total: one invented figure a user can check and
disprove makes every other number in the app suspect, including the ones their
mail depends on.

Where a figure has a real caveat, it ships WITH the caveat rather than without
it. `caveat` is a field on the payload, not a footnote someone might drop:

  * reply times come from the ledger, whose timestamps are recovered from query
    windows, so they're honest to the hour and not to the minute;
  * closed loops undercount, because `closed_at` is nulled when a loop reopens;
  * nothing is visible past the ledger's history horizon.

Read-only. Computed on request from tables the scan already maintains; nothing
here writes, and nothing here calls a model.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from sqlalchemy.orm import Session

from backend import models
from backend.services import activity, counterparty, followups

logger = logging.getLogger(__name__)

#: How relationship classes are named to the user. Mirrors the People screen —
#: the same person must not be a "customer" here and a "Client" there.
REL_LABEL = {
    counterparty.CUSTOMER: "Clients",
    counterparty.PROSPECT: "Prospects",
    counterparty.INTERNAL: "Colleagues",
    counterparty.VENDOR: "Suppliers",
    counterparty.UNKNOWN: "Everyone else",
}

#: Ordered the way a business owner cares, not alphabetically.
REL_ORDER = (
    counterparty.CUSTOMER,
    counterparty.PROSPECT,
    counterparty.VENDOR,
    counterparty.INTERNAL,
    counterparty.UNKNOWN,
)

#: Below this, a median is one or two conversations pretending to be a pattern.
MIN_SAMPLE = 3


def _median(values: List[int]) -> Optional[int]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return int(vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2)


def response_profile(db: Session, user_id: str) -> Dict[str, Any]:
    """How fast the user answers each kind of person, and how fast they're
    answered back. The asymmetry is the interesting part: someone the user
    answers in an hour who takes three days to answer them is a different
    business relationship from the reverse.
    """
    rows = (
        db.query(models.Counterparty)
        .filter(
            models.Counterparty.user_id == user_id,
            models.Counterparty.muted.is_(False),
            models.Counterparty.relationship != counterparty.BULK,
        )
        .all()
    )

    groups: List[Dict[str, Any]] = []
    for rel in REL_ORDER:
        members = [c for c in rows if (c.relationship or "unknown") == rel]
        if len(members) < 1:
            continue
        yours = _median([c.your_median_reply_h for c in members if c.your_median_reply_h is not None])
        theirs = _median([c.their_median_reply_h for c in members if c.their_median_reply_h is not None])
        sample = len([c for c in members if c.your_median_reply_h is not None])
        groups.append({
            "relationship": rel,
            "label": REL_LABEL.get(rel, rel.title()),
            "people": len(members),
            "you_answer_in_h": yours,
            "they_answer_in_h": theirs,
            # Rendered as a hint, not hidden — a thin sample is still worth
            # showing as long as it's labelled as thin.
            "thin": sample < MIN_SAMPLE,
        })

    return {
        "groups": groups,
        "caveat": (
            "Times come from when messages were observed, so they’re accurate to "
            "about the hour rather than the minute."
        ),
    }


def attention(db: Session, user_id: str, *, limit: int = 6) -> Dict[str, Any]:
    """Where the user's attention actually goes — ranked by revealed preference
    (who they answer) rather than by who sends the most, which is the ranking
    every inbox already gives them and the one that's wrong."""
    rows = (
        db.query(models.Counterparty)
        .filter(
            models.Counterparty.user_id == user_id,
            models.Counterparty.muted.is_(False),
            models.Counterparty.relationship != counterparty.BULK,
        )
        .order_by(models.Counterparty.importance.desc(), models.Counterparty.thread_count.desc())
        .limit(max(1, limit))
        .all()
    )
    return {
        "people": [
            {
                "email": c.email,
                "display_name": c.display_name or "",
                "relationship": c.relationship or "unknown",
                "relationship_label": REL_LABEL.get(c.relationship or "", "Everyone else"),
                "thread_count": int(c.thread_count or 0),
                "your_reply_rate": int(c.your_reply_rate or 0),
                "importance": int(c.importance or 0),
            }
            for c in rows
        ],
    }


def at_risk(db: Session, user_id: str, *, limit: int = 5) -> Dict[str, Any]:
    """The threads nobody has answered — named, because "3 going cold" is a
    number and "Northwind hasn't replied in 12 days" is a decision."""
    cold = followups.list_followups(db, user_id, state="cold", limit=max(1, limit))
    now = datetime.utcnow()
    return {
        "counts": followups.counts(db, user_id),
        "threads": [
            {
                "id": f.id,
                "thread_id": f.thread_id,
                "who": f.counterparty_name or f.counterparty_email or "someone",
                "email": f.counterparty_email or "",
                "subject": f.subject or "",
                "silent_days": max(
                    0,
                    int(((now - (f.last_outbound_at or f.last_activity_at or now)).total_seconds()) // 86400),
                ),
                "risk": int(f.risk or 0),
            }
            for f in cold
        ],
    }


def handled(db: Session, user_id: str, *, days: int = 30) -> Dict[str, Any]:
    """What the app did, over a longer window than the feed's strip.

    Sourced from the activity log rather than recomputed from state, so this and
    the feed can never disagree — a discrepancy between "what happened" and "how
    much happened" is exactly the kind of thing that destroys trust in both.
    """
    out = activity.summary(db, user_id, days=days)

    folders_active = (
        db.query(func.count(models.MailFolder.id))
        .filter(models.MailFolder.user_id == user_id, models.MailFolder.status == "active")
        .scalar()
    ) or 0
    folders_pending = (
        db.query(func.count(models.MailFolder.id))
        .filter(models.MailFolder.user_id == user_id, models.MailFolder.status == "proposed")
        .scalar()
    ) or 0

    return {
        **out,
        "folders_active": int(folders_active),
        "folders_pending": int(folders_pending),
    }


def coverage(db: Session, user_id: str) -> Dict[str, Any]:
    """How much history any of this rests on.

    Shown because an insight drawn from four days of mail deserves to be read
    differently from one drawn from six weeks, and the user is the only one who
    can make that judgement.
    """
    first = (
        db.query(func.min(models.ThreadMessage.ts_hi))
        .filter(models.ThreadMessage.user_id == user_id)
        .scalar()
    )
    messages = (
        db.query(func.count(models.ThreadMessage.id))
        .filter(models.ThreadMessage.user_id == user_id)
        .scalar()
    ) or 0
    threads = (
        db.query(func.count(func.distinct(models.ThreadMessage.thread_id)))
        .filter(models.ThreadMessage.user_id == user_id)
        .scalar()
    ) or 0
    days = 0
    if first:
        days = max(0, int((datetime.utcnow() - first).total_seconds() // 86400))
    return {
        "days": days,
        "messages": int(messages),
        "threads": int(threads),
        "since": first.isoformat() if first else None,
    }


def build(db: Session, user_id: str) -> Dict[str, Any]:
    """Everything the Insights tab renders, in one request."""
    return {
        "coverage": coverage(db, user_id),
        "response": response_profile(db, user_id),
        "attention": attention(db, user_id),
        "at_risk": at_risk(db, user_id),
        "handled": handled(db, user_id),
    }
