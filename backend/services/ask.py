"""
Ask — one plain-language way into everything the app already knows.

The app holds a great deal that is only reachable by knowing which screen to
open: who has gone quiet, what an account owes, how fast you answer a given
customer, what was filed last week. A business owner does not think in screens.
They think "where are we with Northwind?" and "who's waiting on me?" — and every
answer to those is already in this database.

So this is a router, not a chatbot. The model's only job is to turn a sentence
into a structured intent; every number in the reply then comes from a real query.
That ordering matters: a model asked to *summarise* mail will happily invent a
figure, and one invented number makes the true ones worthless. Here it can pick
the wrong intent — visibly, and the user just rephrases — but it cannot make up
a fact.

Anything that CHANGES something comes back as a `proposal` instead of being
done: the rule it would create, the mail it would affect, and a count. The app's
whole lifecycle is draft → approve → act, and an assistant that quietly
reorganised a real mailbox on a misread instruction would be the one thing users
never forgive.

Degrades honestly with no LLM configured (local dev): keyword routing handles the
common shapes, and anything it can't place says so rather than guessing.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend import models
from backend.services import accounts as accounts_service
from backend.services import counterparty as cp_service
from backend.services import followups as followups_service
from backend.services import insights as insights_service
from backend.services import worklist as worklist_service

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

#: What a question can resolve to. Small on purpose — every one of these is a
#: real query with a real answer, and a router with twenty intents picks wrong
#: far more often than one with five.
NOW = "now"                 # "what needs me", "what's going on"
WHO = "who"                 # "where are we with Northwind", "what about Dana"
FIND = "find"               # "emails about the renewal", "anything from invoices"
QUIET = "quiet"             # "who has gone quiet", "what's at risk"
BRIEF = "brief"             # "how did last week go" → a report you could paste
PREP = "prep"               # "prep me for my call with Dana" → a dossier
RULE = "rule"               # "always flag anything from my lawyer"  → proposal
FILE = "file"               # "file supplier mail into Ops"          → proposal
PROMISED = "promised"       # "what did I promise" / "what am I late on"
SCHEDULE = "schedule"       # "check my mail every hour"             → proposal
NOTIFY = "notify"           # "only ping me about urgent"            → proposal
UNKNOWN = "unknown"

_INTENTS = (NOW, WHO, FIND, QUIET, BRIEF, PREP, PROMISED, RULE, FILE, SCHEDULE, NOTIFY)

#: Cadences the app can actually honour. Five minutes is the floor because the
#: platform's own trigger fires on that interval and the app only runs when it
#: does — offering "every minute" would be a promise it cannot keep.
_CADENCES = (5, 15, 30, 60, 180, 720, 1440)


def _nearest_cadence(minutes: int) -> int:
    return min(_CADENCES, key=lambda c: (abs(c - minutes), c))


def _parse_every(text: str) -> Optional[int]:
    """Minutes from "every 30 minutes" / "hourly" / "twice a day" / "every 2h"."""
    q = (text or "").lower()
    if re.search(r"\b(hourly|every hour|once an hour)\b", q):
        return 60
    if re.search(r"\btwice a day\b", q):
        return 720
    if re.search(r"\b(daily|once a day|every day)\b", q):
        return 1440
    m = re.search(r"\bevery\s+(?:(\d+)\s*)?(minute|min|hour|hr|h|day)s?\b", q)
    if m:
        n = int(m.group(1) or 1)
        unit = m.group(2)
        if unit.startswith(("minute", "min")):
            return n
        if unit.startswith(("hour", "hr", "h")):
            return n * 60
        return n * 1440
    return None


# ── interpreting the question ───────────────────────────────────────────────

_ROUTER_SYSTEM = (
    "You route a question about someone's email into ONE intent. You never answer "
    "the question and never invent facts — a separate system does the lookup.\n"
    "Intents:\n"
    "  now   — what needs me / what should I do / what's going on right now\n"
    "  who   — about a specific person or company (subject = their name or email)\n"
    "  find  — searching for mail on a topic (subject = the search words)\n"
    "  quiet — who has gone quiet / what is at risk / who hasn't replied\n"
    "  brief — how did last week/month go / summarise / a report of what happened\n"
    "  prep  — prepare me for a call/meeting with someone (subject = who)\n"
    "  promised — what did I promise / commit to / what am I late on\n"
    "  rule  — asking to ALWAYS flag/alert on something (subject = what to flag)\n"
    "  file  — asking to file/label/organise mail (subject = what, target = folder)\n"
    "  schedule — how OFTEN to check the mailbox (subject = the phrase, e.g. 'every hour')\n"
    "  notify — which mail should ping them (subject = 'urgent' or 'all')\n"
    'Reply with ONLY JSON: {"intent": "...", "subject": "...", "target": "..."}. '
    'Use "" for anything not present.'
)


def _interpret_llm(question: str) -> Optional[Dict[str, str]]:
    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        result = client.chat(
            [{"role": "user", "content": question.strip()[:600]}],
            temperature=0,
            max_tokens=120,
            system=_ROUTER_SYSTEM,
        )
        raw = (getattr(result, "content", "") or "").strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(raw[start : end + 1])
        intent = str(data.get("intent") or "").strip().lower()
        if intent not in _INTENTS:
            return None
        return {
            "intent": intent,
            "subject": str(data.get("subject") or "").strip()[:120],
            "target": str(data.get("target") or "").strip()[:60],
        }
    except Exception as e:  # noqa: BLE001 — routing is best-effort by design
        logger.info("ask: LLM routing unavailable (%s: %s)", type(e).__name__, e)
        return None


def _interpret_keywords(question: str) -> Dict[str, str]:
    """Deterministic fallback. Runs with no LLM at all (local dev, proxy down).

    Handles the shapes people actually type; anything else becomes `unknown`,
    which answers with what it CAN do rather than guessing wrong.
    """
    original = " ".join((question or "").split())
    q = original.lower()

    # Matched case-insensitively but sliced out of the ORIGINAL, so a folder
    # keeps the capitalisation the user typed — creating "ops" when they asked
    # for "Ops" makes a mess of a real mailbox's label list.
    m = re.search(r"\b(?:file|label|organi[sz]e)\b(.+?)\b(?:in|into|under)\b(.+)$", q)
    if m:
        return {
            "intent": FILE,
            "subject": original[m.start(1):m.end(1)].strip(" .,"),
            "target": original[m.start(2):m.end(2)].strip(" .,"),
        }
    if re.search(r"\b(check|scan|read|sync|look at)\b.*\b(every|hourly|twice a day|daily)\b", q) or (
        re.search(r"\b(every|hourly|twice a day)\b", q) and re.search(r"\b(mail|inbox|mailbox)\b", q)
    ):
        return {"intent": SCHEDULE, "subject": original, "target": ""}
    if re.search(r"\b(only|just)\b.*\b(urgent|important)\b.*\b(ping|notify|alert|tell)\b", q) or re.search(
        r"\b(ping|notify|alert|tell)\s+me\b.*\b(only|just)?\s*(about\s+)?(urgent|everything|all)\b", q
    ):
        return {"intent": NOTIFY, "subject": original, "target": ""}
    if re.search(r"\b(always|whenever|any time|every time)\b.*\b(flag|alert|urgent|tell me)\b", q):
        return {"intent": RULE, "subject": original, "target": ""}
    # No trailing \b: "promise"/"promised"/"commitment" all need to match, and
    # \bpromis\b matches none of them.
    if re.search(r"\bpromis|\bcommit|\bsaid i'?d\b|\blate on\b|\bbehind on\b|\bowe.*deliver", q):
        return {"intent": PROMISED, "subject": "", "target": ""}
    if re.search(r"\b(gone quiet|went quiet|at risk|going cold|hasn'?t replied|no reply|slipping)\b", q):
        return {"intent": QUIET, "subject": "", "target": ""}
    m = re.search(r"\b(?:prep|prepare|brief) me (?:for|on|about)?\s*(?:my |the )?(?:call|meeting|chat)?\s*(?:with\s+)?(.+)$", q)
    if m:
        return {"intent": PREP, "subject": original[m.start(1):m.end(1)].strip(" ?.,"), "target": ""}
    if re.search(r"\b(how did .* go|last week|this week|last month|summar|report|recap|how'?s it going)\b", q):
        return {"intent": BRIEF, "subject": original, "target": ""}
    m = re.search(r"\b(?:where are we with|what about|how about|status of|catch me up on)\s+(.+)$", q)
    if m:
        return {"intent": WHO, "subject": original[m.start(1):m.end(1)].strip(" ?.,"), "target": ""}
    m = re.search(r"\b(?:find|search|show me|anything)\b.*?\b(?:about|from|on|re)\s+(.+)$", q)
    if m:
        return {"intent": FIND, "subject": original[m.start(1):m.end(1)].strip(" ?.,"), "target": ""}
    if re.search(r"\b(what needs me|what should i|what'?s going on|today|right now|my day)\b", q):
        return {"intent": NOW, "subject": "", "target": ""}
    return {"intent": UNKNOWN, "subject": original, "target": ""}


def interpret(question: str) -> Dict[str, str]:
    return _interpret_llm(question) or _interpret_keywords(question)


# ── answering, from real rows only ──────────────────────────────────────────

def _block(text: str, *, strong: bool = False, muted: bool = False) -> Dict[str, Any]:
    return {"text": text, "strong": strong, "muted": muted}


#: Words that carry no search signal. "file invoice mail into Ops" means mail
#: ABOUT invoices — matching the literal phrase "invoice mail" finds nothing,
#: which then reports "nothing matches" for a rule that would in fact catch
#: dozens of messages. That understates a change's blast radius, which is worse
#: than being too broad.
_FILLER = {
    "mail", "email", "emails", "message", "messages", "anything", "everything",
    "stuff", "things", "thing", "all", "any", "the", "a", "an", "from", "about",
    "with", "for", "my", "our", "me", "to", "of", "and", "or", "in", "on", "into",
}


def _terms(text: str) -> List[str]:
    """The words worth searching for, longest first."""
    words = re.findall(r"[a-z0-9@.\-']{2,}", (text or "").lower())
    kept = [w for w in words if w not in _FILLER]
    return sorted(kept, key=len, reverse=True)[:4] or words[:1]


def _match_any(column, terms: List[str]):
    """A filter matching ANY term — someone naming two things means either."""
    return or_(*[func.lower(column).like(f"%{t}%") for t in terms]) if terms else None


def _thread_filter(user_id: str, terms: List[str]):
    subj = _match_any(models.ThreadMessage.subject, terms)
    send = _match_any(models.ThreadMessage.sender, terms)
    if subj is None:
        return models.ThreadMessage.user_id == user_id
    return or_(subj, send)


def _answer_now(db: Session, user_id: str) -> Dict[str, Any]:
    work = worklist_service.build(db, user_id, limit=6)
    accs = accounts_service.build(db, user_id)
    at_risk = [a for a in accs if a.chasing > 0]

    stats = [_stat(work["total"], "need you")]
    if work["overdue"]:
        stats.append(_stat(work["overdue"], "overdue", tone="warn"))
    if work.get("ready_to_send"):
        stats.append(_stat(work["ready_to_send"], "ready to send"))
    if at_risk:
        stats.append(_stat(len(at_risk), "going quiet", tone="warn"))

    lines = []
    for i in work["items"][:5]:
        who = i["who"] + (f" · {i['company']}" if i.get("company") and i["company"] != i["who"] else "")
        lines.append(_block(f"{i['headline']} — {who} · {i['due_label'] or i['age_label']}"))
    if at_risk:
        lines.append(_block(
            "Going quiet: " + ", ".join(f"{a.name} ({a.silent_days}d)" for a in at_risk[:4]),
            muted=True,
        ))
    if work["total"] == 0:
        lines.append(_block("Nobody is waiting on a reply, and no thread has gone quiet.", muted=True))
    return {"title": "Right now", "stats": stats, "lines": lines, "link": "/"}


def _find_counterparties(db: Session, user_id: str, subject: str) -> List[models.Counterparty]:
    """Match a person or company by name, address or domain.

    Deliberately generous — someone typing "northwind" should find
    ops@northwind.co without knowing the address.
    """
    term = (subject or "").strip().lower()
    if not term:
        return []
    like = f"%{term}%"
    return (
        db.query(models.Counterparty)
        .filter(
            models.Counterparty.user_id == user_id,
            or_(
                func.lower(models.Counterparty.display_name).like(like),
                func.lower(models.Counterparty.email).like(like),
                func.lower(models.Counterparty.domain).like(like),
                func.lower(models.Counterparty.crm_company).like(like),
            ),
        )
        .order_by(models.Counterparty.importance.desc())
        .limit(25)
        .all()
    )


def _answer_who(db: Session, user_id: str, subject: str) -> Dict[str, Any]:
    people = _find_counterparties(db, user_id, subject)
    if not people:
        return {
            "title": f"Nothing about “{subject}”",
            "lines": [_block("No contact or company matches that in the mail I've read.", muted=True)],
        }

    # Prefer the ACCOUNT the match belongs to — the question "where are we with
    # Northwind" is about the company, not whichever address matched first.
    keys = {accounts_service.account_key(c) for c in people}
    acc = next((a for a in accounts_service.build(db, user_id) if a.key in keys), None)

    if acc is None:
        c = people[0]
        return {
            "title": c.display_name or c.email,
            "lines": [
                _block(f"{c.email} · {accounts_service.REL_LABEL.get(c.relationship or '', 'Unclassified')}"),
                _block(f"{c.thread_count or 0} threads · you answer {c.your_reply_rate or 0}%", muted=True),
            ],
        }

    lines = [_block(
        f"{accounts_service.REL_LABEL.get(acc.relationship, 'Unclassified')}"
        f" · {len(acc.people)} {'person' if len(acc.people) == 1 else 'people'}"
        + (f" · last contact {acc.silent_days}d ago" if acc.silent_days is not None else ""),
        strong=True,
    )]
    if acc.headline:
        lines.append(_block(acc.headline))
    state = []
    if acc.you_owe:
        state.append(f"you owe {acc.you_owe}")
    if acc.chasing:
        state.append(f"{acc.chasing} gone quiet")
    if acc.open_threads:
        state.append(f"{acc.open_threads} open")
    lines.append(_block(" · ".join(state) if state else "Nothing outstanding", muted=True))
    if acc.your_median_reply_h:
        lines.append(_block(f"You reply to them in about {acc.your_median_reply_h}h", muted=True))
    for c in sorted(acc.people, key=lambda x: -(x.importance or 0))[:4]:
        lines.append(_block(f"{c.display_name or c.email} — answers {c.your_reply_rate or 0}%", muted=True))
    return {"title": acc.name, "lines": lines, "link": f"/accounts/{acc.key}"}


def _answer_find(db: Session, user_id: str, subject: str) -> Dict[str, Any]:
    """Search the ledger, not Gmail.

    Every message the app has read is already indexed locally, so this costs no
    broker call and works when Gmail is rate-limited. It searches what we
    actually hold — subject and sender — and says so rather than implying it
    searched message bodies.
    """
    term = (subject or "").strip()
    if not term:
        return {"title": "Search", "lines": [_block("Tell me what to look for.", muted=True)]}
    terms = _terms(term)
    rows = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            _thread_filter(user_id, terms),
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .limit(40)
        .all()
    )
    seen: Dict[str, models.ThreadMessage] = {}
    for r in rows:
        seen.setdefault(r.thread_id, r)
    hits = list(seen.values())[:8]
    if not hits:
        return {
            "title": f"Nothing matching “{term}”",
            "lines": [_block("I search the subjects and senders I've indexed, not message bodies.", muted=True)],
        }
    lines = [_block(f"{len(seen)} conversation{'' if len(seen) == 1 else 's'} mentioning “{term}”", strong=True)]
    for r in hits:
        who = cp_service._local_part(r.counterparty_email or "") or (r.sender or "")
        lines.append(_block(f"{r.subject or '(no subject)'} — {who}"))
    return {"title": "Found", "lines": lines}


def _answer_quiet(db: Session, user_id: str) -> Dict[str, Any]:
    risk = insights_service.at_risk(db, user_id, limit=8)
    threads = risk.get("threads", [])
    if not threads:
        return {"title": "Nothing has gone quiet", "lines": [
            _block("Every open thread has moved recently.", muted=True)]}
    lines = []
    for t in threads:
        lines.append(_block(f"{t['who']} — {t['subject'] or '(no subject)'} · silent {t['silent_days']}d"))
    return {"title": "At risk", "stats": [_stat(len(threads), "going quiet", tone="warn")],
            "lines": lines, "link": "/accounts"}


def _stat(value: Any, label: str, *, tone: str = "") -> Dict[str, Any]:
    """A headline figure. `tone` is 'warn' only when the number is bad news —
    colouring everything makes nothing stand out."""
    return {"value": str(value), "label": label, "tone": tone}


def _answer_brief(db: Session, user_id: str, question: str) -> Dict[str, Any]:
    """What actually happened, as a report someone could paste into a update.

    Sourced from the activity log rather than recomputed from current state, so
    this and the Activity feed can never disagree — and so it counts what was
    DONE rather than what happens to be outstanding now.
    """
    q = (question or "").lower()
    days = 30 if "month" in q else 7
    period = "the last 30 days" if days == 30 else "the last 7 days"

    from backend.services import activity as activity_service

    done = activity_service.summary(db, user_id, days=days)
    work = worklist_service.build(db, user_id, limit=1)
    accs = accounts_service.build(db, user_id)
    at_risk = [a for a in accs if a.chasing > 0]

    stats = [
        _stat(done.get("filed", 0), "filed"),
        _stat(done.get("flagged", 0), "flagged"),
        _stat(done.get("sent", 0), "replies sent"),
        _stat(work["total"], "still open"),
    ]
    if at_risk:
        stats.append(_stat(len(at_risk), "going quiet", tone="warn"))

    lines = []
    if done.get("went_quiet"):
        lines.append(_block(f"{done['went_quiet']} thread{'' if done['went_quiet'] == 1 else 's'} went quiet in {period}."))
    for a in at_risk[:3]:
        lines.append(_block(f"{a.name} — {a.headline or 'no reply'} · silent {a.silent_days}d"))
    if not any(done.values()) and work["total"] == 0:
        lines.append(_block(f"Nothing recorded in {period} yet.", muted=True))
    lines.append(_block(f"Counted from what actually happened in {period}, not estimated.", muted=True))

    return {"title": f"How {period.replace('the ', '')} went", "stats": stats, "lines": lines, "link": "/activity"}


def _answer_prep(db: Session, user_id: str, subject: str) -> Dict[str, Any]:
    """Everything about one counterparty, before you speak to them.

    The question behind "prep me for my call with Dana" is: what's outstanding,
    what did they last ask, and how have we been treating each other. All three
    are already stored; nobody had a way to see them together.
    """
    people = _find_counterparties(db, user_id, subject)
    if not people:
        return {
            "title": f"Nothing on “{subject}”",
            "lines": [_block("No contact matches that in the mail I've read.", muted=True)],
        }

    keys = {accounts_service.account_key(c) for c in people}
    acc = next((a for a in accounts_service.build(db, user_id) if a.key in keys), None)
    emails = {(c.email or "").lower() for c in people}

    loops = [
        f for f in followups_service.list_followups(db, user_id, state="open", limit=100)
        if (f.counterparty_email or "").lower() in emails
    ]
    best = max(people, key=lambda c: c.importance or 0)

    stats = [_stat(len(loops), "open with them")]
    if acc:
        if acc.you_owe:
            stats.append(_stat(acc.you_owe, "you owe", tone="warn"))
        if acc.silent_days is not None:
            stats.append(_stat(f"{acc.silent_days}d", "since contact"))
    if best.your_reply_rate:
        stats.append(_stat(f"{best.your_reply_rate}%", "you answer"))

    lines = []
    if acc:
        lines.append(_block(
            f"{accounts_service.REL_LABEL.get(acc.relationship, 'Unclassified')} · {acc.name}", strong=True))
    for f in loops[:5]:
        side = "waiting on you" if (f.ball or "") == "you" else "waiting on them"
        lines.append(_block(f"{f.ask_summary or f.subject or '(no subject)'} — {side}"))
    if not loops:
        lines.append(_block("Nothing open with them right now.", muted=True))
    if best.your_median_reply_h:
        lines.append(_block(
            f"You usually reply to them in about {best.your_median_reply_h}h"
            + (f"; they take about {best.their_median_reply_h}h" if best.their_median_reply_h else ""),
            muted=True,
        ))

    title = (best.display_name or best.email) if not acc else acc.name
    return {"title": f"Before you talk to {title}", "stats": stats, "lines": lines,
            "link": f"/accounts/{acc.key}" if acc else None}


# ── proposals: what it WOULD change ─────────────────────────────────────────

def _propose_rule(db: Session, user_id: str, subject: str) -> Dict[str, Any]:
    """A triage rule, described in the user's own words and NOT created.

    The count of affected mail is a real query, so the user is approving a
    change whose blast radius they can see.
    """
    text = (subject or "").strip()
    if not text:
        return {"title": "What should I flag?", "lines": [
            _block("Tell me what matters — “anything from my accountant”, say.", muted=True)]}
    affected = (
        db.query(func.count(models.ThreadMessage.id))
        .filter(
            models.ThreadMessage.user_id == user_id,
            _thread_filter(user_id, _terms(text)),
        )
        .scalar()
    ) or 0
    return {
        "title": "Flag this from now on",
        "lines": [
            _block(text, strong=True),
            _block(
                f"Matches {affected} message{'' if affected == 1 else 's'} in what I've read"
                if affected else "Nothing in the last 45 days matches yet — it will apply to new mail.",
                muted=True,
            ),
        ],
        "proposal": {
            "kind": "rule",
            "label": "Create rule",
            # `nl` because the user's sentence IS the rule — the triage model
            # judges each message against it, which handles nuance a keyword
            # match would miss.
            "payload": {"name": text[:60], "kind": "nl", "value": text, "tier": "urgent"},
        },
    }


def _propose_file(db: Session, user_id: str, subject: str, target: str) -> Dict[str, Any]:
    what = (subject or "").strip()
    folder = (target or "").strip()
    if not (what and folder):
        return {"title": "File what, where?", "lines": [
            _block("Try “file anything from suppliers into Ops”.", muted=True)]}
    affected = (
        db.query(func.count(func.distinct(models.ThreadMessage.thread_id)))
        .filter(
            models.ThreadMessage.user_id == user_id,
            _thread_filter(user_id, _terms(what)),
        )
        .scalar()
    ) or 0
    return {
        "title": f"File into {folder}",
        "lines": [
            _block(f"Mail matching “{what}”", strong=True),
            _block(
                f"Would apply to {affected} existing conversation{'' if affected == 1 else 's'}"
                if affected else "Nothing existing matches — it will apply to new mail.",
                muted=True,
            ),
        ],
        "proposal": {
            "kind": "label_rule",
            "label": f"File into {folder}",
            "payload": {
                "name": f"{what[:40]} → {folder}"[:60],
                # `sender` matches the address OR the display name, which is what
                # someone means by "from suppliers"; subject matching would miss
                # every message whose subject doesn't repeat the word.
                "match_type": "sender",
                "match_value": what[:80],
                "target_label": folder[:60],
                "archive_after": False,
            },
        },
    }


def _answer_promised(db: Session, user_id: str) -> Dict[str, Any]:
    """What the user said they'd do and hasn't done.

    Every line carries the sentence they actually wrote, so this is checkable
    rather than something to be taken on trust — which matters more here than
    anywhere else in the app, because acting on it means telling a customer
    something.
    """
    from backend.services import comprehension as comp

    items = comp.commitments(db, user_id, limit=8)
    if not items:
        return {
            "title": "Nothing outstanding",
            "lines": [_block(
                "I haven't found a promise you've not kept. I only see the threads I've read.",
                muted=True,
            )],
        }

    late = [c for c in items if c["overdue_days"] > 0]
    stats = [_stat(len(items), "promises open")]
    if late:
        stats.append(_stat(len(late), "past their date", tone="warn"))

    lines = []
    for c in items[:6]:
        who = c["to"] or "someone"
        when = f" · {c['overdue_days']}d late" if c["overdue_days"] else ""
        lines.append(_block(f"{c['what']} — {who}{when}", strong=bool(c["overdue_days"])))
        if c["quote"]:
            lines.append(_block(f"you wrote: “{c['quote'][:120]}”", muted=True))
    return {"title": "What you promised", "stats": stats, "lines": lines, "link": "/"}


def _said(minutes: int) -> str:
    """A cadence in the words someone would use for it.

    "every 12 hours" is technically right and nobody says it; if they asked for
    "twice a day" they should be agreeing to "twice a day".
    """
    if minutes == 1:
        return "every minute"
    if minutes < 60:
        return f"every {minutes} minutes"
    if minutes == 60:
        return "every hour"
    if minutes == 720:
        return "twice a day"
    if minutes < 1440:
        return f"every {minutes // 60} hours"
    if minutes == 1440:
        return "once a day"
    return f"every {minutes // 1440} days"


def _propose_schedule(db: Session, user_id: str, subject: str) -> Dict[str, Any]:
    """Change how often the mailbox is read.

    The one piece of scheduling this app genuinely owns. The daily report's time
    lives in Claritty's trigger settings, so asking for that gets told where it
    is rather than a proposal the app couldn't honour.
    """
    from backend.services.sentry import get_config

    cfg = get_config(db, user_id)
    current = int(getattr(cfg, "scan_interval_minutes", 5) or 5)

    wanted = _parse_every(subject)
    if wanted is None:
        return {
            "title": "How often should I check?",
            "lines": [
                _block(f"Right now: {_said(current)}.", strong=True),
                _block("Try “check my mail every hour” or “twice a day”.", muted=True),
            ],
        }

    picked = _nearest_cadence(wanted)

    # Any caveat about what was asked for versus what can be done belongs on
    # BOTH answers. Someone who asks for "every minute" and is told only
    # "already set" learns nothing about why it can't go faster.
    notes: List[Dict[str, Any]] = []
    if picked != wanted:
        notes.append(_block(
            f"You asked for {_said(wanted)}; {_said(picked)} is the nearest I can actually do.",
            muted=True,
        ))
    if picked == 5:
        notes.append(_block(
            "Five minutes is as fast as it goes — the platform's scan fires on that interval.",
            muted=True,
        ))
    notes.append(_block("You can still tap Scan any time for an immediate check.", muted=True))

    if picked == current:
        return {
            "title": "Already set",
            "lines": [_block(f"I'm already checking {_said(current)}.", strong=True)] + notes,
        }

    lines = [_block(f"{_said(current)}  →  {_said(picked)}", strong=True)] + notes

    return {
        "title": "Change how often I check",
        "lines": lines,
        "proposal": {
            "kind": "config",
            "label": f"Check {_said(picked)}",
            "payload": {"scan_interval_minutes": picked},
        },
    }


def _propose_notify(db: Session, user_id: str, subject: str) -> Dict[str, Any]:
    """Which mail is worth interrupting someone for."""
    from backend.services.sentry import get_config

    cfg = get_config(db, user_id)
    current = (cfg.notify_tier or "urgent").strip()
    q = (subject or "").lower()

    if re.search(r"\b(everything|all|both|more)\b", q):
        wanted, said = "needs_reply", "urgent mail and anything needing a reply"
    elif re.search(r"\b(urgent|important|only|less|quieter)\b", q):
        wanted, said = "urgent", "urgent mail only"
    else:
        return {
            "title": "What should ping you?",
            "lines": [
                _block(
                    "Currently: "
                    + ("urgent mail only" if current == "urgent" else "urgent mail and anything needing a reply"),
                    strong=True,
                ),
                _block("Try “only ping me about urgent” or “tell me about everything”.", muted=True),
            ],
        }

    if wanted == current:
        return {"title": "Already set", "lines": [_block(f"I already ping you about {said}.", strong=True)]}

    return {
        "title": "Change what pings you",
        "lines": [
            _block(f"Ping me about {said}", strong=True),
            _block("Everything else still appears in the app — this only changes what interrupts you.", muted=True),
        ],
        "proposal": {"kind": "config", "label": f"Ping me about {said}", "payload": {"notify_tier": wanted}},
    }


def _answer_unknown(question: str) -> Dict[str, Any]:
    return {
        "title": "I can answer things like",
        "lines": [
            _block("“what needs me today?”"),
            _block("“where are we with Northwind?”"),
            _block("“who has gone quiet?”"),
            _block("“find anything about the renewal”"),
            _block("“always flag anything from my accountant”"),
            _block("“file supplier mail into Ops”"),
            _block("“what did I promise?”"),
            _block("“check my mail every hour”"),
            _block("“only ping me about urgent”"),
            _block("I answer from the mail I've read — I don't guess.", muted=True),
        ],
    }


def ask(db: Session, user_id: str, question: str, *, context: Optional[str] = None) -> Dict[str, Any]:
    """Answer one question. Every figure below comes from a query, never a model.

    `context` is the screen the user asked from, so "what's going on here?" on an
    account page means that account rather than the whole mailbox.
    """
    q = (question or "").strip()
    if not q:
        return {"intent": UNKNOWN, **_answer_unknown(q)}

    routed = interpret(q)
    intent, subject, target = routed["intent"], routed.get("subject", ""), routed.get("target", "")

    # "what's happening here" on an account page is about THAT account.
    if intent in (NOW, UNKNOWN) and context and context.startswith("/accounts/"):
        key = context.split("/accounts/", 1)[1]
        if key:
            intent, subject = WHO, key.split(":", 1)[-1]

    if intent == NOW:
        out = _answer_now(db, user_id)
    elif intent == WHO:
        out = _answer_who(db, user_id, subject)
    elif intent == FIND:
        out = _answer_find(db, user_id, subject)
    elif intent == QUIET:
        out = _answer_quiet(db, user_id)
    elif intent == BRIEF:
        out = _answer_brief(db, user_id, subject)
    elif intent == PREP:
        out = _answer_prep(db, user_id, subject)
    elif intent == PROMISED:
        out = _answer_promised(db, user_id)
    elif intent == RULE:
        out = _propose_rule(db, user_id, subject)
    elif intent == FILE:
        out = _propose_file(db, user_id, subject, target)
    elif intent == SCHEDULE:
        out = _propose_schedule(db, user_id, subject)
    elif intent == NOTIFY:
        out = _propose_notify(db, user_id, subject)
    else:
        out = _answer_unknown(q)

    return {"intent": intent, **out}
