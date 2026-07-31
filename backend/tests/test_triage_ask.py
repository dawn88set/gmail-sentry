"""Ask + deadline extraction (backend/services/triage.py)."""
from datetime import datetime, timedelta

from backend.services import triage


def test_heuristic_extracts_the_ask():
    out = triage.heuristic_classify([], "Dana <d@x.com>", "Q3 quote",
                                    "Hi — can you send the revised numbers? Thanks.")
    assert "can you send the revised numbers" in out["ask"].lower()
    assert out["ask_confidence"] > 0
    assert out["expects_reply"] is True


def test_heuristic_declines_to_invent_an_ask():
    """A wrong one-liner on a follow-up row is worse than none — the user acts
    on it."""
    out = triage.heuristic_classify([], "News <n@x.com>", "Weekly roundup",
                                    "Here is what happened this week in tech.")
    assert out["ask"] == ""
    assert out["ask_confidence"] == 0


def test_heuristic_finds_an_explicit_deadline():
    out = triage.heuristic_classify([], "Dana <d@x.com>", "Contract",
                                    "Please sign by Friday.")
    assert out["due"].lower() == "friday"


def test_resolve_due_handles_the_common_phrasings():
    now = datetime(2026, 7, 1, 9, 0, 0)  # a Wednesday
    assert triage.resolve_due("today", now=now).date() == now.date()
    assert triage.resolve_due("tomorrow", now=now).date() == (now + timedelta(days=1)).date()
    assert triage.resolve_due("friday", now=now).weekday() == 4
    assert triage.resolve_due("2026-08-15", now=now).date() == datetime(2026, 8, 15).date()


def test_resolve_due_declines_ambiguous_dates():
    """3/4 is March 4th or April 3rd depending on locale. A fabricated deadline
    makes the app chase people early, which users don't forgive."""
    assert triage.resolve_due("3/4") is None
    assert triage.resolve_due("") is None
    assert triage.resolve_due("whenever") is None


def test_ask_is_trimmed_to_one_line():
    long = "Can you " + ("please review this extremely long request " * 8)
    out = triage.heuristic_classify([], "a@x.com", "s", long)
    assert len(out["ask"]) <= 120 and "\n" not in out["ask"]
