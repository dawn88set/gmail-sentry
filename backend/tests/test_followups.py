"""
Open loops (backend/services/followups.py).

The behaviours worth pinning here are the ones that decide whether a user trusts
the app or learns to ignore it:

  * a reply sent from the phone closes the alert and flips the loop,
  * sending a reply OPENS "waiting on them" instead of ending the story,
  * aging is per-relationship, so a slow-by-nature contact isn't chased early,
  * alerts and follow-ups partition rather than double-count,
  * "not a follow-up" sticks.

Network-free and LLM-free: everything is derived from the ledger.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import counterparty as cp_service
from backend.services import followups as fu_service
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


_SEQ = [0]


def msg(db, user, thread, direction, *, ago_h, sender="", subject=""):
    _SEQ[0] += 1
    ts = utcnow() - timedelta(hours=ago_h)
    email = ""
    if sender:
        email = sender.split("<")[-1].strip(">").strip().lower() if "<" in sender else sender.lower()
    db.add(
        models.ThreadMessage(
            user_id=user,
            gmail_message_id=format(0x18F000 + _SEQ[0], "x"),
            thread_id=thread,
            direction=direction,
            ts_lo=ts,
            ts_hi=ts,
            hydrated=bool(sender),
            sender=sender,
            counterparty_email=email or None,
            subject=subject,
        )
    )
    db.commit()
    return ts


def a_counterparty(db, user, email, *, median_reply_h=None, importance=50, relationship="unknown"):
    c = models.Counterparty(
        user_id=user, email=email, domain=email.split("@")[-1],
        their_median_reply_h=median_reply_h, importance=importance,
        relationship=relationship,
    )
    db.add(c)
    db.commit()
    return c


# ── state derivation ────────────────────────────────────────────────────────

def test_they_wrote_last_means_you_owe_them():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=3, sender="Dana Levi <dana@northwind.co>", subject="Q3 quote")

    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).one()
    assert fu.state == fu_service.AWAITING_YOU
    assert fu.counterparty_email == "dana@northwind.co"
    assert fu.subject == "Q3 quote"


def test_you_wrote_last_means_waiting_on_them():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=5, sender="Dana Levi <dana@northwind.co>")
    msg(db, "u1", "t1", "out", ago_h=4)

    fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).one().state == fu_service.AWAITING_THEM


def test_cold_outreach_with_no_answer_is_tracked():
    """You emailed a prospect and heard nothing. Invisible before follow-ups —
    there was no alert, because no mail ever arrived."""
    db = _session()
    a_counterparty(db, "u1", "mark@prospect.io", median_reply_h=12)
    msg(db, "u1", "t1", "out", ago_h=24 * 9, sender="")

    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).one()
    assert fu.state == fu_service.GOING_COLD


def test_bulk_senders_never_become_loops():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=2, sender="News <newsletter@bigco.com>")

    fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).count() == 0


def test_muted_counterparties_never_become_loops():
    db = _session()
    c = a_counterparty(db, "u1", "loud@corp.com")
    c.muted = True
    db.commit()
    msg(db, "u1", "t1", "in", ago_h=2, sender="Loud <loud@corp.com>")

    fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).count() == 0


# ── the reply-from-phone case ───────────────────────────────────────────────

def test_a_reply_from_the_phone_closes_the_alert():
    """The behaviour that makes the app trustworthy. Before this, replying from
    the Gmail app left the alert nagging forever."""
    db = _session()
    now = utcnow()
    alert = models.Alert(
        user_id="u1", gmail_message_id="m1", thread_id="t1",
        sender="Dana Levi <dana@northwind.co>", subject="Q3 quote",
        tier="urgent", status="new", created_at=now - timedelta(hours=3),
    )
    db.add(alert)
    db.commit()
    msg(db, "u1", "t1", "in", ago_h=3, sender="Dana Levi <dana@northwind.co>")
    # ...answered from the phone, which the in:sent sweep picks up.
    msg(db, "u1", "t1", "out", ago_h=1)

    closed = fu_service.close_alerts_replied_elsewhere(db, "u1")

    assert closed == 1
    assert db.query(models.Alert).one().status == "done"


def test_an_older_outbound_does_not_close_a_newer_alert():
    """A long thread you replied to last week, then they wrote again today. That
    new message is genuinely unanswered."""
    db = _session()
    now = utcnow()
    msg(db, "u1", "t1", "out", ago_h=24 * 7)
    db.add(models.Alert(
        user_id="u1", gmail_message_id="m2", thread_id="t1",
        sender="Dana <dana@northwind.co>", subject="Re: Q3",
        tier="urgent", status="new", created_at=now - timedelta(hours=1),
    ))
    db.commit()
    msg(db, "u1", "t1", "in", ago_h=1, sender="Dana <dana@northwind.co>")

    assert fu_service.close_alerts_replied_elsewhere(db, "u1") == 0
    assert db.query(models.Alert).one().status == "new"


# ── sending a reply opens the next loop ─────────────────────────────────────

def test_sending_a_reply_opens_waiting_on_them():
    """The loop must not end when the reply goes out — that's exactly how an
    unanswered quote used to disappear for three weeks."""
    db = _session()
    a_counterparty(db, "u1", "dana@northwind.co", median_reply_h=6)
    msg(db, "u1", "t1", "in", ago_h=2, sender="Dana Levi <dana@northwind.co>")
    fu_service.sync_followups(db, "u1")
    assert db.query(models.FollowUp).one().state == fu_service.AWAITING_YOU

    fu = fu_service.record_outbound(
        db, "u1", thread_id="t1", message_id="sent1",
        to_email="dana@northwind.co", subject="Re: Q3",
    )

    assert fu is not None
    assert fu.state == fu_service.AWAITING_THEM
    assert fu.last_outbound_at is not None
    # And the ledger knows immediately, without waiting for a sweep.
    row = db.query(models.ThreadMessage).filter_by(gmail_message_id="sent1").one()
    assert row.direction == "out" and row.ts_exact is True


def test_record_outbound_links_the_alert_to_the_loop():
    db = _session()
    alert = models.Alert(
        user_id="u1", gmail_message_id="m1", thread_id="t1",
        sender="Dana <dana@northwind.co>", tier="urgent", status="done",
    )
    db.add(alert)
    db.commit()

    fu = fu_service.record_outbound(
        db, "u1", thread_id="t1", message_id="s1",
        to_email="dana@northwind.co", alert_id=alert.id,
    )

    assert db.query(models.Alert).one().followup_id == fu.id


# ── per-relationship aging ──────────────────────────────────────────────────

def test_a_slow_contact_is_not_chased_as_early_as_a_fast_one():
    """The reason aging isn't a global constant: a lawyer who answers in three
    days shouldn't be nudged after one."""
    db = _session()
    a_counterparty(db, "u1", "lawyer@firm.com", median_reply_h=72)
    a_counterparty(db, "u1", "quick@corp.com", median_reply_h=2)
    msg(db, "u1", "slow-t", "in", ago_h=100, sender="L <lawyer@firm.com>")
    msg(db, "u1", "slow-t", "out", ago_h=48)
    msg(db, "u1", "fast-t", "in", ago_h=100, sender="Q <quick@corp.com>")
    msg(db, "u1", "fast-t", "out", ago_h=48)

    fu_service.sync_followups(db, "u1")

    slow = db.query(models.FollowUp).filter_by(thread_id="slow-t").one()
    fast = db.query(models.FollowUp).filter_by(thread_id="fast-t").one()
    assert slow.stale_after_hours > fast.stale_after_hours
    # Same 48h of silence: normal for the lawyer, cold for the quick replier.
    assert slow.state == fu_service.AWAITING_THEM
    assert fast.state == fu_service.GOING_COLD


