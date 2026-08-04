"""
The worklist — what your email needs from you, ranked.

The app computed all of this and showed inventory instead: alerts in one
section, loops in another, junk counts in a third. These tests hold the three
properties that make it a worklist rather than a fourth list:

  * it says what to DO (the ask), not what arrived (the subject),
  * it never invents a deadline,
  * overdue outranks everything, and nothing is counted twice.
"""
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import activity, followups, worklist
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _alert(db, **kw):
    d = dict(user_id="u1", gmail_message_id="m1", thread_id="t1",
             sender="Dana Levi <dana@northwind.co>", subject="Q3 quote",
             tier="needs_reply", status="new", created_at=utcnow() - timedelta(hours=3))
    d.update(kw)
    a = models.Alert(**d)
    db.add(a); db.commit()
    return a


def _loop(db, **kw):
    d = dict(user_id="u1", thread_id="t1", state=followups.AWAITING_YOU, ball="you",
             counterparty_email="dana@northwind.co", counterparty_name="Dana Levi",
             subject="Q3 quote", risk=40, created_at=utcnow() - timedelta(days=1),
             state_changed_at=utcnow() - timedelta(days=1))
    d.update(kw)
    f = models.FollowUp(**d)
    db.add(f); db.commit()
    return f


def test_a_row_says_what_to_do_not_what_arrived():
    """"Send the revised pricing" beats "Q3 quote". The ask lives on the loop,
    the alert only has a subject — so it has to be carried across."""
    db = _session()
    _alert(db)
    _loop(db, ask_summary="Send the revised pricing before Friday")

    item = worklist.build(db, "u1")["items"][0]
    assert item["headline"] == "Send the revised pricing before Friday"
    assert item["subject"] == "Q3 quote"     # still available, as the second line


def test_it_falls_back_to_the_subject_rather_than_inventing_one():
    db = _session()
    _alert(db, subject="Contract review")
    item = worklist.build(db, "u1")["items"][0]
    assert item["headline"] == "Contract review"


def test_a_real_deadline_is_surfaced():
    """due_at was parsed and then rendered nowhere in the entire UI."""
    db = _session()
    _alert(db)
    _loop(db, due_at=utcnow() + timedelta(days=2))
    item = worklist.build(db, "u1")["items"][0]
    assert item["due_label"].startswith("due ")
    assert item["overdue"] is False


def test_an_overdue_item_says_so_and_outranks_everything():
    db = _session()
    _alert(db, gmail_message_id="m9", thread_id="t9", tier="urgent",
           sender="Urgent Person <x@y.com>", subject="urgent thing")
    _alert(db)
    _loop(db, due_at=utcnow() - timedelta(days=2))

    out = worklist.build(db, "u1")
    assert out["items"][0]["overdue"] is True
    assert "overdue" in out["items"][0]["due_label"]
    assert out["overdue"] == 1


def test_no_deadline_means_no_deadline_shown():
    """A fabricated due date is worse than none — the ordering has to be
    trustable without checking it."""
    db = _session()
    _alert(db)
    item = worklist.build(db, "u1")["items"][0]
    assert item["due_label"] == ""
    assert item["due_at"] is None


def test_nothing_is_counted_twice():
    """Alerts and follow-ups are disjoint by construction: list_followups drops
    threads whose newest inbound still has a live alert."""
    db = _session()
    _alert(db)
    _loop(db)
    out = worklist.build(db, "u1")
    assert out["total"] == 1, [i["id"] for i in out["items"]]


def test_a_quiet_thread_becomes_a_chase_not_a_reply():
    db = _session()
    _loop(db, thread_id="t2", state=followups.GOING_COLD, ball="them",
          last_outbound_at=utcnow() - timedelta(days=12),
          state_changed_at=utcnow() - timedelta(days=12))
    item = worklist.build(db, "u1")["items"][0]
    assert item["kind"] == worklist.CHASE
    assert "silent" in item["age_label"]


def test_it_reports_what_can_be_cleared_in_one_tap():
    db = _session()
    _alert(db, reply_draft="Here you go.", reply_status="drafted")
    out = worklist.build(db, "u1")
    assert out["ready_to_send"] == 1
    assert out["items"][0]["reply_ready"] is True


def test_done_today_counts_work_that_moved_a_conversation():
    """An inbox is endless; a list you cleared is the difference between a
    worklist and an anxiety list. Dismissing an alert is not work done."""
    db = _session()
    activity.record(db, "u1", "reply_sent", "You replied to Dana")
    activity.record(db, "u1", "nudge_sent", "You followed up with Mark")
    activity.record(db, "u1", "mail_flagged", "Flagged 3 emails")   # not work
    db.commit()
    assert worklist.build(db, "u1")["done_today"] == 2


def test_it_is_scoped_to_one_user():
    db = _session()
    _alert(db)
    _alert(db, user_id="u2", gmail_message_id="m2", subject="not yours")
    assert worklist.build(db, "u1")["total"] == 1


def test_rows_name_the_company_not_just_the_person():
    """"Sam Ortiz" means nothing to an owner with two hundred contacts.

    The company is what they can picture, and it is what ties this list to the
    Accounts screen — without it the two read as two separate lists of the same
    mail.
    """
    db = _session()
    db.add(models.Counterparty(
        user_id="u1", email="dana@northwind.co", domain="northwind.co",
        display_name="Dana Levi", relationship="customer", importance=80,
    ))
    db.commit()
    _loop(db, counterparty_email="dana@northwind.co")

    row = worklist.build(db, "u1")["items"][0]

    assert row["company"] == "Northwind"


def test_an_alert_row_resolves_its_company_from_a_raw_from_header():
    """Alerts store `Dana Levi <dana@x.co>` while loops store the bare address.

    Keying the lookup on one without normalising the other would silently blank
    the company on exactly the rows that arrive first.
    """
    db = _session()
    db.add(models.Counterparty(
        user_id="u1", email="dana@northwind.co", domain="northwind.co",
        display_name="Dana Levi", relationship="customer", importance=80,
    ))
    db.commit()
    _alert(db, sender="Dana Levi <dana@northwind.co>")

    row = worklist.build(db, "u1")["items"][0]

    assert row["company"] == "Northwind"


def test_an_unknown_sender_has_no_company_rather_than_a_guess():
    db = _session()
    _loop(db, counterparty_email="stranger@nowhere.example")

    assert worklist.build(db, "u1")["items"][0]["company"] == ""
