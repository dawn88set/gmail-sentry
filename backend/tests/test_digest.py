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


# ── duplicate schedules ─────────────────────────────────────────────────────


def _sends(monkeypatch):
    """Record every delivery attempt instead of making one."""
    sent = []
    monkeypatch.setattr(
        digest.notify, "notify_all",
        lambda db, u, cfg, text: sent.append(text) or [{"ok": True, "channel": "slack"}],
    )
    return sent


def test_two_schedules_firing_together_send_one_report(monkeypatch):
    """The platform created TWO identical 08:00 instances of this trigger on the
    live workspace. The app can't stop a duplicate schedule existing, but the
    same report arriving twice is its problem, not the owner's."""
    db = _session()
    sent = _sends(monkeypatch)
    a_loop(db, "u1", thread="t1", state="going_cold", who="dana", subject="Q3")

    first = digest.run_digest(db, "u1")
    second = digest.run_digest(db, "u1")

    assert first["sent"] is True
    assert second["sent"] is False and second["reason"] == "already_sent"
    assert len(sent) == 1


def test_a_deliberate_second_report_later_in_the_day_still_sends(monkeypatch):
    """Morning and evening digests are a real thing someone might configure —
    the guard has to catch duplicates, not a second scheduled report."""
    db = _session()
    sent = _sends(monkeypatch)
    a_loop(db, "u1", thread="t1", state="going_cold", who="dana", subject="Q3")

    digest.run_digest(db, "u1")
    # Age the record past the window, as ten hours later would.
    ev = db.query(models.ActivityEvent).filter_by(user_id="u1", kind="report_sent").one()
    ev.at = utcnow() - digest.DUPLICATE_WINDOW - timedelta(minutes=1)
    db.commit()

    assert digest.run_digest(db, "u1")["sent"] is True
    assert len(sent) == 2


def test_one_users_report_does_not_suppress_anothers(monkeypatch):
    db = _session()
    sent = _sends(monkeypatch)
    a_loop(db, "u1", thread="t1", state="going_cold", who="dana", subject="Q3")
    a_loop(db, "u2", thread="t2", state="going_cold", who="sam", subject="Renewal")

    assert digest.run_digest(db, "u1")["sent"] is True
    assert digest.run_digest(db, "u2")["sent"] is True
    assert len(sent) == 2


# ── promises reach the one message that arrives unprompted ──────────────────


def _promise(db, user, thread, what, quote, *, days_late=0, to="Dana Levi"):
    from backend.services.ledger import utcnow as _now
    db.add(models.ThreadRead(
        user_id=user, thread_id=thread,
        your_commitment=what, commitment_quote=quote,
        commitment_due=_now() - timedelta(days=days_late) if days_late else None,
        read_at=_now(),
    ))
    db.add(models.FollowUp(
        user_id=user, thread_id=thread, state=followups_state(), ball="you",
        counterparty_email="dana@northwind.co", counterparty_name=to,
        subject="Q3", risk=10,
        created_at=_now() - timedelta(days=3), state_changed_at=_now() - timedelta(days=3),
        last_inbound_at=_now() - timedelta(days=3), last_activity_at=_now() - timedelta(days=3),
    ))
    db.commit()


def followups_state():
    from backend.services import followups as f
    return f.AWAITING_YOU


def test_a_promise_reaches_the_report_with_your_own_words():
    """A broken promise costs more than a late reply, and nothing else in the
    day reminds anyone of it. The report is what reaches someone away from their
    desk — which is exactly when a promise slips past its date."""
    db = _session()
    _promise(db, "u1", "t1", "send the revised pricing", "I'll get you revised pricing by Friday")

    text = digest.build_digest_text(db, "u1")

    assert "You promised" in text
    assert "send the revised pricing" in text
    assert "I'll get you revised pricing by Friday" in text   # checkable


def test_an_overdue_promise_is_marked_and_counted():
    db = _session()
    _promise(db, "u1", "t1", "send the revised pricing",
             "revised pricing by Friday", days_late=3)

    text = digest.build_digest_text(db, "u1")

    assert "past its date" in text
    assert "3d late" in text


def test_a_promise_alone_is_enough_to_send_a_report():
    """Before this, a day with nothing incoming but an overdue promise sent
    nothing at all — the quietest days are when a promise is most likely to be
    the only thing that matters."""
    db = _session()
    _promise(db, "u1", "t1", "send the revised pricing", "revised pricing by Friday")

    assert digest.build_digest_text(db, "u1") != ""


def test_a_genuinely_empty_day_still_sends_nothing():
    db = _session()
    assert digest.build_digest_text(db, "u1") == ""


def test_the_report_says_what_mail_is_ASKING_not_its_subject_line():
    """Same helper as the widget and the worklist. The report is where a bare
    "Re: Q3" is least useful — there is no screen beside it to explain."""
    db = _session()
    a = an_alert(db, "u1", tier="needs_reply", subject="Re: Q3",
                 sender="Dana Levi <dana@northwind.co>")
    db.add(models.ThreadRead(
        user_id="u1", thread_id=a.thread_id,
        their_ask="a 12% discount on 40 seats", their_ask_quote="12% discount",
    ))
    db.commit()

    text = digest.build_digest_text(db, "u1")

    assert "a 12% discount on 40 seats" in text
    assert "Re: Q3" not in text
