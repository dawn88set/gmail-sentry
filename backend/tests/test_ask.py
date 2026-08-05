"""
Ask — plain language over everything the app knows.

The risk with a natural-language surface is that it becomes a place where facts
get invented. The design that prevents it: the model only ROUTES a sentence to
an intent, and every figure in the reply comes from a real query. So these tests
hold two things above all —

  * a question that would CHANGE something returns a proposal and changes
    nothing until it's approved,
  * the numbers in an answer match the same numbers the screens show.

Routing here exercises the deterministic fallback, which is what runs with no
LLM configured. That path has to work on its own: local dev has no proxy, and a
proxy outage must degrade to something honest rather than to nothing.
"""
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.database import Base
from backend.services import ask, followups, worklist
from backend.services.ledger import utcnow


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _cp(db, email, name, **kw):
    d = dict(
        user_id="u1", email=email, display_name=name, domain=email.split("@")[-1],
        relationship="customer", importance=80, is_internal=False, muted=False,
        thread_count=4, your_reply_rate=90, your_median_reply_h=2,
        last_seen_at=utcnow() - timedelta(days=1),
    )
    d.update(kw)
    c = models.Counterparty(**d)
    db.add(c); db.commit()
    return c


def _loop(db, email, name, subject, **kw):
    d = dict(
        user_id="u1", thread_id=f"t-{subject[:8]}", state=followups.AWAITING_YOU, ball="you",
        counterparty_email=email, counterparty_name=name, subject=subject,
        ask_summary=subject, risk=50,
        created_at=utcnow() - timedelta(days=2), state_changed_at=utcnow() - timedelta(days=2),
        last_inbound_at=utcnow() - timedelta(days=2), last_activity_at=utcnow() - timedelta(days=2),
    )
    d.update(kw)
    f = models.FollowUp(**d)
    db.add(f); db.commit()
    return f


_msg_seq = [0]


def _msg(db, thread_id, subject, sender, **kw):
    # A counter, not a slice of the subject — two messages with similar subjects
    # would otherwise collide on the unique (user, message id) constraint.
    _msg_seq[0] += 1
    d = dict(
        user_id="u1", thread_id=thread_id, gmail_message_id=f"m{_msg_seq[0]}",
        direction="in", subject=subject, sender=sender,
        counterparty_email=sender, hydrated=True,
        # The ledger stores a time WINDOW per message (it recovers time from the
        # query bounds), and both ends are NOT NULL.
        ts_lo=utcnow() - timedelta(days=1, hours=6),
        ts_hi=utcnow() - timedelta(days=1),
    )
    d.update(kw)
    m = models.ThreadMessage(**d)
    db.add(m); db.commit()
    return m


# ── routing (the no-LLM fallback) ───────────────────────────────────────────

def test_the_fallback_routes_the_shapes_people_actually_type():
    cases = {
        "what needs me today?": ask.NOW,
        "where are we with Northwind": ask.WHO,
        "who has gone quiet?": ask.QUIET,
        "find anything about the renewal": ask.FIND,
        "always flag anything from my accountant": ask.RULE,
        "file supplier mail into Ops": ask.FILE,
    }
    for question, intent in cases.items():
        assert ask._interpret_keywords(question)["intent"] == intent, question


def test_a_folder_keeps_the_capitalisation_the_user_typed():
    # Creating "ops" when they asked for "Ops" makes a mess of a real label list.
    r = ask._interpret_keywords("file supplier mail into Ops/Suppliers")
    assert r["target"] == "Ops/Suppliers"


def test_an_unrecognised_question_says_what_it_can_do_rather_than_guessing():
    db = _session()
    out = ask.ask(db, "u1", "banana")
    assert out["intent"] == ask.UNKNOWN
    assert any("gone quiet" in l["text"] for l in out["lines"])


# ── changes are proposed, never applied ─────────────────────────────────────

def test_asking_for_a_rule_proposes_one_and_creates_nothing():
    db = _session()
    out = ask.ask(db, "u1", "always flag anything from my accountant")

    assert out["proposal"]["kind"] == "rule"
    # The whole safety property: nothing exists until the user taps approve.
    assert db.query(models.TriageRule).count() == 0


def test_asking_to_file_proposes_a_label_rule_and_creates_nothing():
    db = _session()
    out = ask.ask(db, "u1", "file supplier mail into Ops")

    assert out["proposal"]["kind"] == "label_rule"
    assert out["proposal"]["payload"]["target_label"] == "Ops"
    assert db.query(models.LabelRule).count() == 0


def test_a_proposal_counts_what_it_would_affect():
    db = _session()
    _msg(db, "t1", "Invoice 8821 from PackRite", "billing@packrite.com")
    _msg(db, "t2", "Invoice 8822 from PackRite", "billing@packrite.com")

    out = ask.ask(db, "u1", "file invoice mail into Ops")

    # Approving a change you can't see the blast radius of is not consent.
    assert "2" in " ".join(l["text"] for l in out["lines"])


