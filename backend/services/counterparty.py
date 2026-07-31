"""
Who it would cost the user to ignore.

The scan used to inject the top five `comm_profiles.vip_senders` as synthetic
triage rules. That list ranks people by how much mail they send, which is close
to the opposite of what matters — a daily newsletter outranks the client who
writes twice a month.

This module ranks by **revealed preference** instead, entirely from the thread
ledger: does the user actually reply to this person, how fast, across how many
threads, and does the person reply back. Those are choices the user already made;
we're just reading them.

Everything here is plain SQL over `thread_messages`. No Gmail calls, no LLM
calls, so it's cheap enough to recompute whenever it's useful.

## Two honest limitations

**Outbound has no recipient.** The broker's search stubs don't carry one, and we
deliberately never spend a metered `get_message` on our own sent mail. So a
reply is attributed to the counterparty of its *thread*, inferred from the
inbound messages in that thread. Right for ordinary correspondence; approximate
on a large group thread.

**Latency is window-resolution.** `ts_hi` is the upper bound of the query window
a message was found in, so "replied in about 3 hours" is exactly that — about.
Good enough to tell a same-day correspondent from a next-week one, which is all
the aging logic needs.
"""
from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend import models
from backend.services.ledger import utcnow
from backend.services.onboarding import _BULK_LOCALPARTS

logger = logging.getLogger(__name__)

#: Relationship classes. `unknown` is honest and common — most correspondents
#: never accumulate enough signal to classify, and guessing would be worse.
CUSTOMER = "customer"
PROSPECT = "prospect"
INTERNAL = "internal"
VENDOR = "vendor"
BULK = "bulk"
UNKNOWN = "unknown"

#: Subjects that mark a supplier relationship rather than a customer one.
_VENDOR_HINTS = ("invoice", "receipt", "billing", "subscription", "payment due", "renewal notice")

#: Importance below which a counterparty isn't worth CRM enrichment or a slot in
#: the triage rule set.
INTERESTING = 40


def _local_part(email: str) -> str:
    return (email or "").split("@")[0].lower()


def is_bulk_sender(email: str) -> bool:
    """A no-reply / newsletter / notifications address — never a person to owe."""
    lp = _local_part(email)
    if lp in _BULK_LOCALPARTS:
        return True
    # "noreply-bounces", "notifications+xyz" and friends.
    return any(lp.startswith(f"{b}-") or lp.startswith(f"{b}+") for b in _BULK_LOCALPARTS)


def looks_like_a_person(display_name: str, email: str) -> bool:
    """A weak, cheap signal: humans tend to have a two-part display name."""
    name = (display_name or "").strip()
    if not name or "@" in name:
        return False
    return len(name.split()) >= 2 and not is_bulk_sender(email)


