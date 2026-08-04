"""
Accounts — the mailbox grouped into the companies behind it.

The value of this screen is entirely in the grouping being *right*. A list that
puts four unrelated strangers under "Gmail.Com", or that shows a company as
quiet while the worklist shows two overdue replies to it, is worse than no list
at all — it teaches the user their numbers can't be trusted.

So these tests hold the properties that make it usable rather than decorative:

  * a company is one row, however many people it has,
  * free-mail senders are their own account, never "Gmail.Com",
  * colleagues and newsletters stay out of the book of business,
  * the counts EQUAL what the worklist shows for the same people,
  * the ranking puts going-quiet above everything else.
"""
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import accounts, followups, worklist
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _cp(db, email, **kw):
    d = dict(
        user_id="u1",
        email=email,
        domain=email.split("@")[-1],
        display_name=email.split("@")[0].title(),
        relationship="customer",
        importance=50,
        is_internal=False,
        muted=False,
        last_seen_at=utcnow() - timedelta(days=1),
    )
    d.update(kw)
    c = models.Counterparty(**d)
    db.add(c)
    db.commit()
    return c


def _loop(db, email, **kw):
    d = dict(
        user_id="u1",
        thread_id=f"t-{email}",
        state=followups.AWAITING_YOU,
        ball="you",
        counterparty_email=email,
        counterparty_name=email.split("@")[0].title(),
        subject="Q3 quote",
        risk=40,
        created_at=utcnow() - timedelta(days=1),
        state_changed_at=utcnow() - timedelta(days=1),
        last_inbound_at=utcnow() - timedelta(days=1),
    )
    d.update(kw)
    f = models.FollowUp(**d)
    db.add(f)
    db.commit()
    return f


def test_one_company_is_one_row_however_many_people():
    db = _session()
    _cp(db, "dana@northwind.co")
    _cp(db, "sam@northwind.co")
    _cp(db, "jo@northwind.co")

    rows = accounts.build(db, "u1")

    assert len(rows) == 1
    assert rows[0].name == "Northwind"
    assert len(rows[0].people) == 3


def test_free_mail_senders_are_their_own_account_never_gmail_com():
    db = _session()
    _cp(db, "dana@gmail.com", display_name="Dana Levi")
    _cp(db, "mark@gmail.com", display_name="Mark Ruiz")

    rows = accounts.build(db, "u1")
    names = sorted(r.name for r in rows)

    # Two separate people, and neither is filed under the mail provider.
    assert names == ["Dana Levi", "Mark Ruiz"]
    assert all("Gmail" not in n for n in names)


def test_colleagues_and_bulk_stay_out_of_the_book_of_business():
    db = _session()
    _cp(db, "dana@northwind.co")
    _cp(db, "me@ourfirm.com", is_internal=True)
    _cp(db, "news@substack.com", relationship="bulk")
    _cp(db, "muted@loud.io", muted=True)

    rows = accounts.build(db, "u1")

    assert [r.name for r in rows] == ["Northwind"]


def test_crm_company_beats_the_domain():
    db = _session()
    _cp(db, "dana@nw-holdings-eu.co", crm_status="ok", crm_company="Northwind Ltd")

    rows = accounts.build(db, "u1")

    assert rows[0].name == "Northwind Ltd"
    assert rows[0].key == "crm:northwind ltd"


def test_crm_company_ignored_when_the_lookup_did_not_succeed():
    db = _session()
    # A stale company name with a failed lookup must not win — the domain is the
    # thing we actually observed.
    _cp(db, "dana@northwind.co", crm_status="error", crm_company="Old Name Inc")

    assert accounts.build(db, "u1")[0].name == "Northwind"


def test_counts_equal_what_the_worklist_shows_for_the_same_people():
    db = _session()
    _cp(db, "dana@northwind.co")
    _cp(db, "sam@northwind.co")
    _loop(db, "dana@northwind.co")
    _loop(db, "sam@northwind.co")

    work = worklist.build(db, "u1", limit=100)
    rows = accounts.build(db, "u1")

    # The whole point: the card and the list underneath cannot disagree.
    assert sum(r.needs_you for r in rows) == work["total"]
    assert rows[0].needs_you == rows[0].you_owe + rows[0].chasing


def test_going_quiet_outranks_a_bigger_but_calm_account():
    db = _session()
    _cp(db, "dana@northwind.co", importance=10)
    _cp(db, "sam@acme.io", importance=99)
    _loop(db, "dana@northwind.co", state=followups.GOING_COLD, ball="them",
          last_outbound_at=utcnow() - timedelta(days=12))
    _loop(db, "sam@acme.io")

    rows = accounts.build(db, "u1")

    assert rows[0].name == "Northwind"
    assert rows[0].chasing == 1
    assert accounts.to_dict(rows[0])["at_risk"] is True


def test_accounts_are_user_scoped():
    db = _session()
    _cp(db, "dana@northwind.co")
    _cp(db, "other@elsewhere.com", user_id="u2")

    rows = accounts.build(db, "u1")

    assert [r.name for r in rows] == ["Northwind"]
    assert accounts.build(db, "u2")[0].name == "Elsewhere"


def test_strongest_relationship_wins_within_an_account():
    db = _session()
    _cp(db, "dana@northwind.co", relationship="prospect")
    _cp(db, "sam@northwind.co", relationship="customer")

    assert accounts.build(db, "u1")[0].relationship == "customer"


def test_get_account_returns_none_for_a_key_that_no_longer_exists():
    db = _session()
    _cp(db, "dana@northwind.co")

    assert accounts.get_account(db, "u1", "d:gone.example") is None
    assert accounts.get_account(db, "u1", "d:northwind.co")["name"] == "Northwind"


def test_empty_mailbox_is_an_empty_list_not_an_error():
    db = _session()
    out = accounts.list_accounts(db, "u1")
    assert out == {"accounts": [], "total": 0, "at_risk": 0, "needs_you": 0, "you_owe": 0}
