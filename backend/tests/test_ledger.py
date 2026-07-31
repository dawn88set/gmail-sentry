"""
Tests for the thread ledger (backend/services/ledger.py).

Network-free: a FakeGmail stands in for the broker, so we can assert the things
that actually matter and can't be checked by eye —

  * a message is sent to the LLM **once, ever** (the ~5,760-calls/day bug),
  * the deliberate window overlap and concurrent sweeps don't duplicate rows,
  * a watermark never advances past a window that failed,
  * ball position is derived correctly, including the tie rule,
  * a reply sent from the user's phone is detected,
  * query windows are built in UTC (a naive .timestamp() would shift them by the
    host's offset — invisible in UTC, wrong everywhere else).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import ledger
from backend.shared.adapters import IntegrationError


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        bind=engine,
        tables=[models.ThreadMessage.__table__, models.ThreadSyncState.__table__],
    )
    return sessionmaker(bind=engine)()


class FakeGmail:
    """A stand-in broker. Holds messages with real dates and answers the
    `after:`/`before:` window queries the ledger builds, so the sweep is
    exercised end to end rather than mocked away."""

    def __init__(self, messages=None):
        # each: {"id","threadId","box","date","sender","subject"}
        self.messages = list(messages or [])
        self.calls = []
        self.fail_on = set()  # box strings that should raise

    # -- helpers -------------------------------------------------------------
    def add(self, mid, thread, box, date, sender="dana@northwind.co", subject="Hi"):
        self.messages.append(
            {"id": mid, "threadId": thread, "box": box, "date": date,
             "sender": sender, "subject": subject}
        )

    @staticmethod
    def _parse(query):
        box = "in:sent" if "in:sent" in query else "in:inbox"
        lo = hi = None
        for tok in query.split():
            if tok.startswith("after:"):
                lo = datetime.fromtimestamp(int(tok[6:]), tz=timezone.utc).replace(tzinfo=None)
            elif tok.startswith("before:"):
                hi = datetime.fromtimestamp(int(tok[7:]), tz=timezone.utc).replace(tzinfo=None)
        return box, lo, hi

    # -- broker surface used by the ledger -----------------------------------
    def list_page(self, db, user_id, query, max_results=100, page_token=""):
        self.calls.append(query)
        box, lo, hi = self._parse(query)
        if box in self.fail_on:
            raise IntegrationError("gmail", f"boom on {box}")
        hits = [
            {"id": m["id"], "threadId": m["threadId"]}
            for m in self.messages
            if m["box"] == box and (lo is None or m["date"] > lo) and (hi is None or m["date"] <= hi)
        ]
        return {"messages": hits, "nextPageToken": ""}

    def search(self, db, user_id, query, max_results=25):
        box, _, _ = self._parse(query)
        hits = [{"id": m["id"], "threadId": m["threadId"]} for m in self.messages if m["box"] == box]
        return hits[:max_results]

    def get_meta(self, db, user_id, message_id):
        for m in self.messages:
            if m["id"] == message_id:
                return {
                    "id": m["id"], "thread_id": m["threadId"], "snippet": "snip",
                    "label_ids": [], "sender": m["sender"], "subject": m["subject"],
                    "rfc822_msgid": f"<{m['id']}@mail>",
                }
        return {"id": message_id, "thread_id": "", "snippet": "", "label_ids": [],
                "sender": "", "subject": "", "rfc822_msgid": ""}


@pytest.fixture
def gmail(monkeypatch):
    fake = FakeGmail()
    monkeypatch.setattr(ledger, "gmail_adapter", fake)
    return fake


# ── query construction ──────────────────────────────────────────────────────

def test_window_query_is_utc_not_local():
    """A naive datetime's .timestamp() is interpreted as LOCAL time. If the
    ledger ever regressed to that, every window would silently shift by the
    host's UTC offset — correct in UTC, wrong in every other timezone."""
    lo = datetime(2026, 7, 1, 0, 0, 0)
    hi = datetime(2026, 7, 1, 6, 0, 0)
    q = ledger.window_query("in:inbox", lo, hi)
    assert f"after:{int(lo.replace(tzinfo=timezone.utc).timestamp())}" in q
    assert f"before:{int(hi.replace(tzinfo=timezone.utc).timestamp())}" in q
    # Pinned: 2026-07-01T00:00:00Z. A naive .timestamp() on a non-UTC host
    # yields a different number, so this line is the actual regression guard.
    assert "after:1782864000" in q
    assert "before:1782885600" in q