# ── answers come from rows, not from a model ────────────────────────────────

def test_now_reports_the_same_total_the_worklist_shows():
    db = _session()
    _cp(db, "dana@northwind.co", "Dana Levi")
    _loop(db, "dana@northwind.co", "Dana Levi", "PO 4471 needs your signature")

    out = ask.ask(db, "u1", "what needs me today?")
    total = worklist.build(db, "u1", limit=100)["total"]

    assert str(total) in out["lines"][0]["text"]


def test_asking_about_a_company_answers_about_the_account():
    db = _session()
    _cp(db, "dana@northwind.co", "Dana Levi")
    _cp(db, "sam@northwind.co", "Sam Ortiz", importance=60)
    _loop(db, "dana@northwind.co", "Dana Levi", "Renewal quote for 2027")

    out = ask.ask(db, "u1", "where are we with northwind")

    assert out["title"] == "Northwind"
    assert out["link"] == "/accounts/d:northwind.co"
    # Both people, because the question is about the company not the address
    # that happened to match first.
    assert "2 people" in out["lines"][0]["text"]


def test_asking_about_someone_unknown_says_so_instead_of_inventing():
    db = _session()
    out = ask.ask(db, "u1", "where are we with Someone Who Never Wrote")
    assert "Nothing about" in out["title"]


def test_search_finds_by_subject_and_says_what_it_searched():
    db = _session()
    _msg(db, "t1", "Q3 renewal quote", "dana@northwind.co")

    out = ask.ask(db, "u1", "find anything about renewal")
    assert "Q3 renewal quote" in " ".join(l["text"] for l in out["lines"])

    miss = ask.ask(db, "u1", "find anything about kangaroos")
    # Honest about its own reach rather than implying it read every body.
    assert "not message bodies" in " ".join(l["text"] for l in miss["lines"])


def test_on_an_account_page_a_vague_question_means_that_account():
    db = _session()
    _cp(db, "dana@northwind.co", "Dana Levi")

    out = ask.ask(db, "u1", "what's going on", context="/accounts/d:northwind.co")

    assert out["title"] == "Northwind"


def test_answers_are_user_scoped():
    db = _session()
    _cp(db, "dana@northwind.co", "Dana Levi")

    assert "Nothing about" in ask.ask(db, "u2", "where are we with northwind")["title"]


# ── the report and the dossier ──────────────────────────────────────────────
# The two questions a business owner asks that no screen answered: "how did last
# week go?" (something to paste into a status update) and "prep me for my call
# with X" (what's outstanding, before you speak to them).

def test_a_brief_reports_what_happened_not_what_is_outstanding():
    db = _session()
    db.add(models.ActivityEvent(user_id="u1", kind="thread_filed", title="filed", count=6,
                                at=utcnow() - timedelta(days=2)))
    db.add(models.ActivityEvent(user_id="u1", kind="reply_sent", title="sent",
                                at=utcnow() - timedelta(days=1)))
    db.commit()

    out = ask.ask(db, "u1", "how did last week go?")

    labels = {s["label"]: s["value"] for s in out["stats"]}
    # Sourced from the activity log, so this and the Activity feed can never
    # disagree — and it counts what was DONE, not what happens to be open.
    assert labels["filed"] == "6"
    assert labels["replies sent"] == "1"
    assert any("not estimated" in l["text"] for l in out["lines"])


def test_a_brief_over_a_month_uses_a_month_window():
    db = _session()
    db.add(models.ActivityEvent(user_id="u1", kind="thread_filed", title="filed", count=3,
                                at=utcnow() - timedelta(days=20)))
    db.commit()

    week = ask.ask(db, "u1", "how did last week go?")
    month = ask.ask(db, "u1", "summarise last month")

    assert {s["label"]: s["value"] for s in week["stats"]}["filed"] == "0"
    assert {s["label"]: s["value"] for s in month["stats"]}["filed"] == "3"


def test_prep_gathers_what_is_open_with_that_person():
    db = _session()
    _cp(db, "dana@northwind.co", "Dana Levi")
    _loop(db, "dana@northwind.co", "Dana Levi", "Renewal quote for 2027")

    out = ask.ask(db, "u1", "prep me for my call with Dana")

    assert "Dana" in out["title"] or "Northwind" in out["title"]
    assert {s["label"] for s in out["stats"]} >= {"open with them"}
    assert any("Renewal quote" in l["text"] for l in out["lines"])


def test_prep_on_someone_unknown_says_so():
    db = _session()
    out = ask.ask(db, "u1", "prep me for my call with Nobody")
    assert "Nothing on" in out["title"]


