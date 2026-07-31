"""
run_scan over the thread ledger — the cost claim, verified.

The scan used to re-query `in:inbox newer_than:2d` every five minutes and
re-classify everything it found, because a message judged `fyi` left no trace.
On a quiet inbox that was ~20 LLM calls every five minutes — roughly 5,760 a day
to discover nothing had changed.

These tests pin the fix by counting: how many times the model is consulted, and
how many messages are fetched, across repeated scans of an unchanged mailbox.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import ledger, sentry
from backend.shared.adapters import IntegrationNotConnected

from test_ledger import FakeGmail


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class Counters:
    def __init__(self):
        self.classify = 0
        self.get_meta = 0


@pytest.fixture
def rig(monkeypatch):
    """A scan wired to a fake mailbox, with the metered calls counted."""
    counts = Counters()
    fake = FakeGmail()

    real_get_meta = fake.get_meta

    def counting_get_meta(db, user_id, message_id):
        counts.get_meta += 1
        return real_get_meta(db, user_id, message_id)

    fake.get_meta = counting_get_meta

    def fake_classify(rules, sender, subject, snippet):
        counts.classify += 1
        # "urgent" only for the one we plant as urgent; everything else is fyi,
        # which is precisely the case that used to leave no trace.
        tier = "urgent" if "URGENT" in (subject or "") else "fyi"
        return {"tier": tier, "reason": "because", "matched_rules": [], "source": "ai"}

    monkeypatch.setattr(ledger, "gmail_adapter", fake)
    monkeypatch.setattr(sentry, "gmail_adapter", fake)
    monkeypatch.setattr(sentry, "classify_email", fake_classify)
    monkeypatch.setattr(sentry, "_refresh_cleanup_counts", lambda db, uid, run: None)
    monkeypatch.setattr(sentry.notify, "notify_all", lambda *a, **k: [])
    monkeypatch.setattr(sentry, "get_profile", lambda db, uid: None)
    return fake, counts


def test_quiet_inbox_costs_nothing_on_the_second_scan(rig):
    """The headline: nothing new means no model calls and no message fetches."""
    fake, counts = rig
    db = _session()
    now = ledger.utcnow()
    for i in range(20):
        fake.add(f"18f0{i:02x}", f"t{i}", "in:inbox", now - timedelta(minutes=i + 1),
                 subject=f"Newsletter {i}")

    sentry.run_scan(db, "u1")
    assert counts.classify == 20, "first scan should judge each message once"

    before_classify, before_meta = counts.classify, counts.get_meta
    for _ in range(5):  # five more scan intervals, unchanged mailbox
        sentry.run_scan(db, "u1")

    assert counts.classify == before_classify, (
        "a quiet inbox must not re-classify anything — this is the 5,760-calls/day bug"
    )
    assert counts.get_meta == before_meta, "and must not re-fetch message bodies either"


def test_only_new_mail_is_judged(rig):
    fake, counts = rig
    db = _session()
    now = ledger.utcnow()
    fake.add("18f001", "t1", "in:inbox", now - timedelta(minutes=2), subject="Old news")

    sentry.run_scan(db, "u1")
    assert counts.classify == 1

    fake.add("18f002", "t2", "in:inbox", ledger.utcnow() - timedelta(seconds=1), subject="Fresh")
    sentry.run_scan(db, "u1")

    assert counts.classify == 2, "exactly one new message → exactly one new judgement"


def test_urgent_mail_still_becomes_an_alert(rig):
    """The cost fix must not cost us the actual feature."""
    fake, counts = rig
    db = _session()
    fake.add("18f0aa", "t1", "in:inbox", ledger.utcnow() - timedelta(minutes=1),
             subject="URGENT: contract")

    out = sentry.run_scan(db, "u1")

    alerts = db.query(models.Alert).all()
    assert len(alerts) == 1
    assert alerts[0].tier == "urgent"
    assert alerts[0].gmail_message_id == "18f0aa"
    assert out["flagged"] == 1


def test_an_alerted_message_is_never_re_alerted(rig):
    fake, counts = rig
    db = _session()
    fake.add("18f0bb", "t1", "in:inbox", ledger.utcnow() - timedelta(minutes=1),
             subject="URGENT: contract")

    for _ in range(4):
        sentry.run_scan(db, "u1")

    assert db.query(models.Alert).count() == 1
    assert counts.classify == 1


def test_muted_senders_are_settled_without_a_model_call(rig):
    """Muting is cheap to decide, so it should never spend a judgement — but it
    must still record a verdict, or the message returns on the next scan."""
    fake, counts = rig
    db = _session()
    fake.add("18f0cc", "t1", "in:inbox", ledger.utcnow() - timedelta(minutes=1),
             sender="noreply@spammy.io", subject="Deals")

    cfg = sentry.get_config(db, "u1")
    cfg.muted_senders = ["spammy.io"]
    db.commit()

    sentry.run_scan(db, "u1")
    sentry.run_scan(db, "u1")

    assert counts.classify == 0, "a muted sender shouldn't cost an LLM call"
    row = db.query(models.ThreadMessage).filter_by(gmail_message_id="18f0cc").one()
    assert row.triaged_at is not None, "muted mail must still be marked, or it comes back"
    assert db.query(models.Alert).count() == 0


def test_fyi_verdicts_are_persisted(rig):
    """The specific regression: `fyi` produces no Alert, so the ONLY record that
    it was ever judged is the ledger row."""
    fake, counts = rig
    db = _session()
    fake.add("18f0dd", "t1", "in:inbox", ledger.utcnow() - timedelta(minutes=1),
             subject="Newsletter")

    sentry.run_scan(db, "u1")

    row = db.query(models.ThreadMessage).filter_by(gmail_message_id="18f0dd").one()
    assert row.triage_tier == "fyi"
    assert row.triage_source == "ai"
    assert row.triaged_at is not None
    assert db.query(models.Alert).count() == 0


def test_not_connected_still_records_a_scan_run(rig, monkeypatch):
    """Scheduling visibility: a run that fires while Gmail is disconnected must
    still write a ScanRun, or the UI looks like scheduling stopped."""
    fake, counts = rig
    db = _session()

    def boom(*a, **k):
        raise IntegrationNotConnected("gmail")

    monkeypatch.setattr(ledger, "sync_ledger", boom)

    with pytest.raises(IntegrationNotConnected):
        sentry.run_scan(db, "u1")

    runs = db.query(models.ScanRun).all()
    assert len(runs) == 1
    assert runs[0].error == "gmail_not_connected"


def test_scan_sees_a_reply_sent_from_the_phone(rig):
    """End to end through run_scan: the sweep indexes in:sent, so the thread's
    ball flips without the app ever being told about the send."""
    fake, counts = rig
    db = _session()
    fake.add("18f100", "t1", "in:inbox", ledger.utcnow() - timedelta(minutes=5),
             subject="URGENT: contract")

    sentry.run_scan(db, "u1")
    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "you"

    fake.add("18f200", "t1", "in:sent", ledger.utcnow() - timedelta(seconds=1))
    sentry.run_scan(db, "u1")

    assert ledger.thread_ball(db, "u1")["t1"]["ball"] == "them"
