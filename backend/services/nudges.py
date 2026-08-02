"""
Nudges — chasing a thread that's gone quiet, in the user's own voice.

This is the only part of Gmail Sentry that puts a message in front of someone
the user did not just hear from. A reply answers an email that's on screen; a
nudge answers silence. That asymmetry is why this module is mostly guards.

## Nothing sends itself

There is no code path that mails a nudge without an explicit request. A nudge is
never pre-generated either — unlike a reply, which the scan can draft ahead of
time because the user is about to read the message it answers. A pre-drafted
nudge sitting in a list is one mis-tap away from an unrequested email to a
client, so drafting only happens when someone asks for it.

## The guards, and why each exists

**Backfill.** The ledger imports weeks of history on first run, and most old
silent threads are silent on purpose. Without this guard the first successful
sync would offer to chase forty people the user deliberately stopped replying
to. Loops discovered during (or just after) backfill are never eligible.

**Three per thread, ever.** After three unanswered nudges the answer is no. A
fourth is harassment sent on the user's behalf.

**48 hours between nudges to the same person.** Two threads going cold with the
same contact must not produce two chase emails in one morning.

**Five drafts per sweep.** A cap on how much work can be queued at once, so a
burst can't turn into a mailing.

**One live proposal per loop.** Generating again supersedes the old draft rather
than stacking, so "approve" is never ambiguous about which text goes out.

## Escalation

Attempt 1 is gentle, 2 is direct, 3 closes the loop gracefully — "I'll assume
this isn't a priority right now" — which is often the most useful message in the
sequence, because it ends the thread honestly instead of leaving it dangling.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend import models
from backend.services import activity
from backend.services import counterparty as cp_service
from backend.services import followups as fu_service
from backend.services import ledger
from backend.services.reply import DRAFT_FALLBACK_MARK, split_fallback, style_for

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

#: Hard ceiling on chases per thread. After three, the answer is no.
MAX_NUDGES_PER_THREAD = 3

#: Minimum gap between nudges to the SAME person, across all their threads.
MIN_HOURS_BETWEEN_NUDGES_PER_CONTACT = 48

#: How long after the ledger finishes importing history before its threads
#: become eligible. Old silence is usually deliberate.
BACKFILL_GRACE_HOURS = 1

#: Cap on drafts generated in one sweep.
MAX_DRAFTS_PER_SWEEP = 5

TONE_FOR_ATTEMPT = {1: "gentle", 2: "direct", 3: "closing"}

_TONE_BRIEF = {
    "gentle": (
        "Float the thread back up. Warm, brief, no pressure and no guilt — assume "
        "it simply got buried, because it usually did."
    ),
    "direct": (
        "Ask plainly for what's needed, restating the specific ask in one line and "
        "ending with a concrete question that's easy to answer. Still friendly, but "
        "don't bury the request."
    ),
    "closing": (
        "Close the loop gracefully. Say you'll assume this isn't a priority right "
        "now and that you're happy to pick it up whenever. No guilt, no final-notice "
        "tone — leave the door open. This should read as considerate, not annoyed."
    ),
}


def _first_name(name: str, email: str) -> str:
    n = (name or "").strip()
    if n:
        return n.split()[0]
    local = (email or "").split("@")[0]
    return local.split(".")[0].title() or "there"


def _reply_subject(subject: str) -> str:
    s = (subject or "").strip()
    if not s:
        return "Following up"
    return s if s.lower().startswith("re:") else f"Re: {s}"


# ── eligibility ─────────────────────────────────────────────────────────────

def why_not_eligible(
    db: Session,
    user_id: str,
    fu: models.FollowUp,
    *,
    now: Optional[datetime] = None,
) -> str:
    """"" if a nudge may be drafted, else a reason the UI can show verbatim.

    Returns prose rather than a boolean because every one of these has to be
    explained to the user. Silently disabling a button teaches people the app is
    broken; saying "you nudged 2 days ago, wait 2 more" teaches them it's careful.
    """
    ref = now or ledger.utcnow()

    if fu.state not in (fu_service.GOING_COLD, fu_service.AWAITING_THEM):
        return "This thread isn't waiting on them."
    if fu.ball != "them":
        return "The ball is in your court — reply instead of nudging."

    if int(fu.nudge_count or 0) >= MAX_NUDGES_PER_THREAD:
        return (
            f"You've nudged this thread {fu.nudge_count} times. "
            "After three, it's kinder to let it go."
        )

    cp = cp_service.get(db, user_id, fu.counterparty_email or "")
    if cp is not None and cp.muted:
        return "You've muted this contact."
    if fu.counterparty_email and cp_service.is_bulk_sender(fu.counterparty_email):
        return "That's an automated address — there's nobody to nudge."

    # Backfill guard. Loops that came out of the initial history import are not
    # eligible: old silence is usually deliberate, and offering to chase forty
    # abandoned threads is the worst thing this feature could do on day one.
    sync = (
        db.query(models.ThreadSyncState)
        .filter(models.ThreadSyncState.user_id == user_id)
        .first()
    )
    if sync is not None and not sync.backfill_done:
        return "Still reading your mail history — nudges open up once that's done."
    if sync is not None and sync.backfill_done_at and fu.created_at:
        if fu.created_at < sync.backfill_done_at + timedelta(hours=BACKFILL_GRACE_HOURS):
            return (
                "This thread came from your existing history. Nudging is for threads "
                "that go quiet from here on — you can still send one from Gmail."
            )

    # Per-contact cooldown, across every thread with this person.
    if fu.counterparty_email:
        recent = (
            db.query(models.FollowUp)
            .filter(
                models.FollowUp.user_id == user_id,
                models.FollowUp.counterparty_email == fu.counterparty_email,
                models.FollowUp.last_nudge_at.isnot(None),
            )
            .order_by(models.FollowUp.last_nudge_at.desc())
            .first()
        )
        if recent is not None and recent.last_nudge_at:
            hours = (ref - recent.last_nudge_at).total_seconds() / 3600.0
            if hours < MIN_HOURS_BETWEEN_NUDGES_PER_CONTACT:
                wait = int(round(MIN_HOURS_BETWEEN_NUDGES_PER_CONTACT - hours))
                who = recent.counterparty_name or fu.counterparty_email
                same = recent.id == fu.id
                where = "this thread" if same else "another thread"
                return (
                    f"You nudged {who} on {where} recently — "
                    f"give it about {wait} more hour{'s' if wait != 1 else ''}."
                )
    return ""


def open_proposal(db: Session, user_id: str, followup_id: str) -> Optional[models.Nudge]:
    return (
        db.query(models.Nudge)
        .filter(
            models.Nudge.user_id == user_id,
            models.Nudge.followup_id == followup_id,
            models.Nudge.status == "proposed",
        )
        .order_by(models.Nudge.created_at.desc())
        .first()
    )


# ── drafting ────────────────────────────────────────────────────────────────

def _draft_text(
    *,
    first_name: str,
    subject: str,
    tone: str,
    days_silent: int,
    ask: str,
    style_samples: List[str],
    voice_tone: str,
    signature: str,
) -> str:
    """The nudge body. Falls back to a plain template marked as such."""
    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        voice_block = ""
        if voice_tone.strip():
            voice_block += f"\n\nThe user's writing voice is: {voice_tone.strip()}. Match it."
        if style_samples:
            joined = "\n\n".join(f"— {s}" for s in style_samples)
            voice_block += (
                "\n\nWrite it in the USER'S OWN VOICE. Here are emails the user has "
                "written — mirror their greeting, warmth, formality, sentence length "
                "and sign-off (match style, don't copy content):\n" + joined
            )
        if signature:
            voice_block += f"\n\nEnd exactly with the user's usual sign-off:\n{signature}"

        context = f"They last heard from the user about {days_silent} days ago and haven't replied."
        if ask:
            context += f" The open question is: {ask}"

        task = (
            "Write a short follow-up email chasing a thread that has gone quiet.\n\n"
            f"{_TONE_BRIEF.get(tone, _TONE_BRIEF['gentle'])}\n\n"
            f"Recipient's first name: {first_name}\n"
            f"Thread subject: {subject}\n"
            f"{context}\n\n"
            "Two or three sentences at most. No subject line, no placeholders, and "
            "do NOT invent facts, deadlines, or commitments that weren't given. "
            "Never imply the recipient did anything wrong."
        )
        result = client.chat(
            [{"role": "user", "content": task + voice_block}],
            temperature=0.5,
            max_tokens=320,
            system=(
                "You write brief follow-up emails that sound exactly like the user. "
                "Warm, never passive-aggressive, never guilt-tripping. Output only "
                "the email body."
            ),
        )
        text = (getattr(result, "content", "") or "").strip()
        if text:
            return text
    except Exception as e:  # unconfigured proxy / budget / parse error
        logger.info(f"nudge draft falling back to template ({type(e).__name__}: {e})")

    # Marked so the UI never advertises a template as a voice-matched draft.
    sign = signature or "Thanks"
    if tone == "closing":
        body = (
            f"Hi {first_name},\n\nNo worries if this isn't a priority right now — "
            f"I'll close it off on my side. Happy to pick it up whenever.\n\n{sign}"
        )
    elif tone == "direct":
        body = (
            f"Hi {first_name},\n\nFollowing up on this — is it something you're "
            f"still looking at? Happy to help if anything's unclear.\n\n{sign}"
        )
    else:
        body = f"Hi {first_name},\n\nJust floating this back to the top of your inbox.\n\n{sign}"
    return DRAFT_FALLBACK_MARK + body


def generate_nudge(
    db: Session,
    user_id: str,
    fu: models.FollowUp,
    *,
    tone: str = "",
    now: Optional[datetime] = None,
) -> Tuple[Optional[models.Nudge], str]:
    """Draft a nudge for one loop. Returns (nudge, reason_if_refused).

    Draft only — this never sends. Supersedes any existing proposal so the
    approve button is never ambiguous about which text goes out.
    """
    ref = now or ledger.utcnow()
    refusal = why_not_eligible(db, user_id, fu, now=ref)
    if refusal:
        return None, refusal

    attempt = int(fu.nudge_count or 0) + 1
    chosen = tone if tone in _TONE_BRIEF else TONE_FOR_ATTEMPT.get(attempt, "direct")

    clock = fu.last_outbound_at or fu.state_changed_at or fu.created_at or ref
    days_silent = max(1, int((ref - clock).total_seconds() // 86400))

    samples, voice_tone, signature = style_for(db, user_id)
    body = _draft_text(
        first_name=_first_name(fu.counterparty_name or "", fu.counterparty_email or ""),
        subject=fu.subject or "",
        tone=chosen,
        days_silent=days_silent,
        ask=fu.ask_summary or "",
        style_samples=samples,
        voice_tone=voice_tone,
        signature=signature,
    )

    # Supersede rather than stack.
    for old in (
        db.query(models.Nudge)
        .filter(
            models.Nudge.user_id == user_id,
            models.Nudge.followup_id == fu.id,
            models.Nudge.status == "proposed",
        )
        .all()
    ):
        old.status = "skipped"

    last_in_thread = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.thread_id == fu.thread_id,
            models.ThreadMessage.rfc822_msgid.isnot(None),
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .first()
    )

    nudge = models.Nudge(
        user_id=user_id,
        followup_id=fu.id,
        thread_id=fu.thread_id,
        attempt_no=attempt,
        tone=chosen,
        draft=body,
        subject=_reply_subject(fu.subject or ""),
        to_email=fu.counterparty_email or "",
        in_reply_to=(last_in_thread.rfc822_msgid if last_in_thread else "") or "",
        status="proposed",
    )
    db.add(nudge)
    db.commit()
    db.refresh(nudge)
    return nudge, ""


def nudge_payload(nudge: models.Nudge) -> Dict[str, object]:
    """Serialize with the fallback marker stripped, and say whether the draft is
    genuinely voice-matched — a template must never claim to be."""
    clean, is_fallback = split_fallback(nudge.draft or "")
    d = nudge.to_dict()
    d["draft"] = clean
    d["voice_matched"] = not is_fallback
    return d


def mark_sent(
    db: Session,
    user_id: str,
    nudge: models.Nudge,
    fu: models.FollowUp,
    message_id: str,
    *,
    now: Optional[datetime] = None,
) -> None:
    """Record a nudge that really went out, and restart the clock on the thread.

    `stale_after_hours` grows by half each attempt: someone who didn't answer the
    first chase deserves longer before the next, not the same interval again.
    """
    ref = now or ledger.utcnow()
    nudge.status = "sent"
    nudge.sent_at = ref
    nudge.external_id = message_id
    nudge.error = ""

    fu.nudge_count = int(fu.nudge_count or 0) + 1
    fu.last_nudge_at = ref
    fu.stale_after_hours = min(
        fu_service.MAX_STALE_HOURS,
        int(round(int(fu.stale_after_hours or fu_service.DEFAULT_STALE_HOURS) * 1.5)),
    )
    # The one message this app sends to someone the user didn't just hear from,
    # so it belongs on the record more than anything else here does.
    who = fu.counterparty_name or fu.counterparty_email or nudge.to_email or "someone"
    activity.record(
        db, user_id, "nudge_sent",
        f"Followed up with {who}",
        detail=nudge.subject or fu.subject or "",
        subject_type="followup", subject_id=fu.id,
        counterparty_email=nudge.to_email or fu.counterparty_email or "",
        count=int(nudge.attempt_no or 1), at=ref,
        meta={"tone": nudge.tone or "gentle", "attempt": int(nudge.attempt_no or 1)},
    )
    db.commit()
