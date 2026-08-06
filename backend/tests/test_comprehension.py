"""
Reading the mail — and refusing to report anything the mail doesn't say.

This is the first thing in the app that forms a judgement rather than counting
rows, so it is also the first thing that COULD fabricate. The design that stops
it: every field the model returns must carry a quote, and any field whose quote
isn't present verbatim in the fetched messages is dropped before it can be
stored. There is no path from the model to the database that skips that check.

So the tests that matter most here are the ones proving a made-up claim dies —
and, just as important, that a REAL quote survives hard-wrapped, re-cased,
non-breaking-space mail. A verifier that rejects genuine quotes silently turns
the whole feature off, which is the worse failure because nothing looks broken.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import comprehension
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


_seq = [0]


def _msg(db, thread_id, *, direction="in", sender="dana@northwind.co", subject="Renewal",
         snippet="", days=1):
    _seq[0] += 1
    m = models.ThreadMessage(
        user_id="u1", thread_id=thread_id, gmail_message_id=f"m{_seq[0]}",
        direction=direction, sender=sender,
        counterparty_email="dana@northwind.co", subject=subject, snippet=snippet,
        hydrated=True,
        ts_lo=utcnow() - timedelta(days=days, hours=6),
        ts_hi=utcnow() - timedelta(days=days),
    )
    db.add(m); db.commit()
    return m


THREAD_TEXT = (
    "Hi — thanks for the numbers. Before we sign off, can you do better than list "
    "on 40 seats? We're comparing against two other quotes.\n\n"
    "Sure — I'll get you revised pricing by Friday."
)


def _stub_llm(monkeypatch, payload):
    """Stand in for the platform proxy. Returns whatever `payload` says."""
    import json as _json

    class _Result:
        content = _json.dumps(payload)

    class _Client:
        def chat(self, *a, **k):
            return _Result()

    import sys, types
    mod = types.ModuleType("claritty_sdk.llm")
    mod.get_llm_client = lambda *a, **k: _Client()
    pkg = types.ModuleType("claritty_sdk")
    pkg.llm = mod
    monkeypatch.setitem(sys.modules, "claritty_sdk", pkg)
    monkeypatch.setitem(sys.modules, "claritty_sdk.llm", mod)


@pytest.fixture
def bodies(monkeypatch):
    """Serve the thread text as message bodies, and count broker calls."""
    calls = {"n": 0}

    def fake_get_body(db, user_id, message_id):
        calls["n"] += 1
        return THREAD_TEXT

    monkeypatch.setattr(comprehension.gmail_adapter, "get_body", fake_get_body)
    return calls


# ── quote verification: the whole safety story ──────────────────────────────

def test_a_real_quote_survives_hard_wraps_case_and_nbsp():
    # Bodies arrive wrapped, re-cased and full of non-breaking spaces. A strict
    # comparison would reject nearly every genuine quote and silently disable
    # the feature while looking fine.
    haystack = comprehension._norm(
        "Before we sign off,\r\n  CAN YOU do better than list on 40 seats?"
    )
    assert comprehension._quoted("can you do better than list", haystack)


def test_a_fabricated_quote_is_rejected():
    haystack = comprehension._norm(THREAD_TEXT)
    assert not comprehension._quoted("we can offer you 20% off", haystack)


def test_a_trivially_short_quote_is_rejected():
    # Five characters of ordinary prose match almost any thread and prove
    # nothing, so they don't count as evidence.
    haystack = comprehension._norm(THREAD_TEXT)
    assert not comprehension._quoted("seats", haystack)


def test_a_short_quote_containing_a_number_still_counts():
    """Amounts are short by nature and specific by nature.

    A flat length floor dropped "on 40 seats" at eleven characters during an
    end-to-end run — silently losing the one field an owner most wants quoted.
    A fragment with a digit in it ("£2,400", "invoice 88213") is evidence even
    when it's brief.
    """
    haystack = comprehension._norm(THREAD_TEXT)
    assert comprehension._quoted("on 40 seats", haystack)
    # Still has to actually BE there.
    assert not comprehension._quoted("on 90 seats", haystack)


def test_a_field_whose_quote_is_absent_is_dropped_entirely():
    facts = comprehension._verify(
        {
            "their_ask": {"text": "a 20% discount", "quote": "we can offer you 20% off"},
            "your_commitment": {"text": "revised pricing by Friday",
                                "quote": "I'll get you revised pricing by Friday", "due": "Friday"},
        },
        comprehension._norm(THREAD_TEXT),
    )
    # The invented ask is gone; the real commitment survives.
    assert facts["their_ask"] == ""
    assert "their_ask" in facts["dropped"]
    assert facts["your_commitment"] == "revised pricing by Friday"


def test_an_amount_the_mail_never_stated_is_dropped():
    facts = comprehension._verify(
        {"amounts": [
            {"text": "£2,400", "quote": "invoice for £2,400"},        # not in the text
            {"text": "40 seats", "quote": "do better than list on 40 seats"},
        ]},
        comprehension._norm(THREAD_TEXT),
    )
    assert [a["text"] for a in facts["amounts"]] == ["40 seats"]


def test_blocked_on_only_accepts_the_three_real_answers():
    h = comprehension._norm(THREAD_TEXT)
    assert comprehension._verify({"blocked_on": "them"}, h)["blocked_on"] == "them"
    assert comprehension._verify({"blocked_on": "probably you?"}, h)["blocked_on"] == ""


# ── reading a thread end to end ─────────────────────────────────────────────

def test_reading_a_thread_stores_the_ask_and_the_promise(bodies, monkeypatch):
    db = _session()
    _msg(db, "t1", direction="in", days=3)
    _msg(db, "t1", direction="out", sender="me@ourfirm.com", days=2)
    _stub_llm(monkeypatch, {
        "their_ask": {"text": "a discount on 40 seats", "quote": "can you do better than list"},
        "your_commitment": {"text": "revised pricing", "quote": "I'll get you revised pricing by Friday",
                            "due": "Friday"},
        "blocked_on": "you",
        "amounts": [],
        "summary": "They want a discount; you owe them pricing.",
    })

    row = comprehension.read(db, "u1", "t1")

    assert row.their_ask == "a discount on 40 seats"
    assert row.your_commitment == "revised pricing"
    assert row.blocked_on == "you"
    # A date the mail actually stated, through the app's conservative parser.
    assert row.commitment_due is not None


def test_a_thread_that_has_not_moved_is_never_re_read(bodies, monkeypatch):
    db = _session()
    _msg(db, "t1")
    _stub_llm(monkeypatch, {"their_ask": {"text": "a discount",
                                          "quote": "can you do better than list"}})

    comprehension.read(db, "u1", "t1")
    first = bodies["n"]
    assert first > 0
    assert comprehension.needs_read(db, "u1", "t1") is False

    # The budgeted pass must not spend a single broker call on it.
    comprehension.read_pending(db, "u1", ["t1"])
    assert bodies["n"] == first


def test_a_thread_that_gains_a_message_is_read_again(bodies, monkeypatch):
    db = _session()
    _msg(db, "t1")
    _stub_llm(monkeypatch, {"their_ask": {"text": "a discount",
                                          "quote": "can you do better than list"}})
    comprehension.read(db, "u1", "t1")

    _msg(db, "t1", days=0)  # they replied
    assert comprehension.needs_read(db, "u1", "t1") is True


def test_the_scan_budget_is_respected(bodies, monkeypatch):
    db = _session()
    for i in range(10):
        _msg(db, f"t{i}")
    _stub_llm(monkeypatch, {"their_ask": {"text": "a discount",
                                          "quote": "can you do better than list"}})

    done = comprehension.read_pending(db, "u1", [f"t{i}" for i in range(10)], limit=3)

    assert done == 3
    assert db.query(models.ThreadRead).count() == 3


def test_newsletters_are_never_read(bodies, monkeypatch):
    db = _session()
    m = _msg(db, "t1", sender="no-reply@news.example")
    m.counterparty_email = "no-reply@news.example"
    db.commit()
    _stub_llm(monkeypatch, {"their_ask": {"text": "x", "quote": "can you do better than list"}})

    assert comprehension.read(db, "u1", "t1") is None
    assert bodies["n"] == 0  # not even a body fetch


def test_with_no_llm_it_no_ops_instead_of_storing_blanks(bodies):
    db = _session()
    _msg(db, "t1")

    # No stub — importing claritty_sdk fails exactly as it does in local dev.
    assert comprehension.read(db, "u1", "t1") is None
    assert db.query(models.ThreadRead).count() == 0


def test_reads_are_user_scoped(bodies, monkeypatch):
    db = _session()
    _msg(db, "t1")
    _stub_llm(monkeypatch, {"their_ask": {"text": "a discount",
                                          "quote": "can you do better than list"}})
    comprehension.read(db, "u1", "t1")

    assert comprehension.get(db, "u2", "t1") is None
    assert comprehension.get(db, "u1", "t1") is not None


# ── commitments: the thing no mail client tracks ────────────────────────────
# "Did you reply" is what every inbox measures. "Did you do what you said" is
# what people are actually judged on, and it only exists because the thread got
# read — the promise is in the user's own sent mail.

def _read(db, thread_id, **kw):
    d = dict(user_id="u1", thread_id=thread_id, your_commitment="revised pricing",
             commitment_quote="I'll get you revised pricing by Friday",
             commitment_at=utcnow() - timedelta(days=6))
    d.update(kw)
    r = models.ThreadRead(**d)
    db.add(r); db.commit()
    return r


def _loop(db, thread_id, name="Dana Levi", email="dana@northwind.co"):
    f = models.FollowUp(
        user_id="u1", thread_id=thread_id, state="awaiting_you", ball="you",
        counterparty_email=email, counterparty_name=name, subject="Renewal",
        created_at=utcnow() - timedelta(days=6), state_changed_at=utcnow() - timedelta(days=6),
    )
    db.add(f); db.commit()
    return f


def test_an_open_promise_is_listed_with_the_sentence_you_wrote():
    db = _session()
    _read(db, "t1")
    _loop(db, "t1")

    out = comprehension.commitments(db, "u1")

    assert out[0]["what"] == "revised pricing"
    assert out[0]["to"] == "Dana Levi"
    # Checkable, not merely asserted — this is what makes it safe to act on.
    assert out[0]["quote"] == "I'll get you revised pricing by Friday"


def test_overdue_promises_come_first_and_say_how_late():
    db = _session()
    _read(db, "t1", your_commitment="the deck", commitment_due=utcnow() - timedelta(days=3))
    _read(db, "t2", your_commitment="pricing", commitment_due=utcnow() + timedelta(days=2))
    _read(db, "t3", your_commitment="an intro", commitment_due=None)

    out = comprehension.commitments(db, "u1")

    assert [c["what"] for c in out] == ["the deck", "pricing", "an intro"]
    assert out[0]["overdue_days"] == 3
    assert out[1]["overdue_days"] == 0


def test_a_promise_is_kept_when_you_next_write_on_that_thread():
    db = _session()
    _read(db, "t1")
    assert len(comprehension.commitments(db, "u1")) == 1

    comprehension.mark_met(db, "u1", "t1")
    db.commit()

    # Gone from the list, and the moment it was met is recorded — that cannot be
    # recovered from state afterwards.
    assert comprehension.commitments(db, "u1") == []
    assert comprehension.get(db, "u1", "t1").commitment_met_at is not None


def test_a_thread_with_no_promise_is_not_a_commitment():
    db = _session()
    _read(db, "t1", your_commitment="", commitment_quote="")
    assert comprehension.commitments(db, "u1") == []


def test_commitments_are_user_scoped():
    db = _session()
    _read(db, "t1")
    assert comprehension.commitments(db, "u2") == []


# ── who spoke last is not who owes ──────────────────────────────────────────
# The single most valuable thing reading the mail buys. The ledger derives the
# ball mechanically from whose message was last, which is wrong precisely when
# it matters: you answer with a promise, so you spoke last, so the app tells you
# to chase the customer YOU owe.

def _thread(db, tid, *, last="out"):
    """Two messages; `last` decides who spoke last."""
    _msg(db, tid, direction="in", days=5)
    if last == "out":
        _msg(db, tid, direction="out", sender="me@ourfirm.com", days=4)
    return models.FollowUp


def test_a_promise_you_made_means_YOU_owe_even_though_you_spoke_last(bodies, monkeypatch):
    from backend.services import followups as fu_service

    db = _session()
    _thread(db, "t1", last="out")
    _stub_llm(monkeypatch, {
        "their_ask": {"text": "a discount", "quote": "can you do better than list"},
        "your_commitment": {"text": "revised pricing",
                            "quote": "I'll get you revised pricing by Friday", "due": "Friday"},
        "blocked_on": "you",
    })
    comprehension.read(db, "u1", "t1")
    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).filter_by(thread_id="t1").first()
    # Without the override this is awaiting_them — "chase Dana", about a thread
    # where you are the one who owes her something.
    assert fu.ball == "you"
    assert fu.state == fu_service.AWAITING_YOU


def test_answering_their_question_hands_the_ball_back_to_them(bodies, monkeypatch):
    from backend.services import followups as fu_service

    db = _session()
    _msg(db, "t1", direction="in", days=4)  # they spoke last by the ledger
    _stub_llm(monkeypatch, {
        "their_ask": {"text": "the delivery date", "quote": "can you do better than list"},
        "blocked_on": "them",
    })
    comprehension.read(db, "u1", "t1")
    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).filter_by(thread_id="t1").first()
    assert fu.ball == "them"


def test_a_finished_conversation_leaves_the_worklist(bodies, monkeypatch):
    from backend.services import followups as fu_service, worklist

    db = _session()
    _thread(db, "t1", last="out")
    _stub_llm(monkeypatch, {
        "their_ask": {"text": "", "quote": ""},
        "your_commitment": {"text": "", "quote": "", "due": ""},
        "blocked_on": "nobody",
    })
    comprehension.read(db, "u1", "t1")
    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).filter_by(thread_id="t1").first()
    assert fu.state == fu_service.DONE
    assert fu.closed_reason == "nothing_outstanding"
    assert worklist.build(db, "u1")["total"] == 0


def test_an_unmet_promise_keeps_a_thread_open_even_when_nobody_is_blocked(bodies, monkeypatch):
    from backend.services import followups as fu_service

    db = _session()
    _thread(db, "t1", last="out")
    # A model saying "nobody" while the user still owes something must NOT close
    # it — that would quietly drop the promise off the list.
    _stub_llm(monkeypatch, {
        "their_ask": {"text": "", "quote": ""},
        "your_commitment": {"text": "the deck",
                            "quote": "I'll get you revised pricing by Friday", "due": ""},
        "blocked_on": "nobody",
    })
    comprehension.read(db, "u1", "t1")
    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).filter_by(thread_id="t1").first()
    assert fu.state in fu_service.OPEN_STATES


def test_a_customer_writing_from_hello_at_is_tracked_like_any_other(bodies, monkeypatch):
    """hello@ / info@ / team@ / help@ are small businesses' MAIN addresses.

    They sit in `_BULK_LOCALPARTS`, which was being used in seven places to
    decide whether a relationship exists at all — so a real customer writing
    from hello@ had no follow-up tracked, was never nudged, and was classified
    as bulk. A newsletter lingering for a week is a far smaller error than a
    paying customer being invisible.
    """
    from backend.services import followups as fu_service

    db = _session()
    m = _msg(db, "t1", sender="Mia Fern <hello@fernvalley.shop>")
    m.counterparty_email = "hello@fernvalley.shop"
    db.commit()

    _stub_llm(monkeypatch, {
        "their_ask": {"text": "wholesale terms", "quote": "can you do better than list"},
        "blocked_on": "you",
    })
    comprehension.read(db, "u1", "t1")
    fu_service.sync_followups(db, "u1")

    fu = db.query(models.FollowUp).filter_by(thread_id="t1").first()
    assert fu is not None, "a real customer at hello@ must get a follow-up"
    assert fu.ask_summary == "wholesale terms"


def test_a_no_reply_address_is_still_never_tracked(bodies, monkeypatch):
    from backend.services import followups as fu_service

    db = _session()
    m = _msg(db, "t1", sender="Updates <no-reply@news.example>")
    m.counterparty_email = "no-reply@news.example"
    db.commit()

    fu_service.sync_followups(db, "u1")

    assert db.query(models.FollowUp).filter_by(thread_id="t1").first() is None


# ── typography: the difference between working and silently doing nothing ───
#
# The quote check is what stops a model's judgement reaching the screen unless
# the words are really in the mail. It compares text, so it is at the mercy of
# punctuation: mail clients emit curly quotes and em dashes, and a model quoting
# that mail back types the straight ASCII equivalents almost every time. Before
# folding, three of four plausible model quotes were rejected over punctuation
# alone — every judgement would have vanished, for a reason nobody could have
# guessed from the screen. These are the regression tests for that.

_BODY = "Hi — we can’t sign off until you confirm the “revised pricing” before the 12th."


def test_a_straight_apostrophe_matches_a_curly_one():
    assert comprehension._quoted("we can't sign off until you confirm", comprehension._norm(_BODY))


def test_straight_double_quotes_match_curly_ones():
    assert comprehension._quoted('the "revised pricing" before the 12th', comprehension._norm(_BODY))


def test_a_hyphen_matches_an_em_dash():
    assert comprehension._quoted("Hi - we can't sign off", comprehension._norm(_BODY))


def test_a_non_breaking_space_matches_a_normal_one():
    body = comprehension._norm("payment of £2,400 is due")
    assert comprehension._quoted("payment of £2,400 is due", body)


def test_folding_punctuation_does_not_let_a_fabrication_through():
    """The whole point. Loosening the comparison must not loosen the guarantee."""
    assert not comprehension._quoted("we will ship it on Tuesday", comprehension._norm(_BODY))
    assert not comprehension._quoted("confirm the revised pricing by Friday", comprehension._norm(_BODY))


def test_a_quote_from_a_different_thread_is_still_rejected():
    assert not comprehension._quoted(
        "the warehouse flagged a damaged pallet", comprehension._norm(_BODY)
    )
