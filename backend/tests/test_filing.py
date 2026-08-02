"""
Smart filing (backend/services/filing.py).

Filing writes labels into somebody's real mailbox, so the tests that matter most
here are the ones about restraint:

  * nothing is labelled with a folder the user hasn't approved,
  * a rejected folder is never proposed again,
  * the backlog is not relabelled the moment filing is switched on,
  * a thread the user's own LabelRule owns is left alone,
  * INBOX is never removed — labelling is not hiding,
  * an unclassifiable thread gets no folder rather than a wrong one.

And the feature itself: one conversation lands in one folder, including the
replies the user sent.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import counterparty as cp_service
from backend.services import filing
from backend.services.ledger import utcnow
from backend.shared.adapters import IntegrationError


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class FakeGmail:
    """Records what would be written to the mailbox."""

    def __init__(self):
        self.calls = []
        self.fail = False

    def batch_modify(self, db, user_id, ids, add=None, remove=None):
        if self.fail:
            raise IntegrationError("gmail", "boom")
        self.calls.append({"ids": list(ids), "add": list(add or []), "remove": list(remove or [])})
        return len(ids)


@pytest.fixture
def gmail(monkeypatch):
    fake = FakeGmail()
    monkeypatch.setattr(filing, "gmail_adapter", fake)
    return fake


_SEQ = [0]


def msg(db, user, thread, direction, *, ago_h=1, sender="", subject=""):
    _SEQ[0] += 1
    ts = utcnow() - timedelta(hours=ago_h)
    email = ""
    if sender:
        email = sender.split("<")[-1].strip(">").strip().lower() if "<" in sender else sender.lower()
    db.add(models.ThreadMessage(
        user_id=user, gmail_message_id=format(0x18F000 + _SEQ[0], "x"),
        thread_id=thread, direction=direction, ts_lo=ts, ts_hi=ts,
        hydrated=bool(sender), sender=sender, counterparty_email=email or None, subject=subject,
    ))
    db.commit()


def a_config(db, user, *, enabled=True, started_h_ago=24):
    cfg = models.SentryConfig(
        user_id=user, filing_enabled=enabled,
        filing_started_at=utcnow() - timedelta(hours=started_h_ago) if enabled else None,
    )
    db.add(cfg)
    db.commit()
    return cfg


def a_counterparty(db, user, email, *, relationship, name="", source="inferred", domain=None):
    c = models.Counterparty(
        user_id=user, email=email, domain=domain or email.split("@")[-1],
        display_name=name, relationship=relationship, relationship_source=source,
        importance=60,
    )
    db.add(c)
    db.commit()
    return c


# ── naming ──────────────────────────────────────────────────────────────────

def test_folder_name_is_relationship_over_company():
    cp = models.Counterparty(email="dana@northwind.co", domain="northwind.co",
                             relationship=cp_service.CUSTOMER)
    name, kind, conf = filing.folder_for_thread(cp, "Q3 quote")
    assert name == "Clients/Northwind" and kind == "counterparty" and conf > 0


def test_each_relationship_class_gets_its_own_parent():
    for rel, parent in (
        (cp_service.CUSTOMER, "Clients"),
        (cp_service.PROSPECT, "Prospects"),
        (cp_service.INTERNAL, "Internal"),
        (cp_service.VENDOR, "Vendors"),
    ):
        cp = models.Counterparty(email="a@meridian-supply.com", domain="meridian-supply.com",
                                 relationship=rel)
        assert filing.folder_for_thread(cp, "hi")[0] == f"{parent}/Meridian Supply"


def test_personal_mail_domains_file_under_the_person():
    """"Clients/Gmail.Com" would be worse than useless."""
    cp = models.Counterparty(email="dana.levi@gmail.com", domain="gmail.com",
                             display_name="Dana Levi", relationship=cp_service.CUSTOMER)
    assert filing.folder_for_thread(cp, "hi")[0] == "Clients/Dana Levi"


def test_a_stated_relationship_is_more_confident_than_an_inferred_one():
    inferred = models.Counterparty(email="a@acme.com", domain="acme.com",
                                   relationship=cp_service.CUSTOMER, relationship_source="inferred")
    stated = models.Counterparty(email="a@acme.com", domain="acme.com",
                                 relationship=cp_service.CUSTOMER, relationship_source="user")
    assert filing.folder_for_thread(stated, "x")[2] > filing.folder_for_thread(inferred, "x")[2]


def test_an_unclassifiable_thread_gets_no_folder():
    """A wrong folder is worse than none — the user then can't find the mail."""
    cp = models.Counterparty(email="who@unknown.com", domain="unknown.com", relationship="unknown")
    assert filing.folder_for_thread(cp, "hello there")[0] == ""
    assert filing.folder_for_thread(None, "hello there")[0] == ""