def test_staleness_is_clamped_to_sane_bounds():
    assert fu_service.stale_after_hours_for(None) == fu_service.DEFAULT_STALE_HOURS
    instant = models.Counterparty(email="a@b.com", their_median_reply_h=0)
    assert fu_service.stale_after_hours_for(instant) >= fu_service.MIN_STALE_HOURS
    glacial = models.Counterparty(email="a@b.com", their_median_reply_h=10_000)
    assert fu_service.stale_after_hours_for(glacial) <= fu_service.MAX_STALE_HOURS


def test_a_customer_is_chased_sooner_than_an_unknown():
    db = _session()
    slow_customer = models.Counterparty(
        user_id="u1", email="c@corp.com", their_median_reply_h=100,
        relationship=cp_service.CUSTOMER,
    )
    assert fu_service.stale_after_hours_for(slow_customer) <= 48


def test_an_explicit_deadline_tightens_the_clock():
    now = utcnow()
    lazy = models.Counterparty(email="a@b.com", their_median_reply_h=100)
    loose = fu_service.stale_after_hours_for(lazy, now=now)
    tight = fu_service.stale_after_hours_for(lazy, due_at=now + timedelta(hours=6), now=now)
    assert tight < loose and tight <= 6


# ── the clock ───────────────────────────────────────────────────────────────