def test_window_query_relative_fallback(monkeypatch):
    """If the broker turns out not to honor epoch after:/before:, only the query
    builder changes — the rest of the design is unaffected."""
    monkeypatch.setenv("SENTRY_LEDGER_EPOCH_QUERIES", "0")
    now = datetime(2026, 7, 10, 12, 0, 0)
    q = ledger.window_query("in:sent", now - timedelta(hours=12), now - timedelta(hours=6), now=now)
    assert q.startswith("in:sent ")
    assert "newer_than:13h" in q and "older_than:6h" in q


def test_stub_ids_accepts_both_casings():
    assert ledger._stub_ids({"id": "m1", "threadId": "t1"}) == ("m1", "t1")
    assert ledger._stub_ids({"id": "m1", "thread_id": "t1"}) == ("m1", "t1")


# ── the sweep ───────────────────────────────────────────────────────────────

def test_sync_indexes_inbound_and_outbound(gmail):
    db = _session()
    now = ledger.utcnow()
    gmail.add("m1", "t1", "in:inbox", now - timedelta(minutes=5))
    gmail.add("m2", "t1", "in:sent", now - timedelta(minutes=2))

    stats = ledger.sync_ledger(db, "u1")

    rows = db.query(models.ThreadMessage).all()
    assert {r.gmail_message_id for r in rows} == {"m1", "m2"}
    assert {r.direction for r in rows} == {"in", "out"}
    assert stats["in_new"] == 1 and stats["out_new"] == 1


def test_resweep_does_not_duplicate(gmail):
    """The forward sweep deliberately overlaps the previous window by 10 minutes,
    so the same message is offered again on the very next run."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("m1", "t1", "in:inbox", now - timedelta(minutes=1))

    ledger.sync_ledger(db, "u1")
    ledger.sync_ledger(db, "u1")
    ledger.sync_ledger(db, "u1")

    assert db.query(models.ThreadMessage).count() == 1


def test_concurrent_sweeps_do_not_duplicate(gmail):
    """Two overlapping scans both racing the same window must not double-insert;
    the unique index plus a savepoint is what makes that safe."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("m1", "t1", "in:inbox", now - timedelta(minutes=1))
    lo, hi = now - timedelta(hours=1), now

    assert ledger.sweep_window(db, "u1", "in:inbox", "in", lo, hi) == 1
    assert ledger.sweep_window(db, "u1", "in:inbox", "in", lo, hi) == 0
    assert db.query(models.ThreadMessage).count() == 1


def test_watermark_does_not_advance_past_a_failed_window(gmail):
    """A window that raises must leave the watermark where it was — advancing it
    would leave a hole in the ledger that nothing ever revisits."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("m1", "t1", "in:inbox", now - timedelta(minutes=1))
    gmail.fail_on = {"in:sent"}

    with pytest.raises(IntegrationError):
        ledger.sync_ledger(db, "u1")

    st = ledger.get_sync_state(db, "u1")
    assert st.sent_watermark is None, "sent watermark advanced despite a failure"


def test_users_are_isolated(gmail):
    db = _session()
    now = ledger.utcnow()
    gmail.add("m1", "t1", "in:inbox", now - timedelta(minutes=1))

    ledger.sync_ledger(db, "u1")
    ledger.sync_ledger(db, "u2")

    for uid in ("u1", "u2"):
        rows = db.query(models.ThreadMessage).filter(models.ThreadMessage.user_id == uid).all()
        assert [r.gmail_message_id for r in rows] == ["m1"]
    # Same Gmail message, two users, no unique-index collision between them.
    assert db.query(models.ThreadMessage).count() == 2


# ── the cost fix ────────────────────────────────────────────────────────────

def test_a_message_is_only_ever_triaged_once(gmail):
    """The bug this whole module exists to kill: an `fyi` message wrote no row,
    so every 5-minute scan re-fetched and re-classified it for two days."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("m1", "t1", "in:inbox", now - timedelta(minutes=1))

    ledger.sync_ledger(db, "u1")
    first = ledger.untriaged_inbound(db, "u1", limit=20)
    assert len(first) == 1

    # Judge it the way the scan does — even though `fyi` produces no alert.
    ledger.mark_triaged(first[0], "fyi", "ai")
    db.commit()

    ledger.sync_ledger(db, "u1")
    assert ledger.untriaged_inbound(db, "u1", limit=20) == []


def test_quiet_inbox_offers_no_work(gmail):
    db = _session()
    ledger.sync_ledger(db, "u1")
    assert ledger.untriaged_inbound(db, "u1", limit=20) == []


# ── thread state ────────────────────────────────────────────────────────────