def test_topical_folders_match_obvious_subjects():
    assert filing.folder_for_thread(None, "Invoice #4821 is due")[0] == "Invoices"
    assert filing.folder_for_thread(None, "NDA for review")[0] == "Legal"


def test_a_slash_in_a_company_name_cannot_create_a_nested_folder():
    cp = models.Counterparty(email="a@x.com", domain="", display_name="Acme / Evil",
                             relationship=cp_service.CUSTOMER)
    assert filing.folder_for_thread(cp, "x")[0] == "Clients/Acme Evil"


# ── approval ────────────────────────────────────────────────────────────────

def test_nothing_is_filed_into_an_unapproved_folder(gmail):
    """The gate that keeps this out of trouble. A proposed folder is a question,
    not a decision."""
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")

    out = filing.run_filing(db, "u1", cfg)

    assert gmail.calls == [], "labelled the mailbox before the user approved anything"
    assert out["filed"] == 0
    assert "Clients/Northwind" in out["proposed"]
    assert db.query(models.MailFolder).one().status == "proposed"


def test_approving_a_folder_files_the_waiting_threads(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)

    filing.approve_folder(db, db.query(models.MailFolder).one())
    out = filing.run_filing(db, "u1", cfg)

    assert out["filed"] == 1
    assert gmail.calls[0]["add"] == ["Clients/Northwind"]
    assert db.query(models.ThreadFolder).one().status == "filed"


def test_a_rejected_folder_is_never_proposed_again(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)

    filing.reject_folder(db, db.query(models.MailFolder).one())
    out = filing.run_filing(db, "u1", cfg)

    assert out["proposed"] == []
    assert gmail.calls == []
    assert db.query(models.ThreadFolder).count() == 0, "pending threads should be dropped too"


def test_renaming_carries_the_waiting_threads_across(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)

    folder = db.query(models.MailFolder).one()
    filing.rename_folder(db, folder, "Accounts/Northwind Ltd")
    filing.approve_folder(db, folder)
    filing.run_filing(db, "u1", cfg)

    assert db.query(models.ThreadFolder).one().folder_name == "Accounts/Northwind Ltd"
    assert gmail.calls[0]["add"] == ["Accounts/Northwind Ltd"]


def test_proposals_are_capped_per_sweep(gmail):
    """Waking up to sixty pending folders makes people reject the feature."""
    db = _session()
    cfg = a_config(db, "u1")
    for i in range(12):
        a_counterparty(db, "u1", f"a{i}@corp{i}.com", relationship=cp_service.CUSTOMER)
        msg(db, "u1", f"t{i}", "in", sender=f"A <a{i}@corp{i}.com>", subject="hi")

    filing.run_filing(db, "u1", cfg)

    assert db.query(models.MailFolder).count() <= filing.MAX_PROPOSALS_PER_SWEEP


# ── the feature ─────────────────────────────────────────────────────────────

def test_a_conversation_is_filed_in_both_directions(gmail):
    """The point of the whole thing: the user's own replies stop being orphaned
    in Sent, including the ones sent from their phone."""
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", ago_h=5, sender="Dana <dana@northwind.co>", subject="Q3")
    msg(db, "u1", "t1", "out", ago_h=4)          # replied in-app
    msg(db, "u1", "t1", "out", ago_h=3)          # replied from the phone
    msg(db, "u1", "t1", "in", ago_h=2, sender="Dana <dana@northwind.co>")

    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())
    out = filing.run_filing(db, "u1", cfg)

    assert out["filed"] == 4, "every message in the thread should carry the label"
    assert len(gmail.calls) == 1, "one broker call per thread, not per message"
    assert len(gmail.calls[0]["ids"]) == 4


