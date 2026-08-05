"""
How often the mailbox is checked, chosen by its owner.

The platform owns the schedule — `sentry-scan` fires on ITS interval and calls
the app — and that setting lives in Claritty's trigger UI, which is the wrong
place for a preference about how noisy someone's own inbox assistant should be.
So the cadence is app state and the SCHEDULED path checks it.

The distinction these hold: a scheduled tick respects the interval, and a person
pressing Scan never does. A button that silently declined to run would look
broken, which is worse than an extra Gmail request.
"""
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import sentry
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _scanned(db, minutes_ago: int):
    db.add(models.ScanRun(user_id="u1", started_at=utcnow() - timedelta(minutes=minutes_ago)))
    db.commit()


def _interval(db, minutes: int):
    cfg = sentry.get_config(db, "u1")
    cfg.scan_interval_minutes = minutes
    db.commit()


def test_a_mailbox_never_scanned_is_always_due():
    db = _session()
    _interval(db, 60)
    assert sentry.due_for_scan(db, "u1") is True


def test_not_due_before_the_chosen_interval_has_passed():
    db = _session()
    _interval(db, 60)
    _scanned(db, minutes_ago=10)
    assert sentry.due_for_scan(db, "u1") is False


def test_due_once_the_interval_has_passed():
    db = _session()
    _interval(db, 60)
    _scanned(db, minutes_ago=61)
    assert sentry.due_for_scan(db, "u1") is True


def test_the_default_matches_the_platform_trigger():
    db = _session()
    # 5 minutes, so an install that never touches the setting behaves exactly as
    # it did before this existed.
    assert sentry.get_config(db, "u1").scan_interval_minutes == 5


def test_a_scheduled_run_declines_early_and_reports_why():
    db = _session()
    _interval(db, 60)
    _scanned(db, minutes_ago=5)

    out = sentry.run_scan(db, "u1", respect_interval=True)

    assert out["skipped"] == "interval"
    assert out["scanned"] == 0
    # And it must not have written a ScanRun — otherwise every declined tick
    # would push the next real scan another interval away, forever.
    assert db.query(models.ScanRun).count() == 1
