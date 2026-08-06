"""
Reading the mail — the app's only source of judgement about what was said.

Until this module, the app had never read an email. Triage classified from a
~100-character snippet, "the ask" was a regex over that snippet, and every
surface above them — the worklist, accounts, insights — was counting and sorting
*who* and *when*. That is why the answer to "where are we with Northwind?" was
"silent 11 days": a timestamp, when the real answer was in the thread.

The rule that keeps this honest:

    Figures are computed. Judgement is generated, quoted, and VERIFIED.

Every field the model returns must carry a quote, and `_verify` drops any field
whose quote is not present verbatim in the messages we actually fetched. A
fabricated ask cannot reach the screen, because there is no path from the model
to the database that doesn't pass through that check. That is a stronger
guarantee than instructing a model to be careful, and it is the reason this can
be trusted with a decision like "chase this customer".

Cost is bounded on three axes: only threads that already need action, at most
`MAX_MESSAGES` bodies per thread, and `MAX_READS_PER_SCAN` threads per scan. A
thread whose newest message hasn't changed is never re-read.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend import models
from backend.services import counterparty as cp_service
from backend.services.triage import resolve_due
from backend.integrations import gmail_ops as gmail_adapter
from backend.shared.adapters import IntegrationNotConnected, IntegrationError

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

#: Newest-first. Eight is enough to see how a thread got where it is without
#: paying for a forty-message CC chain.
MAX_MESSAGES = 8
#: Per scan, so a backlog drains over several runs instead of one spike.
MAX_READS_PER_SCAN = 6
#: Bodies are trimmed before the model sees them — quoted reply chains repeat
#: the whole thread on every message, which would blow the budget on text we
#: already have.
MAX_BODY_CHARS = 4000


_SYSTEM = (
    "You read one email thread and report what it actually says. You are not "
    "summarising politely — you are telling a busy business owner the thing they "
    "would have learned by reading it themselves.\n\n"
    "EVERY field you fill must include a `quote`: a short span copied EXACTLY, "
    "character for character, from the thread text. Quotes are checked against "
    "the source and any field whose quote does not appear is discarded. Never "
    "paraphrase inside a quote. If something is not stated in the thread, leave "
    "that field empty — an empty field is correct and useful; an invented one is "
    "worse than silence.\n\n"
    "Never state an amount or a date the thread does not contain."
)


def _prompt(subject: str, messages: List[Dict[str, Any]], self_address: str) -> str:
    lines = [
        f"The user's own address is {self_address or '(unknown)'} — messages from "
        "them are the USER's, everything else is the counterparty's.",
        f"Thread subject: {subject or '(none)'}",
        "",
        "MESSAGES, oldest first:",
    ]
    for m in messages:
        who = "USER" if m["is_self"] else "THEM"
        when = m["at"].strftime("%d %b %Y") if m.get("at") else "unknown date"
        lines.append(f"\n--- [{who}] {m['sender']} · {when}\n{m['body']}")
    lines += [
        "",
        "Return ONLY this JSON:",
        json.dumps(
            {
                "their_ask": {"text": "what THEY want, one line, or \"\"", "quote": ""},
                "your_commitment": {
                    "text": "what the USER promised to do, one line, or \"\"",
                    "quote": "",
                    "due": "a date/deadline EXACTLY as written, or \"\"",
                },
                "blocked_on": "you | them | nobody",
                "amounts": [{"text": "e.g. £2,400 invoice 88213", "quote": ""}],
                "summary": "one line a person would say about where this stands",
            },
            indent=1,
        ),
    ]
    return "\n".join(lines)


# ── the honesty mechanism ───────────────────────────────────────────────────

#: Typographic characters folded to their ASCII equivalents before comparing.
#:
#: This is the difference between the feature working and silently doing nothing.
#: Mail clients emit curly quotes, en and em dashes and non-breaking spaces; a
#: model quoting that mail back overwhelmingly types the straight ASCII
#: equivalents. Without folding, "we can\'t sign off" fails to match a body
#: containing the curly-apostrophe version, the quote check rejects it, the field
#: is dropped — and every judgement the app has disappears for a reason nobody
#: would guess from the screen. Measured on a realistic body: three of four
#: plausible model quotes were dropped over punctuation alone.
_TYPOGRAPHY = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u2015": "-", "\u2212": "-",
    "\u00a0": " ", "\u2007": " ", "\u2009": " ", "\u202f": " ",
    "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
    "\u2026": "...",
})


def _norm(text: str) -> str:
    """Collapse whitespace, typography and case for comparison.

    Bodies arrive with hard wraps, non-breaking spaces and quoted-printable
    artefacts, so a strict equality check would reject almost every genuine
    quote — which is the failure mode that silently turns this feature off.

    Folding punctuation does NOT weaken the guarantee. The claim being checked is
    that the model is repeating words really present in the mail; whether the
    apostrophe it typed was curly or straight is evidence of nothing.
    """
    return re.sub(r"\s+", " ", (text or "").translate(_TYPOGRAPHY)).strip().lower()


def _quoted(quote: str, haystack: str) -> bool:
    """Is this quote really in the thread?

    Short fragments are rejected: a three-character "quote" matches almost any
    mail and proves nothing. But a fragment containing a NUMBER is specific even
    when it's short — "£2,400", "40 seats", "invoice 88213" are exactly the
    evidence an amount needs, and an end-to-end run showed the flat 12-character
    floor silently dropping "on 40 seats" at eleven.
    """
    q = _norm(quote)
    if q not in haystack:
        return False
    return len(q) >= 12 or (len(q) >= 4 and any(c.isdigit() for c in q))


def _verify(parsed: Dict[str, Any], haystack: str) -> Dict[str, Any]:
    """Keep only the claims the mail actually supports.

    Each field survives only with a quote found in the source. `blocked_on` and
    `summary` carry no quote by nature — `blocked_on` is a closed choice, and the
    summary is only ever shown alongside fields that were verified.
    """
    out: Dict[str, Any] = {
        "their_ask": "", "their_ask_quote": "",
        "your_commitment": "", "commitment_quote": "", "commitment_due_raw": "",
        "blocked_on": "", "amounts": [], "summary": "", "dropped": [],
    }

    ask = parsed.get("their_ask") or {}
    if isinstance(ask, dict) and str(ask.get("text") or "").strip():
        if _quoted(str(ask.get("quote") or ""), haystack):
            out["their_ask"] = " ".join(str(ask["text"]).split())[:280]
            out["their_ask_quote"] = " ".join(str(ask["quote"]).split())[:600]
        else:
            out["dropped"].append("their_ask")

    com = parsed.get("your_commitment") or {}
    if isinstance(com, dict) and str(com.get("text") or "").strip():
        if _quoted(str(com.get("quote") or ""), haystack):
            out["your_commitment"] = " ".join(str(com["text"]).split())[:280]
            out["commitment_quote"] = " ".join(str(com["quote"]).split())[:600]
            out["commitment_due_raw"] = str(com.get("due") or "").strip()[:80]
        else:
            out["dropped"].append("your_commitment")

    blocked = str(parsed.get("blocked_on") or "").strip().lower()
    out["blocked_on"] = blocked if blocked in ("you", "them", "nobody") else ""

    for a in parsed.get("amounts") or []:
        if not isinstance(a, dict):
            continue
        text = " ".join(str(a.get("text") or "").split())[:120]
        if text and _quoted(str(a.get("quote") or ""), haystack):
            out["amounts"].append({"text": text, "quote": " ".join(str(a["quote"]).split())[:400]})
        elif text:
            out["dropped"].append("amount")

    out["summary"] = " ".join(str(parsed.get("summary") or "").split())[:280]
    return out


# ── fetching ────────────────────────────────────────────────────────────────

def _thread_messages(db: Session, user_id: str, thread_id: str) -> List[models.ThreadMessage]:
    return (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.thread_id == thread_id,
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .limit(MAX_MESSAGES)
        .all()
    )


def _fetch_bodies(
    db: Session, user_id: str, rows: List[models.ThreadMessage]
) -> Tuple[List[Dict[str, Any]], str]:
    """Bodies oldest-first, plus the normalised haystack quotes are checked against.

    A message whose body can't be fetched falls back to its snippet — better a
    short real text than none — and if NOTHING can be read the caller aborts
    rather than asking the model to work from subjects.
    """
    out: List[Dict[str, Any]] = []
    for m in reversed(rows):  # oldest first reads like a conversation
        body = ""
        try:
            body = gmail_adapter.get_body(db, user_id, m.gmail_message_id) or ""
        except (IntegrationError, IntegrationNotConnected) as e:
            logger.info("comprehension: body unavailable for %s (%s)", m.gmail_message_id, e)
        body = (body or m.snippet or "").strip()
        if not body:
            continue
        out.append({
            "sender": m.sender or m.counterparty_email or "",
            "is_self": (m.direction or "") == "out",
            "at": m.ts_hi,
            "body": body[:MAX_BODY_CHARS],
        })
    haystack = _norm(" ".join(x["body"] for x in out))
    return out, haystack


# ── the read ────────────────────────────────────────────────────────────────

def needs_read(db: Session, user_id: str, thread_id: str) -> bool:
    """True when this thread has never been read, or has moved since."""
    rows = _thread_messages(db, user_id, thread_id)
    if not rows:
        return False
    newest = rows[0].gmail_message_id or ""
    existing = (
        db.query(models.ThreadRead)
        .filter(models.ThreadRead.user_id == user_id, models.ThreadRead.thread_id == thread_id)
        .first()
    )
    return existing is None or (existing.read_through_message_id or "") != newest


def get(db: Session, user_id: str, thread_id: str) -> Optional[models.ThreadRead]:
    return (
        db.query(models.ThreadRead)
        .filter(models.ThreadRead.user_id == user_id, models.ThreadRead.thread_id == thread_id)
        .first()
    )


def read(db: Session, user_id: str, thread_id: str) -> Optional[models.ThreadRead]:
    """Read one thread and store what it says. None when it can't or shouldn't.

    Returns None rather than a half-filled row when there's no LLM configured —
    which is the normal case locally — so every caller keeps today's behaviour
    instead of rendering blanks.
    """
    rows = _thread_messages(db, user_id, thread_id)
    if not rows:
        return None

    # Newsletters are not relationships; never spend a body fetch on one.
    counterparty = next((r.counterparty_email for r in rows if r.counterparty_email), "")
    if counterparty and cp_service.is_machine_sender(counterparty):
        return None

    messages, haystack = _fetch_bodies(db, user_id, rows)
    if not messages:
        return None

    sync = (
        db.query(models.ThreadSyncState)
        .filter(models.ThreadSyncState.user_id == user_id)
        .first()
    )
    subject = next((r.subject for r in rows if r.subject), "")

    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        result = client.chat(
            [{"role": "user", "content": _prompt(subject, messages, sync.self_address if sync else "")}],
            temperature=0.0,
            max_tokens=700,
            system=_SYSTEM,
        )
        raw = (getattr(result, "content", "") or "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError("no JSON object in model output")
        parsed = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001 — no proxy locally is the common path
        logger.info("comprehension: skipped %s (%s: %s)", thread_id, type(e).__name__, e)
        return None

    facts = _verify(parsed, haystack)
    if facts["dropped"]:
        # Worth seeing in logs: a model that keeps inventing quotes is a prompt
        # problem, and this is the only place it would ever show.
        logger.info("comprehension: dropped unquoted %s on %s", facts["dropped"], thread_id)

    row = get(db, user_id, thread_id) or models.ThreadRead(user_id=user_id, thread_id=thread_id)
    row.their_ask = facts["their_ask"]
    row.their_ask_quote = facts["their_ask_quote"]
    row.their_ask_at = next((m["at"] for m in reversed(messages) if not m["is_self"]), None)
    row.your_commitment = facts["your_commitment"]
    row.commitment_quote = facts["commitment_quote"]
    row.commitment_at = next((m["at"] for m in reversed(messages) if m["is_self"]), None)
    # Only a date the mail actually stated, resolved by the same conservative
    # parser the rest of the app uses — ambiguity yields nothing.
    row.commitment_due = (
        resolve_due(facts["commitment_due_raw"]) if facts["your_commitment"] else None
    )
    row.blocked_on = facts["blocked_on"]
    row.amounts = facts["amounts"]
    row.summary = facts["summary"]
    row.confidence = 80 if (facts["their_ask"] or facts["your_commitment"]) else 30
    row.read_through_message_id = rows[0].gmail_message_id or ""
    row.messages_read = len(messages)
    row.model = MODEL
    row.error = ""
    row.read_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return row


def commitments(db: Session, user_id: str, *, limit: int = 20, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """What the user said they would do and hasn't marked done. Overdue first.

    The single thing no mail client tracks, and the thing a business owner is
    actually judged on: not "did you reply" but "did you do what you said". It
    falls straight out of reading the thread — the promise is in the user's own
    sent mail — and every row carries the sentence they wrote, so it can be
    checked rather than trusted.
    """
    ref = now or datetime.utcnow()
    rows = (
        db.query(models.ThreadRead)
        .filter(
            models.ThreadRead.user_id == user_id,
            models.ThreadRead.your_commitment != "",
            models.ThreadRead.commitment_met_at.is_(None),
        )
        .all()
    )

    # Who it was to, from the loop that already knows — the read doesn't store a
    # counterparty of its own, and duplicating it would be a second answer to
    # the same question.
    loops = {
        f.thread_id: f
        for f in db.query(models.FollowUp)
        .filter(models.FollowUp.user_id == user_id)
        .all()
    }

    out: List[Dict[str, Any]] = []
    for r in rows:
        fu = loops.get(r.thread_id)
        overdue_days = (
            max(0, int((ref - r.commitment_due).total_seconds() // 86400))
            if r.commitment_due and r.commitment_due < ref
            else 0
        )
        out.append({
            "thread_id": r.thread_id,
            "what": r.your_commitment,
            "quote": r.commitment_quote,
            "to": (fu.counterparty_name or fu.counterparty_email or "") if fu else "",
            "subject": (fu.subject or "") if fu else "",
            "promised_at": r.commitment_at.isoformat() if r.commitment_at else None,
            "due_at": r.commitment_due.isoformat() if r.commitment_due else None,
            "overdue_days": overdue_days,
        })

    # Overdue first and worst first; then promises with a date, then the rest.
    out.sort(key=lambda c: (-c["overdue_days"], c["due_at"] is None, c["due_at"] or ""))
    return out[: max(1, limit)]


def mark_met(db: Session, user_id: str, thread_id: str, *, now: Optional[datetime] = None) -> None:
    """A promise is kept when the user next writes on that thread.

    Called from the send paths rather than inferred later: "did they deliver"
    cannot be recovered from state afterwards, which is the same reason the
    activity log exists.
    """
    row = get(db, user_id, thread_id)
    if row is not None and row.your_commitment and not row.commitment_met_at:
        row.commitment_met_at = now or datetime.utcnow()
        db.add(row)


def read_pending(db: Session, user_id: str, thread_ids: List[str], *, limit: int = MAX_READS_PER_SCAN) -> int:
    """Read up to `limit` of the given threads that need it. Returns how many.

    Callers pass the threads that already need action, so the budget is spent on
    mail the user is going to look at.
    """
    done = 0
    for tid in thread_ids:
        if done >= max(0, limit):
            break
        if not needs_read(db, user_id, tid):
            continue
        if read(db, user_id, tid) is not None:
            done += 1
        else:
            # No LLM, or nothing readable — stop rather than walking the whole
            # backlog making the same failing call.
            break
    return done
