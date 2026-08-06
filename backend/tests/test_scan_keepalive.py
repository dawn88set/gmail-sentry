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