def test_re_deriving_the_same_state_does_not_reset_the_clock():
    """If every sweep reset state_changed_at, nothing would ever age and no
    thread could go cold."""
    db = _session()
    a_counterparty(db, "u1", "dana@northwind.co", median_reply_h=1)
    msg(db, "u1", "t1", "in", ago_h=50, sender="Dana <dana@northwind.co>")
    msg(db, "u1", "t1", "out", ago_h=49)

    fu_service.sync_followups(db, "u1")
    first = db.query(models.FollowUp).one().state_changed_at
    for _ in range(3):
        fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).one().state_changed_at == first


def test_their_reply_reopens_a_cold_loop_as_owed():
    db = _session()
    a_counterparty(db, "u1", "mark@prospect.io", median_reply_h=2)
    msg(db, "u1", "t1", "out", ago_h=200)
    fu_service.sync_followups(db, "u1")
    assert db.query(models.FollowUp).one().state == fu_service.GOING_COLD

    msg(db, "u1", "t1", "in", ago_h=1, sender="Mark <mark@prospect.io>")
    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).one()
    assert fu.state == fu_service.AWAITING_YOU
    assert fu.closed_reason == "they_replied"


# ── the Alert / FollowUp boundary ───────────────────────────────────────────

def test_a_fresh_alert_is_not_also_an_owed_followup():
    """Otherwise the headline count double-counts and stops being trustworthy."""
    db = _session()
    now = utcnow()
    msg(db, "u1", "t1", "in", ago_h=2, sender="Dana <dana@northwind.co>")
    db.add(models.Alert(
        user_id="u1", gmail_message_id="m1", thread_id="t1",
        sender="Dana <dana@northwind.co>", tier="urgent", status="new",
        created_at=now - timedelta(hours=2),
    ))
    db.commit()
    fu_service.sync_followups(db, "u1")

    assert fu_service.list_followups(db, "u1", state="owed") == []
    assert fu_service.counts(db, "u1")["owed"] == 0


def test_an_aged_out_alert_becomes_an_owed_followup():
    db = _session()
    now = utcnow()
    msg(db, "u1", "t1", "in", ago_h=48, sender="Dana <dana@northwind.co>")
    db.add(models.Alert(
        user_id="u1", gmail_message_id="m1", thread_id="t1",
        sender="Dana <dana@northwind.co>", tier="urgent", status="new",
        created_at=now - timedelta(hours=48),
    ))
    db.commit()
    fu_service.sync_followups(db, "u1")

    owed = fu_service.list_followups(db, "u1", state="owed")
    assert len(owed) == 1 and owed[0].thread_id == "t1"


# ── user intent ─────────────────────────────────────────────────────────────

def test_not_a_followup_sticks_across_sweeps():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=5, sender="Dana <dana@northwind.co>")
    fu_service.sync_followups(db, "u1")

    fu_service.mark_ignored(db, db.query(models.FollowUp).one())
    for _ in range(3):
        fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).one().state == fu_service.IGNORED


def test_a_snoozed_loop_stays_parked_until_its_time():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=5, sender="Dana <dana@northwind.co>")
    fu_service.sync_followups(db, "u1")

    fu_service.snooze(db, db.query(models.FollowUp).one(), hours=48)
    fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).one().state == fu_service.SNOOZED


# ── ordering + counts ───────────────────────────────────────────────────────