def test_ball_position(gmail):
    db = _session()
    now = ledger.utcnow()
    # Gmail ids are increasing hex; these are ordered to match the dates, so
    # threads whose messages share a window still resolve correctly.
    # t1: they wrote last → you owe them.
    gmail.add("18f0a1", "t1", "in:sent", now - timedelta(hours=3))
    gmail.add("18f0a5", "t1", "in:inbox", now - timedelta(hours=1))
    # t2: you wrote last → waiting on them.
    gmail.add("18f0a0", "t2", "in:inbox", now - timedelta(hours=4))
    gmail.add("18f0a3", "t2", "in:sent", now - timedelta(hours=2))
    # t3: inbound only, never answered.
    gmail.add("18f09f", "t3", "in:inbox", now - timedelta(hours=5))
    # t4: cold outreach — you wrote, silence. Invisible before the ledger.
    gmail.add("18f09e", "t4", "in:sent", now - timedelta(hours=6))

    ledger.sync_ledger(db, "u1")
    ball = ledger.thread_ball(db, "u1")

    assert ball["t1"]["ball"] == "you"
    assert ball["t2"]["ball"] == "them"
    assert ball["t3"]["ball"] == "you"
    assert ball["t4"]["ball"] == "them"


def test_same_window_tie_goes_to_them(gmail):
    """Inbound and outbound in one window carry identical ts_hi. Ties resolve to
    'them' — replying inside a sweep interval is far likelier, and a missed
    follow-up is much cheaper than nudging someone you already answered."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("x1", "t1", "in:inbox", now - timedelta(minutes=2))
    gmail.add("x2", "t1", "in:sent", now - timedelta(minutes=1))

    ledger.sync_ledger(db, "u1")
    ball = ledger.thread_ball(db, "u1")

    assert ball["t1"]["last_in"] == ball["t1"]["last_out"], "expected a same-window tie"
    assert ball["t1"]["ball"] == "them"


def test_reply_sent_from_the_phone_is_detected(gmail):
    """The behaviour that makes the app trustworthy: today a reply sent from the
    Gmail mobile app leaves a stale alert nagging forever."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("in1", "t1", "in:inbox", now - timedelta(hours=2))

    ledger.sync_ledger(db, "u1")
    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "you"

    # User replies from their phone — the app never sees the send directly.
    gmail.add("out1", "t1", "in:sent", ledger.utcnow() - timedelta(seconds=1))
    ledger.sync_ledger(db, "u1")

    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "them"


def test_record_sent_message_flips_the_ball_immediately(gmail):
    """An in-app send shouldn't wait up to a sweep to be reflected."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("in1", "t1", "in:inbox", now - timedelta(hours=2))
    ledger.sync_ledger(db, "u1")
    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "you"

    ledger.record_sent_message(
        db, "u1", gmail_message_id="sent1", thread_id="t1",
        to_email="Dana Levi <dana@northwind.co>", subject="Re: Q3",
    )

    row = db.query(models.ThreadMessage).filter_by(gmail_message_id="sent1").one()
    assert row.direction == "out" and row.ts_exact is True
    assert row.counterparty_email == "dana@northwind.co"
    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "them"


def test_record_sent_message_is_idempotent_with_the_sweep(gmail):
    """The next in:sent sweep will offer the same message; it must be a no-op,
    not a duplicate or a crash."""
    db = _session()
    ledger.record_sent_message(db, "u1", gmail_message_id="s1", thread_id="t1")
    gmail.add("s1", "t1", "in:sent", ledger.utcnow() - timedelta(seconds=1))

    ledger.sync_ledger(db, "u1")

    assert db.query(models.ThreadMessage).filter_by(gmail_message_id="s1").count() == 1


# ── hydration ───────────────────────────────────────────────────────────────

def test_hydration_is_budgeted_and_names_threads_first(gmail):
    """Identity is the metered part, so each get_message call should buy the most
    it can: one per unnamed thread beats three in the same conversation."""
    db = _session()
    now = ledger.utcnow()
    for i in range(3):
        gmail.add(f"t1m{i}", "t1", "in:inbox", now - timedelta(minutes=10 + i))
    gmail.add("t2m0", "t2", "in:inbox", now - timedelta(minutes=20))
    gmail.add("t3m0", "t3", "in:inbox", now - timedelta(minutes=30))

    ledger.sync_ledger(db, "u1", hydrate_budget=3)

    named = {
        r.thread_id
        for r in db.query(models.ThreadMessage).filter(models.ThreadMessage.hydrated.is_(True)).all()
    }
    assert named == {"t1", "t2", "t3"}, "budget should have covered every thread once"


def test_outbound_is_never_hydrated(gmail):
    """We already know who sent it — spending a metered call there is waste."""
    db = _session()
    gmail.add("s1", "t1", "in:sent", ledger.utcnow() - timedelta(minutes=1))

    ledger.sync_ledger(db, "u1", hydrate_budget=10)

    row = db.query(models.ThreadMessage).filter_by(gmail_message_id="s1").one()
    assert row.hydrated is False


# ── backfill ────────────────────────────────────────────────────────────────

def test_backfill_walks_backward_and_completes(gmail):
    db = _session()
    now = ledger.utcnow()
    gmail.add("old1", "t9", "in:inbox", now - timedelta(days=5))
    gmail.add("old2", "t9", "in:sent", now - timedelta(days=20))

    st = ledger.get_sync_state(db, "u1")
    st.horizon_days = 30
    db.commit()

    for _ in range(30):  # each run covers 2 days of history
        ledger.sync_ledger(db, "u1")
        if ledger.get_sync_state(db, "u1").backfill_done:
            break

    st = ledger.get_sync_state(db, "u1")
    assert st.backfill_done is True
    assert st.backfill_done_at is not None, "needed by the nudge backfill guard"
    ids = {r.gmail_message_id for r in db.query(models.ThreadMessage).all()}
    assert {"old1", "old2"} <= ids


# ── time resolution ─────────────────────────────────────────────────────────

def test_reobserving_a_message_narrows_its_window(gmail):
    """A message first seen in a wide window carries a vague timestamp. A later,
    tighter window must be allowed to sharpen it — otherwise the first
    observation is permanent, every pre-existing thread stays stuck at one coarse
    ts_hi, and ball position never recovers from the initial import."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("18f0aa", "t1", "in:inbox", now - timedelta(hours=3))

    wide_lo, wide_hi = now - timedelta(hours=12), now
    ledger.sweep_window(db, "u1", "in:inbox", "in", wide_lo, wide_hi)
    row = db.query(models.ThreadMessage).one()
    assert (row.ts_hi - row.ts_lo) == timedelta(hours=12)

    tight_lo, tight_hi = now - timedelta(hours=4), now - timedelta(hours=2)
    ledger.sweep_window(db, "u1", "in:inbox", "in", tight_lo, tight_hi)

    row = db.query(models.ThreadMessage).one()
    assert row.ts_hi == tight_hi and row.ts_lo == tight_lo
    assert db.query(models.ThreadMessage).count() == 1