def test_every_answer_that_shows_figures_labels_them():
    db = _session()
    _cp(db, "dana@northwind.co", "Dana Levi")
    _loop(db, "dana@northwind.co", "Dana Levi", "PO 4471")

    for q in ("what needs me today?", "how did last week go?", "prep me for my call with Dana"):
        for st in ask.ask(db, "u1", q).get("stats", []):
            # A bare number with no label is a number nobody can act on.
            assert st["label"].strip(), q
            assert st["value"].strip(), q


# ── scheduling and notification, by sentence ────────────────────────────────
# The only scheduling this app genuinely owns is how often it reads the mailbox.
# The daily report's time lives in Claritty's trigger settings, so nothing here
# should ever propose changing that — a control the app cannot honour is worse
# than no control.

def _cfg(db):
    from backend.services.sentry import get_config
    return get_config(db, "u1")


def test_cadence_phrases_people_actually_use():
    cases = {
        "check my mail every hour": 60,
        "scan my inbox every 30 minutes": 30,
        "read my mail twice a day": 720,
        "check my mail every 2 hours": 120,
        "check my inbox daily": 1440,
    }
    for q, mins in cases.items():
        assert ask._interpret_keywords(q)["intent"] == ask.SCHEDULE, q
        assert ask._parse_every(q) == mins, q


def test_a_cadence_change_is_proposed_not_applied():
    db = _session()
    before = _cfg(db).scan_interval_minutes

    out = ask.ask(db, "u1", "check my mail every hour")

    assert out["proposal"]["payload"] == {"scan_interval_minutes": 60}
    # Still unchanged until the user taps.
    assert _cfg(db).scan_interval_minutes == before


def test_an_impossible_cadence_explains_the_floor():
    db = _session()
    out = ask.ask(db, "u1", "check my mail every minute")

    # Five minutes is the floor — the platform's trigger fires on that interval
    # — and five is already the default, so there is nothing to change. The
    # caveat still has to be said: "already set" alone teaches nothing about
    # why it can't go faster.
    assert "proposal" not in out
    joined = " ".join(l["text"] for l in out["lines"])
    assert "nearest I can actually do" in joined
    assert "as fast as it goes" in joined


def test_a_slower_cadence_than_the_floor_is_a_real_proposal():
    db = _session()
    out = ask.ask(db, "u1", "check my mail every 20 minutes")

    # 20 isn't offered; 15 is the nearest, and that IS a change worth making.
    assert out["proposal"]["payload"] == {"scan_interval_minutes": 15}
    assert "nearest I can actually do" in " ".join(l["text"] for l in out["lines"])


def test_asking_for_the_cadence_already_set_proposes_nothing():
    db = _session()
    out = ask.ask(db, "u1", "check my mail every 5 minutes")

    assert "proposal" not in out
    assert "Already set" in out["title"]


def test_a_cadence_question_with_no_period_reports_the_current_one():
    db = _session()
    cfg = _cfg(db); cfg.scan_interval_minutes = 60; db.commit()

    out = ask._propose_schedule(db, "u1", "how often do you check my mail")

    assert "every hour" in " ".join(l["text"] for l in out["lines"])
    assert "proposal" not in out


def test_notification_preference_by_sentence():
    db = _session()

    quieter = ask.ask(db, "u1", "only ping me about urgent")
    assert "Already set" in quieter["title"]  # urgent is the default

    louder = ask.ask(db, "u1", "tell me about everything")
    assert louder["proposal"]["payload"] == {"notify_tier": "needs_reply"}
    assert _cfg(db).notify_tier == "urgent"  # unchanged until approved


def test_asking_what_you_promised_lists_it_with_your_own_words():
    db = _session()
    db.add(models.ThreadRead(
        user_id="u1", thread_id="t1", your_commitment="revised pricing",
        commitment_quote="I'll get you revised pricing by Friday",
        commitment_due=utcnow() - timedelta(days=3),
    ))
    db.add(models.FollowUp(
        user_id="u1", thread_id="t1", state=followups.AWAITING_YOU, ball="you",
        counterparty_email="dana@northwind.co", counterparty_name="Dana Levi",
        subject="Renewal", created_at=utcnow(), state_changed_at=utcnow(),
    ))
    db.commit()

    out = ask.ask(db, "u1", "what did I promise?")

    assert out["intent"] == ask.PROMISED
    joined = " ".join(l["text"] for l in out["lines"])
    assert "revised pricing" in joined
    assert "Dana Levi" in joined
    assert "3d late" in joined
    # The sentence they actually wrote, so the claim can be checked.
    assert "I'll get you revised pricing by Friday" in joined


def test_asking_what_you_promised_with_nothing_open_says_what_it_can_see():
    db = _session()
    out = ask.ask(db, "u1", "what am I late on?")
    joined = " ".join(l["text"] for l in out["lines"])
    # Honest about its own reach rather than implying a clean slate.
    assert "only see the threads I've read" in joined