def _hours(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


# ── deriving the facts ──────────────────────────────────────────────────────

def _thread_owner(messages: List[models.ThreadMessage]) -> Tuple[str, str]:
    """(email, display_name) of the counterparty on a thread.

    Taken from the inbound messages, since outbound carries no recipient. The
    most frequent inbound sender wins, which keeps a thread attributed to the
    person the user is actually talking to even when a cc chimes in once.
    """
    counts: Dict[str, int] = {}
    names: Dict[str, str] = {}
    for m in messages:
        if m.direction != "in":
            continue
        email = (m.counterparty_email or "").strip().lower()
        if not email:
            continue
        counts[email] = counts.get(email, 0) + 1
        if m.sender and email not in names:
            raw = m.sender
            names[email] = raw.split("<")[0].strip().strip('"') if "<" in raw else ""
    if not counts:
        return "", ""
    email = max(counts, key=lambda e: counts[e])
    return email, names.get(email, "")


def _thread_stats(messages: List[models.ThreadMessage]) -> Dict[str, object]:
    """Per-thread facts the importance formula needs.

    `you_replied` means an outbound message exists AFTER their first inbound —
    not merely that the thread contains one, which would also be true of a
    thread the user started and then abandoned.
    """
    ordered = sorted(messages, key=lambda m: (m.ts_hi, m.gmail_message_id or ""))
    ins = [m for m in ordered if m.direction == "in"]
    outs = [m for m in ordered if m.direction == "out"]

    first_in = ins[0].ts_hi if ins else None
    first_out = outs[0].ts_hi if outs else None

    you_replied = bool(first_in and any(o.ts_hi >= first_in for o in outs))
    they_replied = bool(first_out and any(i.ts_hi >= first_out for i in ins))
    # A thread the user opened — no inbound before their first message.
    you_started = bool(first_out and (first_in is None or first_out < first_in))

    your_latency = their_latency = None
    if first_in:
        after = [o.ts_hi for o in outs if o.ts_hi >= first_in]
        if after:
            your_latency = _hours(min(after) - first_in)
    if first_out:
        after = [i.ts_hi for i in ins if i.ts_hi >= first_out]
        if after:
            their_latency = _hours(min(after) - first_out)

    return {
        "in_count": len(ins),
        "out_count": len(outs),
        "you_replied": you_replied,
        "they_replied": they_replied,
        "you_started": you_started,
        "your_latency_h": your_latency,
        "their_latency_h": their_latency,
        "first_seen": ordered[0].ts_hi if ordered else None,
        "last_seen": ordered[-1].ts_hi if ordered else None,
        "subjects": [m.subject or "" for m in ins],
    }


def importance_score(cp: models.Counterparty, *, two_way_recently: bool) -> int:
    """0-100. Weights are explicit so the ranking can be argued with.

    Deliberately dominated by "do you answer them" rather than "how much do they
    send" — the first is a judgement the user already made, the second is
    something a mailing list can manufacture.
    """
    if cp.muted:
        return 0
    if cp.pinned:
        return 100

    score = 0.0
    # Revealed preference: you answer them.
    score += 30.0 * (int(cp.your_reply_rate or 0) / 100.0)
    # A sustained relationship, not one blast. Log so 40 threads isn't 40x 1.
    score += 20.0 * min(1.0, math.log1p(int(cp.thread_count or 0)) / math.log1p(40))
    # You answer them FAST — the clearest signal of priority there is.
    if cp.your_median_reply_h is not None:
        score += 15.0 * max(0.0, 1.0 - (float(cp.your_median_reply_h) / 72.0))
    # Still live.
    if two_way_recently:
        score += 10.0
    # Probably a human.
    if looks_like_a_person(cp.display_name or "", cp.email or ""):
        score += 5.0
    # Bulk senders are not people you can owe a reply to.
    if is_bulk_sender(cp.email or ""):
        score -= 25.0
    # An open deal or a known customer is a strong external signal — but only
    # ever a bonus, so the app ranks sensibly with no CRM connected at all.
    if (cp.crm_status or "") == "ok" and (cp.crm_stage or ""):
        score += 20.0

    return max(0, min(100, int(round(score))))


def infer_relationship(cp: models.Counterparty, *, vendor_hint: bool) -> str:
    """Deterministic classification. Returns `unknown` rather than guessing.

    User and CRM classifications are never overwritten — inference only fills in
    what nobody has stated.
    """
    if (cp.relationship_source or "inferred") in ("user", "crm"):
        return cp.relationship or UNKNOWN
    if is_bulk_sender(cp.email or ""):
        return BULK
    if cp.is_internal:
        return INTERNAL
    if (cp.crm_status or "") == "ok" and (cp.crm_stage or ""):
        stage = (cp.crm_stage or "").lower()
        return CUSTOMER if stage in ("customer", "closedwon", "closed won") else PROSPECT
    if vendor_hint:
        return VENDOR
    threads = int(cp.thread_count or 0)
    if threads >= 3 and int(cp.their_reply_rate or 0) > 60 and int(cp.your_reply_rate or 0) > 60:
        return CUSTOMER
    if int(cp.their_reply_rate or 0) > 50 and threads >= 1:
        return PROSPECT
    return UNKNOWN


def recompute(db: Session, user_id: str, *, limit_threads: int = 4000) -> int:
    """Rebuild every counterparty for this user from the ledger.

    Pure SQL + Python; safe to run on a schedule or on demand. Returns how many
    counterparties were written.
    """
    rows: List[models.ThreadMessage] = (
        db.query(models.ThreadMessage)
        .filter(models.ThreadMessage.user_id == user_id)
        .order_by(models.ThreadMessage.ts_hi.desc())
        .limit(limit_threads * 4)
        .all()
    )
    if not rows:
        return 0

    by_thread: Dict[str, List[models.ThreadMessage]] = {}
    for m in rows:
        by_thread.setdefault(m.thread_id, []).append(m)

    sync = (
        db.query(models.ThreadSyncState)
        .filter(models.ThreadSyncState.user_id == user_id)
        .first()
    )
    self_domain = ((sync.self_domain if sync else "") or "").lower()

    agg: Dict[str, Dict[str, object]] = {}
    for thread_id, msgs in by_thread.items():
        email, name = _thread_owner(msgs)
        if not email:
            continue  # nothing hydrated on this thread yet — it'll resolve later
        st = _thread_stats(msgs)
        slot = agg.setdefault(
            email,
            {
                "name": name, "threads": 0, "in": 0, "out": 0,
                "you_replied": 0, "they_replied": 0, "you_started": 0,
                "your_lat": [], "their_lat": [],
                "first": None, "last": None, "vendor_hint": False,
            },
        )
        slot["threads"] = int(slot["threads"]) + 1
        slot["in"] = int(slot["in"]) + int(st["in_count"])
        slot["out"] = int(slot["out"]) + int(st["out_count"])
        slot["you_replied"] = int(slot["you_replied"]) + (1 if st["you_replied"] else 0)
        slot["you_started"] = int(slot["you_started"]) + (1 if st["you_started"] else 0)
        if st["you_started"]:
            slot["they_replied"] = int(slot["they_replied"]) + (1 if st["they_replied"] else 0)
        if st["your_latency_h"] is not None:
            slot["your_lat"].append(st["your_latency_h"])  # type: ignore[union-attr]
        if st["their_latency_h"] is not None:
            slot["their_lat"].append(st["their_latency_h"])  # type: ignore[union-attr]
        if name and not slot["name"]:
            slot["name"] = name
        for key in ("first", "last"):
            val = st["first_seen"] if key == "first" else st["last_seen"]
            cur = slot[key]
            if val and (cur is None or (val < cur if key == "first" else val > cur)):
                slot[key] = val
        if any(h in (s or "").lower() for s in st["subjects"] for h in _VENDOR_HINTS):  # type: ignore[union-attr]
            slot["vendor_hint"] = True

    now = utcnow()
    written = 0
    for email, slot in agg.items():
        cp = (
            db.query(models.Counterparty)
            .filter(
                models.Counterparty.user_id == user_id,
                models.Counterparty.email == email,
            )
            .first()
        )
        if cp is None:
            cp = models.Counterparty(user_id=user_id, email=email)
            db.add(cp)

        cp.domain = email.split("@")[-1]
        if slot["name"]:
            cp.display_name = str(slot["name"])[:200]
        cp.is_internal = bool(self_domain and cp.domain == self_domain)

        threads = int(slot["threads"])
        started = int(slot["you_started"])
        cp.thread_count = threads
        cp.msg_in_count = int(slot["in"])
        cp.msg_out_count = int(slot["out"])
        cp.threads_you_replied = int(slot["you_replied"])
        cp.your_reply_rate = int(round(100 * int(slot["you_replied"]) / threads)) if threads else 0
        cp.their_reply_rate = int(round(100 * int(slot["they_replied"]) / started)) if started else 0

        your_lat: List[float] = slot["your_lat"]  # type: ignore[assignment]
        their_lat: List[float] = slot["their_lat"]  # type: ignore[assignment]
        cp.your_median_reply_h = int(round(statistics.median(your_lat))) if your_lat else None
        cp.their_median_reply_h = int(round(statistics.median(their_lat))) if their_lat else None

        cp.first_seen_at = slot["first"]  # type: ignore[assignment]
        cp.last_seen_at = slot["last"]  # type: ignore[assignment]

        two_way = bool(
            cp.last_seen_at
            and cp.last_seen_at >= now - timedelta(days=30)
            and int(slot["you_replied"]) > 0
        )
        cp.relationship = infer_relationship(cp, vendor_hint=bool(slot["vendor_hint"]))
        cp.importance = importance_score(cp, two_way_recently=two_way)
        written += 1

    db.commit()
    return written


def triage_rules_for(db: Session, user_id: str, *, limit: int = 8) -> List[Dict[str, str]]:
    """The people worth surfacing mail from, as synthetic triage rules.

    Drop-in replacement for the scan's old top-5-vip_senders block. Muted and
    bulk senders are excluded outright, and a pinned counterparty always makes
    the cut because that's an explicit instruction from the user.
    """
    rows = (
        db.query(models.Counterparty)
        .filter(
            models.Counterparty.user_id == user_id,
            models.Counterparty.muted.is_(False),
            models.Counterparty.importance >= INTERESTING,
        )
        .order_by(models.Counterparty.importance.desc())
        .limit(limit)
        .all()
    )
    out: List[Dict[str, str]] = []
    for cp in rows:
        if is_bulk_sender(cp.email or ""):
            continue
        who = cp.display_name or cp.email
        out.append(
            {
                "name": f"{who} (you usually reply)",
                "kind": "vip_sender",
                "value": cp.email,
                "tier": "needs_reply",
            }
        )
    return out


def get(db: Session, user_id: str, email: str) -> Optional[models.Counterparty]:
    return (
        db.query(models.Counterparty)
        .filter(
            models.Counterparty.user_id == user_id,
            models.Counterparty.email == (email or "").strip().lower(),
        )
        .first()
    )