def test_filing_never_removes_inbox(gmail):
    """Labelling is not hiding. Archiving stays the user's decision."""
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())
    filing.run_filing(db, "u1", cfg)

    assert gmail.calls[0]["remove"] == []


def test_a_filed_thread_is_not_refiled(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())
    filing.run_filing(db, "u1", cfg)
    for _ in range(3):
        filing.run_filing(db, "u1", cfg)

    assert len(gmail.calls) == 1


def test_a_new_message_refiles_its_thread(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", ago_h=5, sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())
    filing.run_filing(db, "u1", cfg)

    msg(db, "u1", "t1", "out", ago_h=1)  # the user replies
    filing.run_filing(db, "u1", cfg)

    assert len(gmail.calls) == 2
    assert len(gmail.calls[1]["ids"]) == 2


# ── restraint ───────────────────────────────────────────────────────────────

def test_switching_filing_on_does_not_relabel_the_backlog(gmail):
    """The ledger backfills ~45 days. Without the forward-only rule the first
    sweep would relabel thousands of old threads at once."""
    db = _session()
    cfg = a_config(db, "u1", started_h_ago=1)
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "old", "in", ago_h=24 * 30, sender="Dana <dana@northwind.co>", subject="Ancient")
    msg(db, "u1", "new", "in", ago_h=0, sender="Dana <dana@northwind.co>", subject="Fresh")

    filing.run_filing(db, "u1", cfg)
    folder = db.query(models.MailFolder).one()
    filing.approve_folder(db, folder)
    filing.run_filing(db, "u1", cfg)

    filed_threads = {tf.thread_id for tf in db.query(models.ThreadFolder).all()}
    assert filed_threads == {"new"}, "the backlog must not be touched automatically"


def test_the_backlog_can_be_previewed_without_doing_anything(gmail):
    db = _session()
    a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    for i in range(3):
        msg(db, "u1", f"t{i}", "in", ago_h=24 * (i + 2),
            sender="Dana <dana@northwind.co>", subject="Q3")

    preview = filing.preview_backlog(db, "u1", days=30)

    assert preview and preview[0]["folder"] == "Clients/Northwind"
    assert preview[0]["threads"] == 3
    assert gmail.calls == [], "a preview must not write anything"


def test_a_users_own_label_rule_wins(gmail):
    """Someone who already configured filing gets no surprises from this layer."""
    db = _session()
    cfg = a_config(db, "u1")
    db.add(models.LabelRule(
        user_id="u1", name="Northwind", match_type="domain",
        match_value="northwind.co", target_label="Clients/Northwind", active=True,
    ))
    db.commit()
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")

    out = filing.run_filing(db, "u1", cfg)

    assert out["proposed"] == []
    assert gmail.calls == []


def test_bulk_and_muted_senders_are_never_filed(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    muted = a_counterparty(db, "u1", "loud@corp.com", relationship=cp_service.CUSTOMER)
    muted.muted = True
    db.commit()
    msg(db, "u1", "t-mute", "in", sender="Loud <loud@corp.com>", subject="Q3")
    msg(db, "u1", "t-bulk", "in", sender="News <newsletter@bigco.com>", subject="Invoice roundup")

    filing.run_filing(db, "u1", cfg)

    assert db.query(models.ThreadFolder).count() == 0


def test_filing_is_off_until_switched_on(gmail):
    db = _session()
    cfg = a_config(db, "u1", enabled=False)
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")

    out = filing.run_filing(db, "u1", cfg)

    assert out["filed"] == 0 and gmail.calls == []
    assert db.query(models.MailFolder).count() == 0


def test_a_broker_failure_marks_the_thread_and_does_not_raise(gmail):
    """Organising mail must never be able to fail a scan."""
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())

    gmail.fail = True
    out = filing.run_filing(db, "u1", cfg)

    assert out["filed"] == 0
    tf = db.query(models.ThreadFolder).one()
    assert tf.status == "failed" and tf.error


