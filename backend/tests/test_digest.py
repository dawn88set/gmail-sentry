"""
The daily report (backend/services/digest.py).

This is the one moment of clarity that arrives without the user opening
anything, so what it says — and when it stays quiet — is the whole product.

The section that earns its place is "going quiet". Unanswered mail announces
itself; silence doesn't. A prospect who stopped replying twelve days ago
generates no notification and appears in no inbox, and is invisible until the
quarter closes badly.
"""

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import digest
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def an_alert(db, user, *, tier, subject, sender, draft=""):
    a = models.Alert(
        user_id=user, gmail_message_id=f"m{subject}", thread_id=f"t{subject}",
        sender=sender, subject=subject, tier=tier, status="new",
        reply_draft=draft, deep_link="https://mail.google.com/x",
    )
    db.add(a)
    db.commit()
    return a


def a_loop(db, user, *, thread, state, who, ask="", subject="", ago_h=48, risk=50):
    f = models.FollowUp(
        user_id=user, thread_id=thread, state=state, ball="you" if state == "awaiting_you" else "them",
        counterparty_email=f"{who}@corp.com", counterparty_name=who.title(),
        ask_summary=ask, subject=subject, risk=risk,
        last_inbound_at=utcnow() - timedelta(hours=ago_h),
        last_outbound_at=utcnow() - timedelta(hours=ago_h),
        state_changed_at=utcnow() - timedelta(hours=ago_h),
    )
    db.add(f)
    db.commit()
    return f


# ── silence ─────────────────────────────────────────────────────────────────

def test_a_genuinely_quiet_day_sends_nothing():
    """A daily message that's usually empty gets muted, and then the one that
    matters is muted too."""
    db = _session()
    assert digest.build_digest_text(db, "u1") == ""


def test_filing_activity_alone_is_not_worth_a_report():
    """Filing 14 conversations is nice, but it isn't news — it doesn't need the
    user to do anything."""
    db = _session()
    db.add(models.ThreadFolder(
        user_id="u1", thread_id="t1", folder_name="Clients/Acme",
        status="filed", filed_at=utcnow() - timedelta(hours=2),
    ))
    db.commit()
    assert digest.build_digest_text(db, "u1") == ""


# ── the sections ────────────────────────────────────────────────────────────

def test_the_report_leads_with_a_headline_that_counts_loops():
    db = _session()
    an_alert(db, "u1", tier="urgent", subject="Contract", sender="Dana <d@x.com>")
    a_loop(db, "u1", thread="t-owed", state="awaiting_you", who="dana", ask="Send the quote")
    a_loop(db, "u1", thread="t-cold", state="going_cold", who="mark", subject="Pricing")

    text = digest.build_digest_text(db, "u1")

    assert "1 urgent" in text
    assert "1 you owe" in text and "1 going cold" in text


def test_going_quiet_names_the_person_and_how_long():
    """The section that only this app can produce — nothing else in an inbox
    surfaces an absence."""
    db = _session()
    a_loop(db, "u1", thread="t1", state="going_cold", who="mark",
           subject="Pricing for the rollout", ago_h=24 * 12)

    text = digest.build_digest_text(db, "u1")

    assert "🧊 Going quiet" in text
    assert "Mark" in text and "Pricing for the rollout" in text
    assert "silent 12d" in text


def test_owed_items_lead_with_the_ask_not_the_subject():
    """A report is only useful if it's actionable without opening anything."""
    db = _session()
    a_loop(db, "u1", thread="t1", state="awaiting_you", who="dana",
           ask="Needs the revised quote before Friday", subject="Re: Q3")

    text = digest.build_digest_text(db, "u1")

    assert "Needs the revised quote before Friday" in text


def test_owed_falls_back_to_the_subject_when_nothing_was_asked():
    db = _session()
    a_loop(db, "u1", thread="t1", state="awaiting_you", who="dana", ask="", subject="Q3 numbers")
    assert "Q3 numbers" in digest.build_digest_text(db, "u1")


def test_to_reply_items_carry_a_one_tap_approve_link():
    db = _session()
    an_alert(db, "u1", tier="needs_reply", subject="Invoice", sender="Bill <b@x.com>",
             draft="Sure, sending today.")
    text = digest.build_digest_text(db, "u1")
    assert "draft ready" in text and "Approve & send" in text


def test_filing_is_reported_alongside_real_news():
    db = _session()
    a_loop(db, "u1", thread="t1", state="awaiting_you", who="dana", ask="Send it")
    for i in range(3):
        db.add(models.ThreadFolder(
            user_id="u1", thread_id=f"f{i}", folder_name="Clients/Acme",
            status="filed", filed_at=utcnow() - timedelta(hours=1),
        ))
    db.add(models.MailFolder(user_id="u1", name="Vendors/Acme", status="proposed"))
    db.commit()

    text = digest.build_digest_text(db, "u1")

    assert "filed 3 conversations" in text
    assert "1 folder waiting for your OK" in text


def test_long_lists_are_capped_with_a_tail():
    db = _session()
    for i in range(9):
        a_loop(db, "u1", thread=f"t{i}", state="awaiting_you", who=f"p{i}", ask=f"Task {i}")

    text = digest.build_digest_text(db, "u1")

    assert "…and 4 more" in text, "9 owed, 5 shown"


def test_yesterdays_filing_is_not_reported_as_todays():
    db = _session()
    a_loop(db, "u1", thread="t1", state="awaiting_you", who="dana", ask="Send it")
    db.add(models.ThreadFolder(
        user_id="u1", thread_id="old", folder_name="Clients/Acme",
        status="filed", filed_at=utcnow() - timedelta(hours=48),
    ))
    db.commit()

    assert "filed" not in digest.build_digest_text(db, "u1")


def test_users_are_isolated():
    db = _session()
    a_loop(db, "u1", thread="t1", state="going_cold", who="mark", subject="Theirs")
    assert digest.build_digest_text(db, "u2") == ""