def test_reobserving_never_widens_a_window(gmail):
    db = _session()
    now = ledger.utcnow()
    gmail.add("18f0ab", "t1", "in:inbox", now - timedelta(hours=3))

    tight = (now - timedelta(hours=4), now - timedelta(hours=2))
    ledger.sweep_window(db, "u1", "in:inbox", "in", *tight)
    ledger.sweep_window(db, "u1", "in:inbox", "in", now - timedelta(hours=12), now)

    row = db.query(models.ThreadMessage).one()
    assert (row.ts_lo, row.ts_hi) == tight


def test_an_exact_send_timestamp_is_never_overwritten(gmail):
    """record_sent_message knows the actual instant. A later sweep offering the
    same message in a 6-hour bucket must not blur it."""
    db = _session()
    ledger.record_sent_message(db, "u1", gmail_message_id="18f0ac", thread_id="t1")
    exact = db.query(models.ThreadMessage).one().ts_hi

    gmail.add("18f0ac", "t1", "in:sent", ledger.utcnow() - timedelta(seconds=1))
    ledger.sync_ledger(db, "u1")

    row = db.query(models.ThreadMessage).one()
    assert row.ts_exact is True and row.ts_hi == exact


def test_ball_uses_message_id_to_break_a_same_window_tie(gmail):
    """Both messages land in one window, so ts_hi is identical and only the
    Gmail id can order them. The higher id is the later message."""
    db = _session()
    now = ledger.utcnow()
    # You wrote (lower id), then they replied (higher id) — you are owed nothing.
    gmail.add("18f100", "t1", "in:sent", now - timedelta(minutes=4))
    gmail.add("18f200", "t1", "in:inbox", now - timedelta(minutes=3))
    # Mirror image: they wrote, then you answered.
    gmail.add("18f300", "t2", "in:inbox", now - timedelta(minutes=4))
    gmail.add("18f400", "t2", "in:sent", now - timedelta(minutes=3))

    ledger.sync_ledger(db, "u1")
    ball = ledger.thread_ball(db, "u1")

    assert ball["t1"]["last_in"] == ball["t1"]["last_out"], "expected a same-window tie"
    assert ball["t1"]["ball"] == "you", "they spoke last — you owe a reply"
    assert ball["t2"]["ball"] == "them", "you spoke last — waiting on them"


def test_unparseable_ids_fall_back_to_the_conservative_rule(gmail):
    """A non-hex id must not crash the tiebreak; it degrades to 'outbound wins',
    which is the cheap-failure direction."""
    db = _session()
    now = ledger.utcnow()
    gmail.add("not-hex-!", "t1", "in:inbox", now - timedelta(minutes=3))
    gmail.add("also-bad-?", "t1", "in:sent", now - timedelta(minutes=3))

    ledger.sync_ledger(db, "u1")
    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "them"
