"""
The activity log (backend/services/activity.py) and insights
(backend/services/insights.py).

This is the app's account of its own work, so the tests here are mostly about
not lying:

  * one user never sees another user's events,
  * a "6 conversations filed" row counts as six, not one,
  * a re-file doesn't double-count the same work,
  * recording never raises, because a bookkeeping failure must not be able to
    fail a scan,
  * insights report zero honestly on an empty mailbox rather than inventing a
    plausible-looking number.
"""

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import activity, insights
from backend.services import counterparty as cp_service
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


# ── the log ─────────────────────────────────────────────────────────────────

def test_record_does_not_commit_so_it_rolls_back_with_its_transaction():
    """An event claiming a thread was filed must not survive the filing failing."""
    db = _session()
    activity.record(db, "u1", "thread_filed", "Filed 2 conversations into Clients/Acme")
    db.rollback()
    assert db.query(models.ActivityEvent).count() == 0


def test_feed_is_scoped_to_one_user():
    db = _session()
    activity.record(db, "u1", "mail_flagged", "Flagged 2 emails")
    activity.record(db, "u2", "mail_flagged", "Flagged 9 emails")
    db.commit()

    mine = activity.feed(db, "u1")
    assert [e.title for e in mine] == ["Flagged 2 emails"]


def test_feed_is_newest_first_and_respects_the_window():
    db = _session()
    now = utcnow()
    activity.record(db, "u1", "reply_sent", "old", at=now - timedelta(days=40))
    activity.record(db, "u1", "reply_sent", "recent", at=now - timedelta(hours=2))
    activity.record(db, "u1", "reply_sent", "newest", at=now)
    db.commit()

    titles = [e.title for e in activity.feed(db, "u1", days=14)]
    assert titles == ["newest", "recent"]


def test_summary_sums_counts_where_one_row_means_many_things():
    """A row that says "6 conversations filed" is six pieces of work. Counting
    rows there would understate filing by roughly the size of a thread."""
    db = _session()
    activity.record(db, "u1", "thread_filed", "Filed 6", count=6)
    activity.record(db, "u1", "thread_filed", "Filed 2", count=2)
    activity.record(db, "u1", "mail_flagged", "Flagged 4", count=4)
    db.commit()

    out = activity.summary(db, "u1", days=7)
    assert out["filed"] == 8
    # Flagged is one event per scan, so it's counted as one occurrence — the
    # number of alerts lives on the Alerts screen, not here.
    assert out["flagged"] == 1


def test_summary_ignores_events_outside_the_window():
    db = _session()
    activity.record(db, "u1", "thread_filed", "old", count=5, at=utcnow() - timedelta(days=30))
    db.commit()
    assert activity.summary(db, "u1", days=7)["filed"] == 0


def test_by_day_groups_without_reordering():
    db = _session()
    now = utcnow()
    activity.record(db, "u1", "reply_sent", "a", at=now)
    activity.record(db, "u1", "reply_sent", "b", at=now - timedelta(minutes=5))
    activity.record(db, "u1", "reply_sent", "c", at=now - timedelta(days=2))
    db.commit()

    groups = activity.by_day(activity.feed(db, "u1"))
    assert len(groups) == 2
    assert groups[0]["label"] == "Today"
    assert [e["title"] for e in groups[0]["events"]] == ["a", "b"]
    assert [e["title"] for e in groups[1]["events"]] == ["c"]


def test_record_never_raises_on_bad_input():
    """Bookkeeping must not be able to fail a scan."""
    db = _session()
    assert activity.record(db, "", "thread_filed", "no user") is None
    assert activity.record(db, "u1", "", "no kind") is None
    db.commit()
    assert db.query(models.ActivityEvent).count() == 0


def test_short_sender_matches_what_the_report_shows():
    assert activity.short_sender('"Dana Levi" <dana@acme.co>') == "Dana Levi"
    assert activity.short_sender("solo@acme.co") == "solo@acme.co"
    assert activity.short_sender("") == "someone"


# ── insights ────────────────────────────────────────────────────────────────

def test_insights_on_an_empty_mailbox_reports_nothing_rather_than_guessing():
    db = _session()
    out = insights.build(db, "u1")
    assert out["coverage"] == {"days": 0, "messages": 0, "threads": 0, "since": None}
    assert out["response"]["groups"] == []
    assert out["attention"]["people"] == []
    assert out["at_risk"]["threads"] == []
    assert out["handled"]["filed"] == 0


def test_response_profile_groups_by_relationship_and_flags_thin_samples():
    db = _session()
    for i in range(4):
        db.add(models.Counterparty(
            user_id="u1", email=f"client{i}@acme.co", relationship=cp_service.CUSTOMER,
            your_median_reply_h=2, their_median_reply_h=6, thread_count=5, importance=70,
        ))
    db.add(models.Counterparty(
        user_id="u1", email="lead@other.co", relationship=cp_service.PROSPECT,
        your_median_reply_h=24, their_median_reply_h=48, thread_count=1, importance=30,
    ))
    db.commit()

    groups = {g["relationship"]: g for g in insights.response_profile(db, "u1")["groups"]}
    assert groups[cp_service.CUSTOMER]["you_answer_in_h"] == 2
    assert groups[cp_service.CUSTOMER]["people"] == 4
    assert groups[cp_service.CUSTOMER]["thin"] is False
    # One prospect is not a pattern, and the payload says so instead of hiding it.
    assert groups[cp_service.PROSPECT]["thin"] is True


def test_response_profile_excludes_muted_and_bulk():
    db = _session()
    db.add(models.Counterparty(
        user_id="u1", email="noreply@shop.com", relationship=cp_service.BULK,
        your_median_reply_h=1, thread_count=90,
    ))
    db.add(models.Counterparty(
        user_id="u1", email="quiet@acme.co", relationship=cp_service.CUSTOMER,
        your_median_reply_h=1, thread_count=4, muted=True,
    ))
    db.commit()
    assert insights.response_profile(db, "u1")["groups"] == []


def test_attention_ranks_by_importance_not_volume():
    db = _session()
    db.add(models.Counterparty(
        user_id="u1", email="loud@newsletter.co", relationship=cp_service.UNKNOWN,
        thread_count=200, importance=5, your_reply_rate=0,
    ))
    db.add(models.Counterparty(
        user_id="u1", email="client@acme.co", relationship=cp_service.CUSTOMER,
        thread_count=6, importance=88, your_reply_rate=90,
    ))
    db.commit()

    people = insights.attention(db, "u1")["people"]
    assert people[0]["email"] == "client@acme.co"


def test_handled_reads_from_the_log_so_it_cannot_disagree_with_the_feed():
    db = _session()
    activity.record(db, "u1", "thread_filed", "Filed 3", count=3)
    db.add(models.MailFolder(user_id="u1", name="Clients/Acme", status="active"))
    db.add(models.MailFolder(user_id="u1", name="Clients/Beta", status="proposed"))
    db.commit()

    out = insights.handled(db, "u1", days=30)
    assert out["filed"] == 3
    assert out["folders_active"] == 1
    assert out["folders_pending"] == 1


def test_coverage_reports_the_real_history_depth():
    db = _session()
    now = utcnow()
    for i, age in enumerate((1, 10, 20)):
        db.add(models.ThreadMessage(
            user_id="u1", gmail_message_id=f"m{i}", thread_id=f"t{i}", direction="in",
            ts_lo=now - timedelta(days=age), ts_hi=now - timedelta(days=age),
        ))
    db.commit()

    cov = insights.coverage(db, "u1")
    assert cov["messages"] == 3
    assert cov["threads"] == 3
    assert 19 <= cov["days"] <= 21
