"""
Nudges (backend/services/nudges.py).

A nudge is the only message this app puts in front of someone the user did not
just hear from, so nearly all of these tests are about refusing to send one.
The failure mode isn't a crash — it's an email the user wouldn't have written,
going to a client, in their name.

The single most dangerous case is the backfill: the ledger imports weeks of
history on first run, and most old silent threads are silent on purpose.
Without that guard the first successful sync would offer to chase everyone the
user deliberately stopped replying to.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import followups as fu_service
from backend.services import nudges
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def a_sync_state(db, user, *, backfill_done=True, done_h_ago=72):
    st = models.ThreadSyncState(
        user_id=user, backfill_done=backfill_done,
        backfill_done_at=utcnow() - timedelta(hours=done_h_ago) if backfill_done else None,
        self_address="me@acme.com", self_domain="acme.com",
    )
    db.add(st)
    db.commit()
    return st


def a_loop(db, user, *, thread="t1", state=fu_service.GOING_COLD, email="mark@prospect.io",
           name="Mark Ruiz", silent_days=12, nudge_count=0, created_h_ago=48, ask=""):
    f = models.FollowUp(
        user_id=user, thread_id=thread, state=state, ball="them",
        counterparty_email=email, counterparty_name=name,
        subject="Pricing for the rollout", ask_summary=ask,
        nudge_count=nudge_count, stale_after_hours=72,
        last_outbound_at=utcnow() - timedelta(days=silent_days),
        state_changed_at=utcnow() - timedelta(days=silent_days),
        created_at=utcnow() - timedelta(hours=created_h_ago),
    )
    db.add(f)
    db.commit()
    return f


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """No proxy in tests — drafting takes its template path, which is marked."""
    monkeypatch.setattr(nudges, "style_for", lambda db, uid: ([], "", "Best,\nSam"))


# ── it refuses far more often than it agrees ────────────────────────────────

def test_threads_from_the_imported_backlog_are_never_nudged():
    """THE guard. Old silence is usually deliberate — offering to chase forty
    abandoned threads is the worst thing this feature could do on day one."""
    db = _session()
    a_sync_state(db, "u1", backfill_done=True, done_h_ago=0)
    fu = a_loop(db, "u1", created_h_ago=0)  # discovered by the backfill just now

    nudge, why = nudges.generate_nudge(db, "u1", fu)

    assert nudge is None
    assert "existing history" in why
    assert db.query(models.Nudge).count() == 0


def test_nothing_is_nudgeable_while_history_is_still_importing():
    db = _session()
    a_sync_state(db, "u1", backfill_done=False)
    fu = a_loop(db, "u1")

    nudge, why = nudges.generate_nudge(db, "u1", fu)

    assert nudge is None and "history" in why


def test_a_thread_is_never_nudged_more_than_three_times():
    """After three unanswered chases the answer is no. A fourth is harassment
    sent on the user's behalf."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1", nudge_count=3)

    nudge, why = nudges.generate_nudge(db, "u1", fu)

    assert nudge is None and "three" in why.lower()


def test_two_cold_threads_with_one_person_do_not_produce_two_chases():
    """Otherwise the same contact gets two emails in one morning."""
    db = _session()
    a_sync_state(db, "u1")
    first = a_loop(db, "u1", thread="t1")
    first.last_nudge_at = utcnow() - timedelta(hours=2)
    first.nudge_count = 1
    db.commit()
    second = a_loop(db, "u1", thread="t2")

    nudge, why = nudges.generate_nudge(db, "u1", second)

    assert nudge is None
    assert "Mark Ruiz" in why and "hour" in why


def test_the_cooldown_expires():
    db = _session()
    a_sync_state(db, "u1")
    first = a_loop(db, "u1", thread="t1")
    first.last_nudge_at = utcnow() - timedelta(hours=72)
    first.nudge_count = 1
    db.commit()
    second = a_loop(db, "u1", thread="t2")

    nudge, why = nudges.generate_nudge(db, "u1", second)
    assert nudge is not None, why


def test_a_thread_where_the_ball_is_yours_cannot_be_nudged():
    """You owe them a reply. Chasing them for your own silence is absurd.

    Two separate guards cover this — the state check and the ball check — so
    both are exercised: an owed thread is refused outright, and a thread whose
    ball drifted to "you" is refused with the more specific message.
    """
    db = _session()
    a_sync_state(db, "u1")

    owed = a_loop(db, "u1", thread="t-owed", state=fu_service.AWAITING_YOU)
    owed.ball = "you"
    db.commit()
    assert nudges.generate_nudge(db, "u1", owed)[0] is None

    # Ball drifted back to the user while the state still says we're waiting.
    drifted = a_loop(db, "u1", thread="t-drift", email="d@corp.com", name="Dee")
    drifted.ball = "you"
    db.commit()
    nudge, why = nudges.generate_nudge(db, "u1", drifted)
    assert nudge is None and "your court" in why


def test_muted_contacts_and_no_reply_addresses_are_refused():
    db = _session()
    a_sync_state(db, "u1")
    db.add(models.Counterparty(user_id="u1", email="mark@prospect.io", muted=True))
    db.commit()
    assert nudges.generate_nudge(db, "u1", a_loop(db, "u1", thread="t1"))[0] is None

    bot = a_loop(db, "u1", thread="t2", email="no-reply@bigco.com", name="Bot")
    nudge, why = nudges.generate_nudge(db, "u1", bot)
    assert nudge is None and "nobody to nudge" in why


