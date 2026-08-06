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


def test_a_tick_arriving_seconds_early_still_scans():
    """The bug that made "every 5 minutes" mean every ten.

    The platform fires the trigger on its own clock and every scheduler jitters.
    Measured against the last run's start, a tick landing at 4m58s of a 5-minute
    interval used to fail a bare `>=`; the scan was skipped and the next chance
    was a full interval later. Jitter is symmetric, so that lost every other tick
    and silently doubled the cadence the owner had chosen.
    """
    db = _session()
    _interval(db, 5)
    db.add(models.ScanRun(user_id="u1", started_at=utcnow() - timedelta(seconds=298)))
    db.commit()

    assert sentry.due_for_scan(db, "u1") is True


def test_a_tick_far_too_early_is_still_declined():
    """The grace window absorbs jitter — it does not become a second interval."""
    db = _session()
    _interval(db, 60)
    _scanned(db, minutes_ago=30)
    assert sentry.due_for_scan(db, "u1") is False


def test_the_grace_window_never_exceeds_a_minute():
    """On a daily cadence, 20% would be nearly five hours early."""
    assert sentry._grace(1440).total_seconds() == 60
    assert sentry._grace(5).total_seconds() == 60
    assert sentry._grace(1).total_seconds() == 12


def test_health_reports_the_cadence_actually_achieved():
    """The setting can only slow scanning down — the platform's trigger sets the
    ceiling. When the app is running far less often than the owner picked, it has
    to say so; nothing else in the product can reveal that gap."""
    db = _session()
    _interval(db, 5)
    for n in (2, 62, 121, 180, 240):     # ~1 hour apart, though 5 was asked for
        _scanned(db, minutes_ago=n)

    h = sentry.scan_health(db, "u1")

    assert h["verdict"] == "slower"
    assert h["configured_minutes"] == 5
    assert 55 <= h["typical_minutes"] <= 65
    assert "every 5" in h["message"]


def test_health_is_quiet_when_the_cadence_is_honoured():
    db = _session()
    _interval(db, 5)
    for n in (1, 6, 11, 16, 21):
        _scanned(db, minutes_ago=n)
    assert sentry.scan_health(db, "u1")["verdict"] == "ok"
    assert sentry.scan_health(db, "u1")["message"] == ""


def test_health_calls_out_a_schedule_that_has_stopped_firing():
    db = _session()
    _interval(db, 5)
    _scanned(db, minutes_ago=240)
    h = sentry.scan_health(db, "u1")
    assert h["verdict"] == "stalled"
    assert "Scan" in h["message"]     # tells them what to do right now


def test_health_on_a_mailbox_that_has_never_scanned():
    db = _session()
    h = sentry.scan_health(db, "u1")
    assert h["verdict"] == "never" and h["last_scan_at"] is None


def test_manual_scans_cannot_fake_a_healthy_cadence():
    """Pressing Scan shortens gaps, so `slower` stays conservative — but a burst
    of manual scans must not hide a schedule that isn't firing."""
    db = _session()
    _interval(db, 5)
    # Three manual scans in a minute, then nothing for four hours.
    for n in (241, 242, 243, 244):
        _scanned(db, minutes_ago=n)
    assert sentry.scan_health(db, "u1")["verdict"] == "stalled"


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
