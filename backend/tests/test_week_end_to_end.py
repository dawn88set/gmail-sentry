"""A week in one mailbox, run through every surface at once.

Unit tests check each piece against the assumptions that built it — which is
exactly how a whole feature can be dead while its tests pass. `money()` read the
key "value" from a structure the verifier writes as "text", so every amount was
silently dropped, and the unit tests agreed because they were written from the
same wrong assumption. Only running one real thread end to end showed it.

So this holds the pieces AGREEING: the worklist, the report, the money view, the
promise list and a chase, all describing the same four threads. Incoherence
between surfaces is what destroys trust in all of them, and it is invisible from
inside any single test.

Unit tests check pieces against the assumptions that built them. This checks
that the pieces AGREE — the worklist, the report, the money view, the promise
list and a chase all describing the same five threads. Incoherence between
surfaces is the thing that destroys trust in all of them, and it is invisible
from inside any single test.
"""
import json
import sys
import types
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import comprehension, counterparty, followups, worklist, ask, digest
from backend.services.ledger import utcnow

import pytest


@pytest.fixture()
def week():
    """Four threads, read by a stubbed-but-realistic model. Returns (db, user)."""
    U = "owner"
    now = utcnow()

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    # ── the mail ────────────────────────────────────────────────────────────────
    BODIES = {
        # A customer wants a discount, states a number, and is waiting on us.
        "m-north-1": "Hi — before we sign, we need a 12% discount on 40 seats. "
                     "That brings it to £38,400 for the year. Can you confirm by Friday?",
        # We promised something and haven't done it.
        "m-north-2": "Thanks — I'll get you the revised pricing by Friday.",
        # A supplier has gone quiet on us.
        "m-merid-1": "Following up on the Q4 delivery window — any update?",
        # Something finished; nobody owes anybody anything.
        "m-bright-1": "Perfect, that's all sorted. Thanks for your help!",
        # A lead we owe a reply to.
        "m-acme-1": "Could you send over the pilot scope and timeline?",
    }

    THREADS = [
        ("t-north",  "dana@northwind.co",        "Dana Levi", "Q3 renewal",       ["m-north-1", "m-north-2"]),
        ("t-merid",  "mark@meridian-supply.com", "Mark Ruiz", "Q4 delivery",      ["m-merid-1"]),
        ("t-bright", "sam@brightpath.io",        "Sam Okafor", "Onboarding",      ["m-bright-1"]),
        ("t-acme",   "priya@acme.io",            "Priya Shah", "Pilot scope",     ["m-acme-1"]),
    ]

    for tid, email, name, subject, msgs in THREADS:
        db.add(models.Counterparty(
            user_id=U, email=email, display_name=name, domain=email.split("@")[1],
            relationship="customer", importance=70, is_internal=False, muted=False,
            thread_count=3, your_reply_rate=80, last_seen_at=now - timedelta(days=1),
        ))
        for i, mid in enumerate(msgs):
            outbound = mid == "m-north-2"
            db.add(models.ThreadMessage(
                user_id=U, thread_id=tid, gmail_message_id=mid,
                direction="out" if outbound else "in",
                sender=("me@myco.com" if outbound else f"{name} <{email}>"),
                counterparty_email=email, subject=subject, hydrated=True,
                ts_lo=now - timedelta(days=9 - i), ts_hi=now - timedelta(days=9 - i, hours=-6),
            ))
    db.commit()

    # ── the model, stubbed but realistic ────────────────────────────────────────
    FACTS = {
        "t-north": {
            "their_ask": {"text": "a 12% discount on 40 seats",
                          "quote": "we need a 12% discount on 40 seats"},
            "your_commitment": {"text": "send the revised pricing",
                                "quote": "I'll get you the revised pricing by Friday", "due": ""},
            "blocked_on": "you",
            "amounts": [{"text": "£38,400", "quote": "£38,400 for the year"}],
            "summary": "Northwind want a discount before signing.",
        },
        "t-merid": {
            "their_ask": {"text": "", "quote": ""},
            "your_commitment": {"text": "", "quote": "", "due": ""},
            "blocked_on": "them",
            "amounts": [],
            "summary": "Waiting on Meridian for the Q4 window.",
        },
        "t-bright": {
            "their_ask": {"text": "", "quote": ""},
            "your_commitment": {"text": "", "quote": "", "due": ""},
            "blocked_on": "nobody",
            "amounts": [],
            "summary": "Onboarding finished.",
        },
        "t-acme": {
            "their_ask": {"text": "the pilot scope and timeline",
                          "quote": "Could you send over the pilot scope and timeline"},
            "your_commitment": {"text": "", "quote": "", "due": ""},
            "blocked_on": "you",
            "amounts": [],
            "summary": "Acme want the pilot scope.",
        },
    }

    _current = {"tid": None}


    class _Result:
        @property
        def content(self):
            return json.dumps(FACTS[_current["tid"]])


    class _Client:
        def chat(self, *a, **k):
            return _Result()


    mod = types.ModuleType("claritty_sdk.llm")
    mod.get_llm_client = lambda *a, **k: _Client()
    pkg = types.ModuleType("claritty_sdk")
    pkg.llm = mod
    sys.modules["claritty_sdk"] = pkg
    sys.modules["claritty_sdk.llm"] = mod
    comprehension.gmail_adapter.get_body = lambda db, u, mid: BODIES.get(mid, "")

    # ── read the threads ────────────────────────────────────────────────────────
    counterparty.recompute(db, U)
    followups.sync_followups(db, U)
    for tid, *_ in THREADS:
        _current["tid"] = tid
        comprehension.read(db, U, tid)
    followups.sync_followups(db, U)

    return db, U


def test_a_finished_thread_leaves_the_worklist(week):
    """"Perfect, that's all sorted" — nobody owes anybody anything. A worklist
    that keeps it is an inbox with extra steps."""
    db, U = week
    assert not any(i["thread_id"] == "t-bright" for i in worklist.build(db, U, limit=20)["items"])


def test_it_will_not_offer_to_chase_someone_waiting_on_you(week):
    db, U = week
    out = ask.ask(db, U, "chase Dana")
    assert "proposal" not in out


def test_it_will_chase_the_thread_that_is_genuinely_quiet(week):
    db, U = week
    out = ask.ask(db, U, "chase Meridian Supply")
    assert out.get("proposal", {}).get("kind") == "nudge"


def test_rows_say_what_is_being_asked_for(week):
    db, U = week
    row = next(i for i in worklist.build(db, U, limit=20)["items"] if i["thread_id"] == "t-north")
    assert row["headline"] == "a 12% discount on 40 seats"


def test_the_promise_reaches_both_the_app_and_the_report(week):
    db, U = week
    assert any("revised pricing" in c["what"] for c in comprehension.commitments(db, U))
    assert "revised pricing" in digest.build_digest_text(db, U)


def test_an_amount_arrives_with_the_sentence_it_came_from(week):
    """The bug this file exists for: money() read "value" where the verifier
    writes "text", so every amount was dropped and nothing anywhere said so."""
    db, U = week
    monies = comprehension.money(db, U)
    assert monies, "no amounts reached the money view"
    assert monies[0]["amount"] == "£38,400"
    assert "£38,400 for the year" in monies[0]["quote"]


def test_asking_about_money_answers_from_that_amount(week):
    db, U = week
    out = ask.ask(db, U, "who owes me money")
    assert out["title"] == "Money in your mail"
    assert "£38,400" in " ".join(str(l.get("text", "")) for l in out["lines"])