def test_every_refusal_is_explained_in_prose():
    """Silently disabling a button teaches people the app is broken. Saying why
    teaches them it's careful — so no guard may return a bare False."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1", nudge_count=99)
    _, why = nudges.generate_nudge(db, "u1", fu)
    assert len(why) > 20 and why[0].isupper()


# ── drafting ────────────────────────────────────────────────────────────────

def test_a_nudge_is_drafted_not_sent():
    """There is deliberately no state in which a nudge is queued to send itself."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")

    nudge, why = nudges.generate_nudge(db, "u1", fu)

    assert nudge is not None, why
    assert nudge.status == "proposed"
    assert nudge.sent_at is None and not nudge.external_id
    assert fu.nudge_count == 0, "drafting must not count as nudging"


def test_the_tone_escalates_with_each_attempt():
    db = _session()
    a_sync_state(db, "u1")
    for attempt, expected in ((0, "gentle"), (1, "direct"), (2, "closing")):
        fu = a_loop(db, "u1", thread=f"t{attempt}", nudge_count=attempt,
                    email=f"p{attempt}@corp.com", name=f"P{attempt}")
        nudge, why = nudges.generate_nudge(db, "u1", fu)
        assert nudge is not None, why
        assert nudge.tone == expected and nudge.attempt_no == attempt + 1


def test_the_closing_nudge_lets_the_thread_go_gracefully():
    """Often the most useful message in the sequence — it ends the thread
    honestly instead of leaving it dangling."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1", nudge_count=2)
    nudge, _ = nudges.generate_nudge(db, "u1", fu)
    assert nudge.tone == "closing"
    assert "priority" in (nudge.draft or "").lower()


def test_drafting_again_supersedes_rather_than_stacking():
    """Two live proposals would make "approve" ambiguous about what goes out."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")

    nudges.generate_nudge(db, "u1", fu)
    nudges.generate_nudge(db, "u1", fu)

    proposed = db.query(models.Nudge).filter_by(status="proposed").all()
    assert len(proposed) == 1
    assert db.query(models.Nudge).filter_by(status="skipped").count() == 1


def test_a_template_draft_never_claims_to_be_voice_matched():
    """With no LLM the draft is a template. Advertising it as "in your voice"
    would be a lie the user only discovers after sending."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")
    nudge, _ = nudges.generate_nudge(db, "u1", fu)

    payload = nudges.nudge_payload(nudge)

    assert payload["voice_matched"] is False
    assert not payload["draft"].startswith("[FB] "), "marker must be stripped for display"


def test_the_draft_is_threaded_and_addressed():
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")
    db.add(models.ThreadMessage(
        user_id="u1", gmail_message_id="18f0a1", thread_id=fu.thread_id, direction="in",
        ts_lo=utcnow(), ts_hi=utcnow(), rfc822_msgid="abc@mail",
    ))
    db.commit()

    nudge, _ = nudges.generate_nudge(db, "u1", fu)

    assert nudge.to_email == "mark@prospect.io"
    assert nudge.subject == "Re: Pricing for the rollout"
    assert nudge.in_reply_to == "abc@mail"


def test_an_explicit_tone_overrides_the_ladder():
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")
    nudge, _ = nudges.generate_nudge(db, "u1", fu, tone="closing")
    assert nudge.tone == "closing"


# ── after sending ───────────────────────────────────────────────────────────

def test_sending_restarts_the_clock_and_lengthens_the_next_wait():
    """Someone who ignored the first chase deserves longer before the next, not
    the same interval again."""
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")
    nudge, _ = nudges.generate_nudge(db, "u1", fu)
    before = fu.stale_after_hours

    nudges.mark_sent(db, "u1", nudge, fu, "sent-123")

    assert nudge.status == "sent" and nudge.external_id == "sent-123"
    assert fu.nudge_count == 1 and fu.last_nudge_at is not None
    assert fu.stale_after_hours > before


def test_the_cooldown_starts_at_send_not_at_draft():
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1", thread="t1")
    other = a_loop(db, "u1", thread="t2")

    n1, _ = nudges.generate_nudge(db, "u1", fu)
    # Drafting alone must not block the other thread…
    assert nudges.generate_nudge(db, "u1", other)[0] is not None

    nudges.mark_sent(db, "u1", n1, fu, "m1")
    # …but sending does.
    assert nudges.generate_nudge(db, "u1", other)[0] is None


def test_stale_hours_stay_within_bounds_after_repeated_nudges():
    db = _session()
    a_sync_state(db, "u1")
    fu = a_loop(db, "u1")
    for i in range(3):
        # Clear the per-contact cooldown BEFORE drafting — mark_sent sets it, so
        # clearing it afterwards leaves the next generate_nudge blocked.
        fu.last_nudge_at = None
        db.commit()
        n, why = nudges.generate_nudge(db, "u1", fu)
        assert n is not None, why
        nudges.mark_sent(db, "u1", n, fu, f"m{i}")
    assert fu.stale_after_hours <= fu_service.MAX_STALE_HOURS


def test_users_are_isolated():
    db = _session()
    a_sync_state(db, "u1")
    a_sync_state(db, "u2")
    fu = a_loop(db, "u1")
    nudges.generate_nudge(db, "u1", fu)

    assert nudges.open_proposal(db, "u2", fu.id) is None
