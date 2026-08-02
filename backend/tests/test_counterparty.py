"""
Counterparty inference (backend/services/counterparty.py).

The point of these tests is the ranking's *judgement*, not its plumbing. The
thing being replaced — a top-5 list ordered by message volume — would rank a
daily newsletter above a client who writes once a month, so the tests that
matter are the ones that pin the ordering to revealed preference: does the user
reply, how fast, over how many threads.

Network-free and LLM-free by construction: everything here is SQL over the
ledger.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import counterparty as cp
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


_SEQ = [0]


def msg(db, user_id, thread, direction, *, ago_h, sender="", subject=""):
    """Insert a ledger row. Ids increase so the intra-window tiebreak is sane."""
    _SEQ[0] += 1
    ts = utcnow() - timedelta(hours=ago_h)
    db.add(
        models.ThreadMessage(
            user_id=user_id,
            gmail_message_id=format(0x18F000 + _SEQ[0], "x"),
            thread_id=thread,
            direction=direction,
            ts_lo=ts,
            ts_hi=ts,
            hydrated=bool(sender),
            sender=sender,
            counterparty_email=(sender.split("<")[-1].strip(">").strip().lower() if "<" in sender
                                else sender.lower()) or None,
            subject=subject,
        )
    )
    db.commit()


def conversation(db, user, email, name, *, threads, you_reply, reply_after_h=2, ago_h=48):
    """`threads` exchanges with one person, optionally answered by the user."""
    for i in range(threads):
        t = f"{email}-{i}"
        msg(db, user, t, "in", ago_h=ago_h + i, sender=f"{name} <{email}>", subject=f"Note {i}")
        if you_reply:
            msg(db, user, t, "out", ago_h=ago_h + i - (reply_after_h / 1.0))


# ── the ranking ─────────────────────────────────────────────────────────────

def test_a_client_you_answer_outranks_a_newsletter_that_floods_you():
    """The whole reason this replaced `vip_senders`. Volume is not importance."""
    db = _session()
    # A newsletter: 30 messages, never answered.
    for i in range(30):
        msg(db, "u1", f"news-{i}", "in", ago_h=i + 1,
            sender="Daily Digest <newsletter@bigco.com>", subject="Today's roundup")
    # A client: 4 threads, answered every time, within a couple of hours.
    conversation(db, "u1", "dana@northwind.co", "Dana Levi", threads=4, you_reply=True)

    cp.recompute(db, "u1")

    news = cp.get(db, "u1", "newsletter@bigco.com")
    dana = cp.get(db, "u1", "dana@northwind.co")
    assert dana.importance > news.importance, (
        f"client {dana.importance} should outrank newsletter {news.importance}"
    )
    assert news.relationship == cp.BULK


def test_replying_is_what_makes_someone_important():
    """Identical volume; the only difference is whether the user engages."""
    db = _session()
    conversation(db, "u1", "answered@corp.com", "Ann Swered", threads=4, you_reply=True)
    conversation(db, "u1", "ignored@corp.com", "Ig Nored", threads=4, you_reply=False)

    cp.recompute(db, "u1")

    a = cp.get(db, "u1", "answered@corp.com")
    i = cp.get(db, "u1", "ignored@corp.com")
    assert a.your_reply_rate == 100 and i.your_reply_rate == 0
    assert a.importance > i.importance


def test_answering_fast_counts_for_more_than_answering_late():
    db = _session()
    conversation(db, "u1", "fast@corp.com", "Fast Person", threads=3, you_reply=True,
                 reply_after_h=1)
    conversation(db, "u1", "slow@corp.com", "Slow Person", threads=3, you_reply=True,
                 reply_after_h=60)

    cp.recompute(db, "u1")

    fast = cp.get(db, "u1", "fast@corp.com")
    slow = cp.get(db, "u1", "slow@corp.com")
    assert fast.your_median_reply_h < slow.your_median_reply_h
    assert fast.importance > slow.importance


def test_bulk_senders_are_recognised_by_local_part():
    for addr in ("no-reply@x.com", "noreply@x.com", "notifications@x.com",
                 "newsletter@x.com", "noreply-bounces@x.com"):
        assert cp.is_bulk_sender(addr), addr
    for addr in ("dana@northwind.co", "priya.shah@lumenlabs.io"):
        assert not cp.is_bulk_sender(addr), addr


def test_internal_colleagues_are_classified_from_the_users_own_domain():
    db = _session()
    db.add(models.ThreadSyncState(user_id="u1", self_address="me@acme.com", self_domain="acme.com"))
    db.commit()
    conversation(db, "u1", "colleague@acme.com", "Col League", threads=2, you_reply=True)
    conversation(db, "u1", "client@northwind.co", "Cli Ent", threads=2, you_reply=True)

    cp.recompute(db, "u1")

    assert cp.get(db, "u1", "colleague@acme.com").is_internal is True
    assert cp.get(db, "u1", "colleague@acme.com").relationship == cp.INTERNAL
    assert cp.get(db, "u1", "client@northwind.co").is_internal is False


def test_vendor_hint_from_invoice_subjects():
    db = _session()
    for i in range(2):
        t = f"bill-{i}"
        msg(db, "u1", t, "in", ago_h=10 + i,
            sender="Billing <accounts@meridiansupply.com>", subject=f"Invoice #482{i} due")
        msg(db, "u1", t, "out", ago_h=9 + i)

    cp.recompute(db, "u1")

    assert cp.get(db, "u1", "accounts@meridiansupply.com").relationship == cp.VENDOR


# ── reply rates ─────────────────────────────────────────────────────────────

def test_their_reply_rate_only_counts_threads_you_started():
    """Otherwise every thread they opened would inflate their responsiveness."""
    db = _session()
    # You reached out twice; they answered once. → 50%.
    msg(db, "u1", "t1", "out", ago_h=20)
    msg(db, "u1", "t1", "in", ago_h=18, sender="Mark Ruiz <mark@prospect.io>")
    msg(db, "u1", "t2", "out", ago_h=15)
    msg(db, "u1", "t2", "in", ago_h=14, sender="Mark Ruiz <mark@prospect.io>")
    msg(db, "u1", "t3", "out", ago_h=10)  # silence

    cp.recompute(db, "u1")
    mark = cp.get(db, "u1", "mark@prospect.io")
    # t3 has no inbound, so it can't be attributed to anyone — 2 known threads.
    assert mark.their_reply_rate == 100
    assert mark.thread_count == 2


def test_a_thread_you_started_and_abandoned_is_not_a_reply():
    """`you_replied` means outbound AFTER their inbound, not merely present."""
    db = _session()
    msg(db, "u1", "t1", "out", ago_h=30)  # you opened
    msg(db, "u1", "t1", "in", ago_h=20, sender="Zoe <zoe@corp.com>")  # they answered
    # ...and you never came back.

    cp.recompute(db, "u1")
    assert cp.get(db, "u1", "zoe@corp.com").your_reply_rate == 0


# ── overrides ───────────────────────────────────────────────────────────────

def test_pinned_and_muted_override_inference():
    db = _session()
    conversation(db, "u1", "vip@corp.com", "V I P", threads=1, you_reply=False)
    conversation(db, "u1", "loud@corp.com", "Loud One", threads=5, you_reply=True)
    cp.recompute(db, "u1")

    vip = cp.get(db, "u1", "vip@corp.com")
    loud = cp.get(db, "u1", "loud@corp.com")
    vip.pinned = True
    loud.muted = True
    db.commit()

    cp.recompute(db, "u1")
    assert cp.get(db, "u1", "vip@corp.com").importance == 100
    assert cp.get(db, "u1", "loud@corp.com").importance == 0


def test_a_user_stated_relationship_is_never_overwritten():
    db = _session()
    conversation(db, "u1", "dana@northwind.co", "Dana Levi", threads=3, you_reply=True)
    cp.recompute(db, "u1")

    row = cp.get(db, "u1", "dana@northwind.co")
    row.relationship = cp.CUSTOMER
    row.relationship_source = "user"
    db.commit()

    cp.recompute(db, "u1")
    row = cp.get(db, "u1", "dana@northwind.co")
    assert row.relationship == cp.CUSTOMER and row.relationship_source == "user"


# ── the triage handoff ──────────────────────────────────────────────────────

def test_triage_rules_exclude_muted_and_bulk():
    db = _session()
    conversation(db, "u1", "dana@northwind.co", "Dana Levi", threads=4, you_reply=True)
    conversation(db, "u1", "muted@corp.com", "Mu Ted", threads=4, you_reply=True)
    for i in range(20):
        msg(db, "u1", f"n{i}", "in", ago_h=i + 1, sender="News <newsletter@bigco.com>")
    cp.recompute(db, "u1")
    row = cp.get(db, "u1", "muted@corp.com")
    row.muted = True
    db.commit()
    cp.recompute(db, "u1")

    values = {r["value"] for r in cp.triage_rules_for(db, "u1")}
    assert "dana@northwind.co" in values
    assert "muted@corp.com" not in values
    assert "newsletter@bigco.com" not in values


def test_triage_rules_have_the_shape_the_scan_expects():
    db = _session()
    conversation(db, "u1", "dana@northwind.co", "Dana Levi", threads=4, you_reply=True)
    cp.recompute(db, "u1")

    rules = cp.triage_rules_for(db, "u1")
    assert rules, "a frequently-answered client should produce a rule"
    r = rules[0]
    assert set(r) == {"name", "kind", "value", "tier"}
    assert r["kind"] == "vip_sender" and r["tier"] == "needs_reply"


def test_users_are_isolated():
    db = _session()
    conversation(db, "u1", "dana@northwind.co", "Dana Levi", threads=2, you_reply=True)
    conversation(db, "u2", "other@corp.com", "Oth Er", threads=2, you_reply=True)

    cp.recompute(db, "u1")
    cp.recompute(db, "u2")

    assert cp.get(db, "u1", "other@corp.com") is None
    assert cp.get(db, "u2", "dana@northwind.co") is None


def test_recompute_is_idempotent():
    db = _session()
    conversation(db, "u1", "dana@northwind.co", "Dana Levi", threads=3, you_reply=True)

    cp.recompute(db, "u1")
    first = cp.get(db, "u1", "dana@northwind.co").importance
    cp.recompute(db, "u1")
    cp.recompute(db, "u1")

    assert db.query(models.Counterparty).count() == 1
    assert cp.get(db, "u1", "dana@northwind.co").importance == first


def test_empty_ledger_is_a_no_op():
    db = _session()
    assert cp.recompute(db, "u1") == 0
    assert cp.triage_rules_for(db, "u1") == []


# ── inbound-led relationships ───────────────────────────────────────────────
#
# `their_reply_rate` is measured over threads YOU started. When you never
# started one it's undefined, not zero — and reading it as zero left anyone who
# always writes first permanently `unknown`, which means no filing folder. That
# is the ordinary shape of an inbound-led business.

def test_someone_who_always_writes_first_can_still_be_a_client():
    person = models.Counterparty(
        email="dana@northwind.co", domain="northwind.co",
        thread_count=5, your_reply_rate=100, their_reply_rate=0,
    )
    assert cp.infer_relationship(
        person, vendor_hint=False, you_ever_started=False,
    ) == cp.CUSTOMER


def test_one_polite_reply_to_a_stranger_is_not_a_relationship():
    """A folder per stranger would be worse than no filing at all."""
    person = models.Counterparty(
        email="someone@elsewhere.com", domain="elsewhere.com",
        thread_count=1, your_reply_rate=100, their_reply_rate=0,
    )
    assert cp.infer_relationship(
        person, vendor_hint=False, you_ever_started=False,
    ) == cp.UNKNOWN


def test_mail_you_never_answer_stays_unknown_however_much_arrives():
    person = models.Counterparty(
        email="loud@vendor.com", domain="vendor.com",
        thread_count=40, your_reply_rate=0, their_reply_rate=0,
    )
    assert cp.infer_relationship(
        person, vendor_hint=False, you_ever_started=False,
    ) == cp.UNKNOWN


def test_the_two_way_rules_are_unchanged_when_you_did_start_threads():
    person = models.Counterparty(
        email="lead@acme.io", domain="acme.io",
        thread_count=2, your_reply_rate=50, their_reply_rate=80,
    )
    assert cp.infer_relationship(person, vendor_hint=False) == cp.PROSPECT


def test_an_inbound_led_client_gets_a_filing_folder():
    """The point of the fix: unclassified means unfiled."""
    person = models.Counterparty(
        email="dana@northwind.co", domain="northwind.co",
        thread_count=5, your_reply_rate=100, their_reply_rate=0,
    )
    person.relationship = cp.infer_relationship(
        person, vendor_hint=False, you_ever_started=False,
    )
    from backend.services import filing
    assert filing.folder_for_thread(person, "Q3 quote")[0] == "Clients/Northwind"