def test_users_are_isolated(gmail):
    db = _session()
    cfg1 = a_config(db, "u1")
    a_config(db, "u2")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg1)

    assert db.query(models.MailFolder).filter_by(user_id="u2").count() == 0


# ── the notification ────────────────────────────────────────────────────────

def test_the_summary_is_one_batched_line():
    """Filing runs every five minutes; a ping per message would be unusable."""
    line = filing.filing_summary_line({
        "filed": 6, "threads": 3,
        "by_folder": {"Clients/Northwind": 3, "Invoices": 2, "Legal": 1},
        "proposed": [],
    })
    assert line.startswith("📁 Filed 6 —")
    assert "Clients/Northwind" in line and "\n" not in line


def test_the_summary_flags_folders_waiting_for_approval():
    line = filing.filing_summary_line({"filed": 0, "by_folder": {}, "proposed": ["Clients/Acme"]})
    assert "1 new folder waiting for approval" in line


def test_a_quiet_sweep_says_nothing():
    assert filing.filing_summary_line({"filed": 0, "by_folder": {}, "proposed": []}) == ""


# ── the record ──────────────────────────────────────────────────────────────
#
# Filing used to be announced only in a chat message. In the app a folder showed
# a name and a number, so there was no way to see what had been put where, or
# when, or that anything had failed.

def _events(db, user="u1", kind=None):
    q = db.query(models.ActivityEvent).filter(models.ActivityEvent.user_id == user)
    if kind:
        q = q.filter(models.ActivityEvent.kind == kind)
    return q.order_by(models.ActivityEvent.at.asc()).all()


def test_filing_records_one_event_per_folder_counting_conversations(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    msg(db, "u1", "t2", "in", sender="Dana <dana@northwind.co>", subject="Q4")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())
    filing.run_filing(db, "u1", cfg)

    filed = _events(db, kind="thread_filed")
    assert len(filed) == 1, "one row per folder per sweep, not one per thread"
    assert filed[0].count == 2, "counts conversations, which is what the user recognises"
    assert filed[0].folder_name == "Clients/Northwind"
    assert "2 conversations into Clients/Northwind" in filed[0].title


def test_a_settled_thread_records_nothing_on_later_sweeps(gmail):
    """The scan runs every five minutes. If a quiet sweep wrote a row, the feed
    would become the log it exists to replace."""
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())
    filing.run_filing(db, "u1", cfg)
    for _ in range(5):
        filing.run_filing(db, "u1", cfg)

    assert len(_events(db, kind="thread_filed")) == 1


def test_a_filing_failure_is_recorded_rather_than_only_logged(gmail):
    """It used to be invisible everywhere: the thread simply never appeared in
    its folder and nothing said why."""
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    filing.approve_folder(db, db.query(models.MailFolder).one())

    gmail.fail = True
    filing.run_filing(db, "u1", cfg)

    failures = _events(db, kind="filing_failed")
    assert len(failures) == 1
    assert "Clients/Northwind" in failures[0].title
    assert failures[0].detail, "the reason has to survive, not just the fact"


def test_proposing_approving_and_rejecting_a_folder_are_all_on_the_record(gmail):
    db = _session()
    cfg = a_config(db, "u1")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg)
    assert [e.kind for e in _events(db)] == ["folder_proposed"]

    filing.reject_folder(db, db.query(models.MailFolder).one())
    assert [e.kind for e in _events(db)] == ["folder_proposed", "folder_rejected"]


def test_the_record_is_scoped_to_one_user(gmail):
    db = _session()
    cfg1 = a_config(db, "u1")
    a_config(db, "u2")
    a_counterparty(db, "u1", "dana@northwind.co", relationship=cp_service.CUSTOMER)
    msg(db, "u1", "t1", "in", sender="Dana <dana@northwind.co>", subject="Q3")
    filing.run_filing(db, "u1", cfg1)

    assert _events(db, "u2") == []