def test_risk_puts_an_important_silence_above_an_unimportant_one():
    db = _session()
    a_counterparty(db, "u1", "vip@corp.com", median_reply_h=2, importance=90)
    a_counterparty(db, "u1", "meh@corp.com", median_reply_h=2, importance=10)
    for tid, who in (("t-vip", "vip@corp.com"), ("t-meh", "meh@corp.com")):
        msg(db, "u1", tid, "in", ago_h=200, sender=f"X <{who}>")
        msg(db, "u1", tid, "out", ago_h=190)

    fu_service.sync_followups(db, "u1")
    rows = fu_service.list_followups(db, "u1", state="open")

    assert rows[0].counterparty_email == "vip@corp.com"
    assert rows[0].risk > rows[-1].risk


def test_counts_partition_cleanly():
    db = _session()
    a_counterparty(db, "u1", "a@corp.com", median_reply_h=2)
    a_counterparty(db, "u1", "b@corp.com", median_reply_h=200)
    msg(db, "u1", "owed", "in", ago_h=48, sender="A <a@corp.com>")
    msg(db, "u1", "cold", "in", ago_h=300, sender="A <a@corp.com>")
    msg(db, "u1", "cold", "out", ago_h=290)
    msg(db, "u1", "waiting", "in", ago_h=10, sender="B <b@corp.com>")
    msg(db, "u1", "waiting", "out", ago_h=9)

    fu_service.sync_followups(db, "u1")
    c = fu_service.counts(db, "u1")

    assert c["owed"] == 1 and c["cold"] == 1 and c["waiting"] == 1
    assert c["open_loops"] == c["owed"] + c["waiting"] + c["cold"]


def test_users_are_isolated():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=3, sender="Dana <dana@northwind.co>")
    msg(db, "u2", "t2", "in", ago_h=3, sender="Other <other@corp.com>")

    fu_service.sync_followups(db, "u1")
    fu_service.sync_followups(db, "u2")

    assert [f.thread_id for f in fu_service.list_followups(db, "u1", state="all")] == ["t1"]
    assert [f.thread_id for f in fu_service.list_followups(db, "u2", state="all")] == ["t2"]


def test_sync_is_idempotent():
    db = _session()
    msg(db, "u1", "t1", "in", ago_h=3, sender="Dana <dana@northwind.co>")

    for _ in range(4):
        fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).count() == 1


def test_empty_ledger_is_a_no_op():
    db = _session()
    assert fu_service.sync_followups(db, "u1")["opened"] == 0
    assert fu_service.counts(db, "u1")["open_loops"] == 0


def test_an_overdue_loop_ranks_above_a_fresh_one_even_with_no_ranking_data():
    """On a fresh install nobody has an importance score yet. If risk were a
    straight multiply, every loop would score 0 and the list would come back
    unordered — with a two-week silence tied against this morning's mail."""
    db = _session()
    msg(db, "u1", "fresh", "in", ago_h=1, sender="A <a@corp.com>")
    msg(db, "u1", "stale", "in", ago_h=24 * 20, sender="B <b@corp.com>")
    msg(db, "u1", "stale", "out", ago_h=24 * 19)

    fu_service.sync_followups(db, "u1")

    fresh = db.query(models.FollowUp).filter_by(thread_id="fresh").one()
    stale = db.query(models.FollowUp).filter_by(thread_id="stale").one()
    assert stale.risk > 0, "an overdue loop must not score zero"
    assert stale.risk > fresh.risk
    assert fu_service.list_followups(db, "u1", state="open")[0].thread_id == "stale"


def test_a_known_important_person_still_outranks_an_unranked_one():
    """The floor must not flatten real ranking — it's a baseline, not a cap."""
    db = _session()
    a_counterparty(db, "u1", "vip@corp.com", median_reply_h=2, importance=95)
    for tid, who in (("t-vip", "vip@corp.com"), ("t-unknown", "nobody@corp.com")):
        msg(db, "u1", tid, "in", ago_h=200, sender=f"X <{who}>")
        msg(db, "u1", tid, "out", ago_h=190)

    fu_service.sync_followups(db, "u1")

    vip = db.query(models.FollowUp).filter_by(thread_id="t-vip").one()
    unknown = db.query(models.FollowUp).filter_by(thread_id="t-unknown").one()
    assert vip.risk > unknown.risk
