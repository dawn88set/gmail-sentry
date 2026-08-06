"""The app checks its own watch, because the schedule is not its to run.

The platform fires `sentry-scan` and calls in. On the workspace this app is
installed in, that trigger has never fired once — every INTERVAL trigger across
every installed app sits hours to weeks past its `nextRunAt` with `lastRunAt`
null. An inbox assistant whose mail is only read when you press a button is a
mail client, so the app also scans when it is being used.

What these hold: it obeys the SAME interval as the scheduled path (a busy screen
must not turn into a scan per request), two callers arriving together cannot both
scan, and a failure in the background can never reach the response.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import sentry
from backend.services.ledger import utcnow


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@pytest.fixture()
def calls(db, monkeypatch):
    """Count run_scan calls, and point the keepalive at this test's session."""
    monkeypatch.setattr("backend.database.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    seen = []
    monkeypatch.setattr(sentry, "run_scan", lambda d, u, **k: seen.append(u) or {})
    return seen


def _interval(db, minutes):
    cfg = sentry.get_config(db, "u1")
    cfg.scan_interval_minutes = minutes
    db.commit()


def test_it_scans_when_the_interval_has_elapsed(db, calls):
    _interval(db, 5)
    db.add(models.ScanRun(user_id="u1", started_at=utcnow() - timedelta(minutes=9)))
    db.commit()

    sentry.scan_if_due("u1")

    assert calls == ["u1"]


def test_a_busy_screen_does_not_become_a_scan_per_request(db, calls):
    """The whole point of the interval. Polling is frequent; scanning is not."""
    _interval(db, 30)
    db.add(models.ScanRun(user_id="u1", started_at=utcnow() - timedelta(minutes=2)))
    db.commit()

    for _ in range(25):
        sentry.scan_if_due("u1")

    assert calls == []


def test_gmail_not_connected_is_not_an_error_here(db, monkeypatch):
    """The UI already says Gmail isn't connected — the background must stay quiet."""
    from backend.shared.adapters import IntegrationNotConnected

    monkeypatch.setattr("backend.database.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    def _boom(*a, **k):
        raise IntegrationNotConnected("gmail")

    monkeypatch.setattr(sentry, "run_scan", _boom)
    sentry.scan_if_due("u1")          # must not raise


def test_a_failing_scan_never_reaches_the_response(db, monkeypatch):
    monkeypatch.setattr("backend.database.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    def _boom(*a, **k):
        raise RuntimeError("gmail exploded")

    monkeypatch.setattr(sentry, "run_scan", _boom)
    sentry.scan_if_due("u1")          # must not raise


def test_a_started_scan_immediately_blocks_a_second_one(db):
    """Two polls arriving together must not both scan Gmail.

    `run_scan` claims its ScanRun row before doing any work, so the interval
    itself is the lock — without that, `due_for_scan` keeps saying yes right up
    until the first scan finishes writing its row at the very end.
    """
    _interval(db, 5)
    assert sentry.due_for_scan(db, "u1") is True

    # What run_scan now does first.
    db.add(models.ScanRun(user_id="u1"))
    db.commit()

    assert sentry.due_for_scan(db, "u1") is False


# ── one headline, two surfaces ──────────────────────────────────────────────


def test_the_widget_and_the_worklist_describe_the_same_mail_the_same_way():
    """The widget is the surface people actually look at; the app is the 10%.

    The widget was showing "Re: Q3" while the worklist showed what was being
    asked for, because each built its own headline. Two surfaces disagreeing
    about the same mail is worse than either being plain, so they share one
    function — this holds them together.
    """
    from backend.services import worklist

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    db.add(models.Alert(
        user_id="u1", gmail_message_id="m1", thread_id="t1",
        sender="Dana Levi <dana@northwind.co>", subject="Re: Q3",
        tier="urgent", status="new", created_at=utcnow(),
    ))
    db.add(models.ThreadRead(
        user_id="u1", thread_id="t1",
        their_ask="a 12% discount on 40 seats",
        their_ask_quote="12% discount on 40 seats",
    ))
    db.commit()

    alerts = db.query(models.Alert).all()
    widget_headline = worklist.alert_headlines(db, "u1", alerts)[alerts[0].id]
    app_headline = worklist.build(db, "u1")["items"][0]["headline"]

    assert widget_headline == app_headline == "a 12% discount on 40 seats"


def test_an_unread_thread_keeps_its_subject_rather_than_inventing_one():
    from backend.services import worklist

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.Alert(
        user_id="u1", gmail_message_id="m1", thread_id="t1",
        sender="Dana Levi <dana@northwind.co>", subject="Re: Q3",
        tier="urgent", status="new", created_at=utcnow(),
    ))
    db.commit()

    alerts = db.query(models.Alert).all()
    assert worklist.alert_headlines(db, "u1", alerts)[alerts[0].id] == "Re: Q3"


# ── claiming the row up front has consequences ──────────────────────────────
#
# run_scan now writes its ScanRun before doing the work, so the interval itself
# serialises concurrent polls. That is worth having, but it changes what a
# half-finished scan leaves behind, and both consequences are dishonesty of the
# kind this app is otherwise careful about.


def test_a_crashed_scan_does_not_masquerade_as_a_clean_one():
    """Worst case of claiming early: the row exists, the work never happened.

    "Last scan: just now" with no error is the app telling someone it read their
    mail when it did not — and `last_scan_error` exists precisely so the UI can
    explain why the time isn't advancing.
    """
    from backend.services import ledger

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    real = ledger.sync_ledger
    ledger.sync_ledger = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gmail died mid-scan"))
    try:
        with pytest.raises(RuntimeError):
            sentry.run_scan(db, "u1")
    finally:
        ledger.sync_ledger = real

    row = db.query(models.ScanRun).one()
    assert row.error and "gmail died mid-scan" in row.error


def test_a_failure_is_recorded_but_never_swallowed():
    """The caller still has to see it — routes map it to a 5xx."""
    from backend.services import ledger

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    real = ledger.sync_ledger
    ledger.sync_ledger = lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
    try:
        with pytest.raises(ValueError):
            sentry.run_scan(db, "u1")
    finally:
        ledger.sync_ledger = real


def test_a_disconnected_scan_keeps_the_last_good_cleanup_counts():
    """The subtler consequence. The not-connected path carries forward "the
    previous run's" counts — and once we claim our own row first, the newest run
    IS ours, so it carried forward its own zeros and wiped the snapshot on every
    scan that fired while Gmail was disconnected."""
    from backend.services import ledger
    from backend.shared.adapters import IntegrationNotConnected

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ScanRun(
        user_id="u1", started_at=utcnow() - timedelta(days=1),
        promo_count=812, social_count=140, spam_count=33,
    ))
    db.commit()

    real = ledger.sync_ledger
    ledger.sync_ledger = lambda *a, **k: (_ for _ in ()).throw(IntegrationNotConnected("gmail"))
    try:
        with pytest.raises(IntegrationNotConnected):
            sentry.run_scan(db, "u1")
    finally:
        ledger.sync_ledger = real

    newest = db.query(models.ScanRun).order_by(models.ScanRun.started_at.desc()).first()
    assert newest.error == "gmail_not_connected"
    assert (newest.promo_count, newest.social_count, newest.spam_count) == (812, 140, 33)
