"""
The thread ledger — Gmail Sentry's local reconstruction of the mailbox.

Everything the app wants to know that it previously couldn't — who owes whom a
reply, how long something has been sitting, whether the user already answered
from their phone — is a read over one missing primitive: an incrementally-synced
index of message events keyed by thread. This module builds it.

## The trick

The broker exposes no `get_thread` verb, and `gmail.get_message` returns no date.
But `gmail.search`/`list_messages` pass an arbitrary Gmail query string through
and hand back `{id, threadId}` stubs. So:

- **Thread topology is free.** `threadId` arrives on the stub; no metered
  `get_message` call is needed to know which conversation a message belongs to.
- **Time comes from the query, not the message.** We sweep in windows
  (`after:<epoch> before:<epoch>`) and stamp each row with the window's bounds.

Two searches per sweep — one over `in:inbox`, one over `in:sent` — therefore give
ball position, aging, and reply detection for **zero LLM calls and zero
`get_message` calls**.

## The ordering rule

A row's working clock is `ts_hi`, the latest the message could possibly be. That
is deliberately conservative: an aging clock built on `ts_hi` under-ages, so the
app never chases someone before they've actually gone quiet. Where an inbound and
an outbound land in the same window, **outbound wins** (ball → them): replying
inside one sweep interval is overwhelmingly the likelier ordering, and a
follow-up we fail to raise is far cheaper than nudging someone we already
answered.

## The discipline

Structure first (free), identity later (metered), judgement last (LLM, memoised
forever). `hydrate` fills sender/subject only for what will actually be shown,
and `triage_tier` on a row is a permanent receipt so no message is ever judged
by the model twice.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models
from backend.integrations import gmail_ops as gmail_adapter
from backend.shared.adapters import IntegrationNotConnected, IntegrationError

logger = logging.getLogger(__name__)

# How far back to re-sweep on each forward pass. The unique index makes
# re-indexing a no-op, so this is cheap insurance against a message landing at
# the exact boundary of the previous window.
OVERLAP = timedelta(minutes=10)

# Backfill walks backward in buckets. Bounded per run so a first sync can never
# stall the 5-minute scan: 8 × 6h = 2 days of history per run, so the default
# 45-day horizon completes in roughly two hours of normal scanning.
BACKFILL_BUCKET = timedelta(hours=6)
BACKFILL_BUCKETS_PER_RUN = 8

# Page size for a single list_messages call, and a hard ceiling per window per
# run so one enormous window can't run away with the whole scan.
PAGE = 100
MAX_PER_WINDOW = 500

# On the very first forward sweep there is no watermark. Keep this narrow — one
# backfill bucket — so the cold start can't stamp a whole day of mail with a
# single coarse ts_hi. Anything older is backfill's job, at the same resolution.
COLD_START_LOOKBACK = BACKFILL_BUCKET

_INBOX = "in:inbox"
_SENT = "in:sent"


# ── time helpers ────────────────────────────────────────────────────────────
# Every stored datetime is naive UTC (matching the rest of the models). Calling
# .timestamp() on a naive datetime makes Python interpret it as LOCAL time,
# which would silently shift every query window by the host's UTC offset — a
# bug that only shows up outside UTC. Always go through these.

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _epoch(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _epoch_queries_enabled() -> bool:
    """Whether the broker honors `after:`/`before:` with epoch seconds.

    Verified by scripts/verify_ledger_broker.py. Set
    SENTRY_LEDGER_EPOCH_QUERIES=0 to fall back to relative
    `newer_than:`/`older_than:` hour windows, which are coarser but sufficient —
    only this query builder changes, not the design.
    """
    return (os.getenv("SENTRY_LEDGER_EPOCH_QUERIES") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def window_query(box: str, lo: datetime, hi: datetime, *, now: Optional[datetime] = None) -> str:
    """The Gmail query for one (mailbox, time-window) pair."""
    if _epoch_queries_enabled():
        return f"{box} after:{_epoch(lo)} before:{_epoch(hi)}"
    # Relative fallback. Gmail reads `newer_than:Nh` as "within the last N hours",
    # so the window [lo, hi] becomes newer_than(now-lo) AND older_than(now-hi).
    ref = now or utcnow()
    lo_h = max(1, int((ref - lo).total_seconds() // 3600) + 1)
    hi_h = max(0, int((ref - hi).total_seconds() // 3600))
    q = f"{box} newer_than:{lo_h}h"
    if hi_h > 0:
        q += f" older_than:{hi_h}h"
    return q


def _stub_ids(stub: Dict[str, Any]) -> Tuple[str, str]:
    """(message_id, thread_id) from a search stub.

    The broker returns camelCase `threadId` on stubs but snake_case `thread_id`
    from get_message; accept either so a broker change can't silently drop
    thread topology.
    """
    mid = stub.get("id") or stub.get("message_id") or ""
    tid = stub.get("threadId") or stub.get("thread_id") or ""
    return str(mid), str(tid)


def _email_of(raw: str) -> str:
    """Bare address out of a From/To header."""
    raw = (raw or "").strip()
    if "<" in raw and ">" in raw:
        raw = raw[raw.index("<") + 1 : raw.index(">")]
    return raw.strip().strip('"').lower()


# ── sync state ──────────────────────────────────────────────────────────────

def get_sync_state(db: Session, user_id: str) -> models.ThreadSyncState:
    st = (
        db.query(models.ThreadSyncState)
        .filter(models.ThreadSyncState.user_id == user_id)
        .first()
    )
    if st is None:
        st = models.ThreadSyncState(user_id=user_id)
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


def _learn_self_address(db: Session, user_id: str, st: models.ThreadSyncState) -> None:
    """One metered call, once per user ever: who is 'me'.

    Needed to tell internal from external counterparties. Best-effort — a failure
    just means we retry on the next sweep.
    """
    if st.self_address:
        return
    try:
        stubs = gmail_adapter.search(db, user_id, _SENT, max_results=1)
        if not stubs:
            return
        mid, _ = _stub_ids(stubs[0])
        if not mid:
            return
        meta = gmail_adapter.get_meta(db, user_id, mid)
        addr = _email_of(meta.get("sender") or "")
        if addr and "@" in addr:
            st.self_address = addr
            st.self_domain = addr.split("@")[-1]
    except (IntegrationNotConnected, IntegrationError) as e:
        logger.debug("self-address probe deferred: %s", e)


# ── the sweep ───────────────────────────────────────────────────────────────

def _index_stub(
    db: Session,
    user_id: str,
    stub: Dict[str, Any],
    direction: str,
    lo: datetime,
    hi: datetime,
) -> bool:
    """Insert one ledger row. Returns True if it was new.

    The unique index is the dedupe: concurrent sweeps and the deliberate window
    overlap both land here, and a savepoint keeps a rejected duplicate from
    poisoning the surrounding transaction (same pattern as the alert insert).

    **Re-observing NARROWS the window.** A message first seen in a wide window
    (the cold start, or a coarse backfill bucket) carries a correspondingly vague
    timestamp. If a later, tighter window turns up the same message we keep the
    tighter bounds. Without this the first observation would be permanent —
    every pre-existing thread stuck at one coarse `ts_hi`, which collapses ball
    position into the tie rule and never recovers. Widening is ignored, and a
    row with `ts_exact` (a send this app performed, where we know the instant) is
    never touched.
    """
    mid, tid = _stub_ids(stub)
    if not mid:
        return False
    try:
        with db.begin_nested():
            db.add(
                models.ThreadMessage(
                    user_id=user_id,
                    gmail_message_id=mid,
                    # A thread of one still needs a thread key; fall back to the
                    # message id so grouping never sees an empty bucket.
                    thread_id=tid or mid,
                    direction=direction,
                    ts_lo=lo,
                    ts_hi=hi,
                )
            )
            db.flush()
        return True
    except IntegrityError:
        pass  # already indexed — the point of the unique index

    existing = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.gmail_message_id == mid,
        )
        .first()
    )
    if existing is not None and not existing.ts_exact:
        if (hi - lo) < (existing.ts_hi - existing.ts_lo):
            existing.ts_lo, existing.ts_hi = lo, hi
        if tid and existing.thread_id != tid:
            existing.thread_id = tid
    return False


def sweep_window(
    db: Session,
    user_id: str,
    box: str,
    direction: str,
    lo: datetime,
    hi: datetime,
) -> int:
    """Index one (mailbox, window). Returns how many rows were new.

    Uses list_page rather than search because gmail_ops.search drops
    nextPageToken, and a window that silently truncated would leave a permanent
    hole in the ledger.
    """
    q = window_query(box, lo, hi)
    page_token = ""
    seen = 0
    inserted = 0
    while seen < MAX_PER_WINDOW:
        page = gmail_adapter.list_page(db, user_id, q, max_results=PAGE, page_token=page_token)
        msgs = page.get("messages") or []
        for stub in msgs:
            if _index_stub(db, user_id, stub, direction, lo, hi):
                inserted += 1
            seen += 1
        page_token = page.get("nextPageToken") or ""
        if not page_token or not msgs:
            break
    if seen >= MAX_PER_WINDOW and page_token:
        # Never silently truncate: say so, so a too-wide window is visible.
        logger.warning(
            "ledger: window %s [%s..%s] hit the %d-message cap for user=%s; "
            "remaining messages will be picked up by the overlap on the next sweep",
            box, lo, hi, MAX_PER_WINDOW, user_id,
        )
    db.commit()
    return inserted


def _hydrate(db: Session, user_id: str, budget: int) -> int:
    """Fill sender/subject/snippet for the messages we'll actually show.

    Prioritised so each metered call buys the most: an unhydrated inbound message
    in a thread that has NO hydrated message yet names a whole conversation.
    Outbound rows are never hydrated — we already know who sent them.
    """
    if budget <= 0:
        return 0

    # Threads that already have identity — skip them until the cheap wins run out.
    named_threads = {
        r[0]
        for r in db.query(models.ThreadMessage.thread_id)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.hydrated.is_(True),
        )
        .distinct()
        .all()
    }

    pending: List[models.ThreadMessage] = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.direction == "in",
            models.ThreadMessage.hydrated.is_(False),
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .limit(budget * 8)
        .all()
    )

    # Order so each metered call buys the most: one message per still-unnamed
    # thread first (newest thread first), then everything else. `claimed` grows
    # as we go — without it, three messages in the same conversation would eat
    # the whole budget and leave two other threads anonymous.
    claimed = set(named_threads)
    first_of_thread: List[models.ThreadMessage] = []
    rest: List[models.ThreadMessage] = []
    for msg in pending:
        if msg.thread_id in claimed:
            rest.append(msg)
        else:
            claimed.add(msg.thread_id)
            first_of_thread.append(msg)
    ordered = first_of_thread + rest

    done = 0
    for msg in ordered:
        if done >= budget:
            break
        try:
            meta = gmail_adapter.get_meta(db, user_id, msg.gmail_message_id)
        except IntegrationNotConnected:
            raise
        except IntegrationError as e:
            logger.debug("hydrate skipped %s: %s", msg.gmail_message_id, e)
            continue
        msg.sender = meta.get("sender") or ""
        msg.counterparty_email = _email_of(msg.sender)
        msg.subject = meta.get("subject") or ""
        msg.snippet = meta.get("snippet") or ""
        msg.rfc822_msgid = meta.get("rfc822_msgid") or ""
        msg.label_ids = meta.get("label_ids") or []
        if meta.get("thread_id"):
            msg.thread_id = meta["thread_id"]
        msg.hydrated = True
        done += 1
    if done:
        db.commit()
    return done


def sync_ledger(db: Session, user_id: str, *, hydrate_budget: Optional[int] = None) -> Dict[str, int]:
    """Bring the ledger up to date. 2–4 broker calls in the steady state, 0 LLM.

    Raises IntegrationNotConnected (→ 409) so the caller can surface an honest
    connect prompt; every other broker failure is contained per-window so a
    transient error can't lose the watermark.
    """
    st = get_sync_state(db, user_id)
    now = utcnow()
    stats: Counter = Counter()

    _learn_self_address(db, user_id, st)

    # 1. Forward sweep. The watermark advances only after a window completes —
    #    advancing on failure would leave a hole nothing ever revisits.
    for direction, box, attr in (("in", _INBOX, "inbox_watermark"), ("out", _SENT, "sent_watermark")):
        prev = getattr(st, attr)
        lo = (prev or (now - COLD_START_LOOKBACK)) - OVERLAP
        if lo >= now:
            continue
        stats[f"{direction}_new"] += sweep_window(db, user_id, box, direction, lo, now)
        setattr(st, attr, now)

    # 2. Backfill, walking backward, bounded per run.
    if not st.backfill_done:
        cursor = st.backfill_cursor or now
        floor = now - timedelta(days=int(st.horizon_days or 45))
        for _ in range(BACKFILL_BUCKETS_PER_RUN):
            if cursor <= floor:
                break
            lo = max(cursor - BACKFILL_BUCKET, floor)
            stats["backfill_new"] += sweep_window(db, user_id, _INBOX, "in", lo, cursor)
            stats["backfill_new"] += sweep_window(db, user_id, _SENT, "out", lo, cursor)
            cursor = lo
        if cursor <= floor:
            st.backfill_done = True
            st.backfill_done_at = now
            st.backfill_cursor = None
        else:
            st.backfill_cursor = cursor

    # 3. Identity, metered.
    budget = hydrate_budget if hydrate_budget is not None else int(st.hydration_budget or 25)
    stats["hydrated"] = _hydrate(db, user_id, budget)

    st.last_sweep_at = now
    st.last_error = ""
    st.messages_indexed = int(st.messages_indexed or 0) + stats["in_new"] + stats["out_new"] + stats["backfill_new"]
    db.commit()
    return dict(stats)


# ── reads over the ledger ───────────────────────────────────────────────────

def untriaged_inbound(
    db: Session, user_id: str, *, limit: int, within: timedelta = timedelta(days=2)
) -> List[models.ThreadMessage]:
    """Inbound messages this app has never judged, newest first.

    This is what replaced re-querying Gmail every scan. `triaged_at IS NULL` is
    the whole cost fix: once a message has a verdict — including `fyi` — it is
    never sent to the model again.
    """
    return (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.direction == "in",
            models.ThreadMessage.triaged_at.is_(None),
            models.ThreadMessage.ts_hi >= utcnow() - within,
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .limit(limit)
        .all()
    )


def ensure_hydrated(db: Session, user_id: str, msg: models.ThreadMessage) -> models.ThreadMessage:
    """Fill identity for one message if the budgeted pass hasn't reached it yet.

    The scan needs sender/subject/snippet to classify, and it must not depend on
    whether the metered hydration pass happened to cover this row.
    """
    if msg.hydrated:
        return msg
    meta = gmail_adapter.get_meta(db, user_id, msg.gmail_message_id)
    msg.sender = meta.get("sender") or ""
    msg.counterparty_email = _email_of(msg.sender)
    msg.subject = meta.get("subject") or ""
    msg.snippet = meta.get("snippet") or ""
    msg.rfc822_msgid = meta.get("rfc822_msgid") or ""
    msg.label_ids = meta.get("label_ids") or []
    if meta.get("thread_id"):
        msg.thread_id = meta["thread_id"]
    msg.hydrated = True
    return msg


def mark_triaged(msg: models.ThreadMessage, tier: str, source: str) -> None:
    """Record the verdict. Call this for EVERY judged message — including `fyi`
    and muted senders — or the message comes back on the next scan."""
    msg.triage_tier = tier
    msg.triage_source = source
    msg.triaged_at = utcnow()


def _id_rank(gmail_message_id: str) -> int:
    """A within-window ordering hint from the Gmail message id.

    Gmail assigns message ids as increasing hex values, so `int(id, 16)` orders
    two messages that landed in the SAME query window — which `ts_hi` alone
    cannot, because the window is all the time resolution we have.

    This matters more than it sounds. In the steady state a window is 5 minutes
    wide and ties are rare, but the first sync and the backfill use much coarser
    buckets, and the last few hours is exactly where most threads are active.
    Without a tiebreak, every recently-active thread would fall back to the
    blanket "outbound wins" rule and a conversation where they answered you two
    hours ago would read as "waiting on them".

    The ordering is not a documented guarantee, so it is used ONLY to break a
    tie that would otherwise be decided arbitrarily — never to override real
    timestamps. An unparseable id returns -1 and we fall back to the
    conservative rule.
    """
    try:
        return int(gmail_message_id, 16)
    except (TypeError, ValueError):
        return -1


def thread_ball(db: Session, user_id: str) -> Dict[str, Dict[str, Any]]:
    """Per thread: who spoke last, and when. One query, no Gmail calls.

    Returns {thread_id: {last_in, last_out, ball}} where ball is "you" (they
    spoke last, so you owe them) or "them".

    Ordering is by (ts_hi, id_rank): the window first, then the message-id hint
    within it. When both are tied the ball goes to "them" — replying inside one
    window is the likelier reading, and a follow-up we fail to raise is much
    cheaper than nudging someone we already answered.
    """
    rows = (
        db.query(
            models.ThreadMessage.thread_id,
            models.ThreadMessage.direction,
            models.ThreadMessage.ts_hi,
            models.ThreadMessage.gmail_message_id,
        )
        .filter(models.ThreadMessage.user_id == user_id)
        .all()
    )

    latest: Dict[str, Dict[str, Any]] = {}
    for thread_id, direction, ts, mid in rows:
        slot = latest.setdefault(
            thread_id, {"last_in": None, "last_out": None, "_in": None, "_out": None}
        )
        key = (ts, _id_rank(mid))
        which = "_in" if direction == "in" else "_out"
        if slot[which] is None or key > slot[which]:
            slot[which] = key
            slot["last_in" if direction == "in" else "last_out"] = ts

    out: Dict[str, Dict[str, Any]] = {}
    for thread_id, slot in latest.items():
        k_in, k_out = slot["_in"], slot["_out"]
        if k_in and k_out:
            ball = "them" if k_out >= k_in else "you"
        elif k_out:
            ball = "them"
        else:
            ball = "you"
        out[thread_id] = {
            "last_in": slot["last_in"],
            "last_out": slot["last_out"],
            "ball": ball,
        }
    return out


def record_sent_message(
    db: Session,
    user_id: str,
    *,
    gmail_message_id: str,
    thread_id: str,
    to_email: str = "",
    subject: str = "",
    sent_at: Optional[datetime] = None,
) -> None:
    """Record a send this app just performed, with its exact timestamp.

    Two reasons this is worth doing eagerly rather than waiting for the next
    `in:sent` sweep: the thread flips to "waiting on them" immediately instead of
    up to a sweep later, and when the sweep does come around the unique index
    turns it into a no-op. Best-effort — a failure here must never fail a send
    that already succeeded.
    """
    if not gmail_message_id:
        return
    ts = sent_at or utcnow()
    try:
        with db.begin_nested():
            db.add(
                models.ThreadMessage(
                    user_id=user_id,
                    gmail_message_id=gmail_message_id,
                    thread_id=thread_id or gmail_message_id,
                    direction="out",
                    ts_lo=ts,
                    ts_hi=ts,
                    ts_exact=True,
                    hydrated=True,
                    counterparty_email=_email_of(to_email),
                    subject=subject or "",
                )
            )
            db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
    except Exception as e:  # noqa: BLE001
        logger.warning("ledger: could not record sent message %s: %s", gmail_message_id, e)
        db.rollback()
