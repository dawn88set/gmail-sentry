"""
Draft a short reply to an email — human-in-the-loop (never sent automatically;
the app opens Gmail's compose prefilled). LLM via the Claritty proxy, with a
safe deterministic fallback so it works offline.

When `style_samples` (excerpts of the user's own sent emails) are provided, the
draft mirrors THEIR voice — greeting, tone, formality, sign-off.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)
MODEL = "claude-sonnet-4-6"

# Sentinel prefixed to a draft produced by the no-LLM template fallback (NOT the
# user's real voice). Callers strip it with split_fallback() and treat the draft
# as a low-confidence placeholder — e.g. the scan-time pre-draft won't advertise
# it as a ready-to-send draft.
DRAFT_FALLBACK_MARK = "[FB] "


def split_fallback(text: str) -> Tuple[str, bool]:
    """(clean_text, is_fallback) — strips DRAFT_FALLBACK_MARK if present."""
    if text.startswith(DRAFT_FALLBACK_MARK):
        return text[len(DRAFT_FALLBACK_MARK):], True
    return text, False

# Markers that begin a quoted reply chain / forwarded block. We cut the body at
# the first one so an exemplar is the user's OWN prose, not the message they were
# replying to (which otherwise dominates the snippet and muddies the voice).
_QUOTE_MARKERS = re.compile(
    r"(^\s*On .+ wrote:\s*$)"          # Gmail "On Mon, … <x@y> wrote:"
    r"|(^\s*-{2,}\s*Original Message\s*-{2,})"
    r"|(^\s*-{2,}\s*Forwarded message\s*-{2,})"
    r"|(^\s*From:\s.+\S)"              # forwarded header block
    r"|(^\s*_{5,}\s*$)"               # Outlook underscore rule
    r"|(^\s*Sent from my \w+)",        # mobile auto-signature
    re.IGNORECASE | re.MULTILINE,
)


def _clean_body(text: str) -> str:
    """Reduce a raw sent-email body to just the user's own prose: normalize
    newlines, cut at the first quote/forward marker, and drop `>`-quoted lines."""
    if not text:
        return ""
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    m = _QUOTE_MARKERS.search(body)
    if m:
        body = body[: m.start()]
    lines = [ln for ln in body.split("\n") if not ln.lstrip().startswith(">")]
    # collapse >2 blank lines
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return body


def voice_samples(db, user_id: str, limit: int = 5) -> List[str]:
    """The user's own recent sent emails (FULL bodies, cleaned of quoted/forwarded
    text) to match their voice — greeting, tone, and sign-off. Best-effort: []
    if Gmail isn't connected or the read fails. Shared by the reply route and the
    scan-time pre-draft so both sound like the user."""
    from backend.integrations import gmail_ops as gmail_adapter
    from backend.shared.adapters import IntegrationNotConnected, IntegrationError

    samples: List[str] = []
    try:
        # Fetch extra stubs so we can skip empty / near-empty ones and still hit `limit`.
        stubs = gmail_adapter.search(db, user_id, "in:sent", max_results=limit * 3)
        for stub in stubs:
            if len(samples) >= limit:
                break
            mid = stub.get("id")
            if not mid:
                continue
            try:
                body = gmail_adapter.get_body(db, user_id, mid)
            except IntegrationError:
                continue
            cleaned = _clean_body(body)
            if len(cleaned) < 20:  # skip empties / one-word replies
                continue
            if len(cleaned) > 800:  # bound tokens; keep greeting..sign-off
                cleaned = cleaned[:800].rstrip() + "…"
            samples.append(cleaned)
    except (IntegrationNotConnected, IntegrationError):
        return []
    return samples


def style_for(db, user_id: str) -> Tuple[List[str], str, str]:
    """The best voice context for `user_id`: (exemplars, tone, signature). Prefers
    the stored CommProfile (learned once, reused); falls back to reading live
    sent-mail samples when there's no profile yet."""
    from backend.services.learn import get_profile

    prof = get_profile(db, user_id)
    if prof and (prof.style_exemplars or prof.tone):
        samples = list(prof.style_exemplars or []) or voice_samples(db, user_id)
        return samples, (prof.tone or ""), (prof.signature or "")
    return voice_samples(db, user_id), "", ""


#: What the user can ask for, and the instruction each one becomes. Deliberately
#: a closed set: an open text box invites rewriting a draft into something the
#: user never said, and the whole point of drafting in someone's voice is that
#: the words stay theirs.
REFINEMENTS = {
    "shorter": "Cut it down. Same meaning, same voice, fewer words. Remove padding, "
               "not substance. Do not drop any commitment, question, date or number.",
    "warmer": "Make it warmer and friendlier without becoming gushing or informal. "
              "Same facts, same commitments, softer edges.",
    "firmer": "Make it more direct and businesslike. Clearer ask, less hedging. "
              "Never rude, never a threat. Same facts.",
    "formal": "Make it more formal and professional. Fuller sentences, no slang, "
              "no contractions where they read casual. Same facts.",
}


class RefusedToRefine(Exception):
    """The rewrite couldn't be done honestly — surfaced to the user, never
    swallowed into "here's your text back, unchanged"."""


def refine_draft(
    text: str,
    how: str,
    *,
    style_samples: Optional[List[str]] = None,
    tone: str = "",
    context: str = "",
) -> str:
    """Rewrite a passage of a draft the user is already looking at.

    This is the edit that happens AFTER a draft exists — the user reads it,
    finds it nearly right, and wants it shorter or warmer rather than to write
    it again themselves. It's the moment people otherwise abandon the draft and
    type their own, which throws away the voice matching entirely.

    Operates on `text`, which may be a selection rather than the whole draft, so
    the prompt must not add greetings or sign-offs to a fragment.

    RAISES rather than falling back. `draft_reply` can honestly degrade to a
    holding note because something is better than nothing on a blank page; a
    refine has no such excuse. Returning the input unchanged would look like the
    button did nothing, and returning a template would replace the user's words
    with a machine's.
    """
    body = (text or "").strip()
    if not body:
        raise RefusedToRefine("There's nothing selected to rewrite.")
    instruction = REFINEMENTS.get((how or "").strip().lower())
    if not instruction:
        raise RefusedToRefine(f"Don't know how to make it “{how}”.")

    samples = [s.strip() for s in (style_samples or []) if s and s.strip()][:4]
    voice = ""
    if tone.strip():
        voice += f"\n\nThe user's writing voice is: {tone.strip()}. Preserve it."
    if samples:
        joined = "\n\n".join(f"— {s}" for s in samples)
        voice += (
            "\n\nKeep it in the USER'S OWN VOICE. Examples of how they write:\n" + joined
        )

    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        result = client.chat(
            [{"role": "user", "content": (
                f"{instruction}\n\n"
                "Rewrite ONLY the passage below. It may be an excerpt from the middle of an "
                "email, so do not add a greeting, a sign-off, or a subject line unless the "
                "passage already has one. Do not add facts, commitments, dates or numbers "
                "that are not already there. Output only the rewritten passage."
                + (f"\n\nFor context, the email is about: {context}" if context.strip() else "")
                + f"\n\nPassage:\n{body}" + voice
            )}],
            temperature=0.3,
            max_tokens=700,
            system=(
                "You are an editor. You rewrite a passage exactly as instructed while keeping "
                "the author's voice and every fact, commitment and number intact. You never "
                "invent content and never add scaffolding the passage didn't have."
            ),
        )
        out = (getattr(result, "content", "") or "").strip()
        if out:
            return out
        raise RefusedToRefine("The rewrite came back empty. Try again.")
    except RefusedToRefine:
        raise
    except Exception as e:  # noqa: BLE001
        logger.info("refine_draft unavailable: %s: %s", type(e).__name__, e)
        raise RefusedToRefine(
            "Rewriting needs the AI connection, which isn't available right now. "
            "Your draft is untouched."
        ) from e


def draft_reply(
    sender: str,
    subject: str,
    snippet: str,
    style_samples: Optional[List[str]] = None,
    tone: str = "",
    intent: str = "",
    signature: str = "",
) -> str:
    """Draft a reply in the user's voice. When `intent` is given (a rough, scrappy
    note of what the user wants to say — e.g. "tell her Tuesday works, ask for the
    deck"), the draft EXPRESSES that intent, expanded into a polished email in
    their voice. Without an intent, it replies to the email on its merits.

    Returns the draft body. On LLM failure it returns a plain holding note prefixed
    with the DRAFT_FALLBACK_MARK sentinel so callers can flag it as a low-confidence
    placeholder rather than presenting it as the user's real voice."""
    name = (sender or "there").split("<")[0].strip().strip('"') or "there"
    first = name.split(" ")[0] if name else "there"
    samples = [s.strip() for s in (style_samples or []) if s and s.strip()][:6]
    intent = (intent or "").strip()
    signature = (signature or "").strip()

    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        voice_block = ""
        if tone.strip():
            voice_block += f"\n\nThe user's writing voice is: {tone.strip()}. Match it."
        if samples:
            joined = "\n\n".join(f"— {s}" for s in samples)
            voice_block += (
                "\n\nWrite it in the USER'S OWN VOICE. Here are full examples of emails the user "
                "has written — mirror their greeting, tone, warmth, formality, sentence length, "
                "and sign-off (don't copy content, match style):\n" + joined
            )
        if signature:
            voice_block += (
                f"\n\nEnd the reply with the user's usual sign-off, exactly as they write it:\n{signature}"
            )
        if intent:
            task = (
                "The user gave a quick, scrappy note of what they want to say. Turn it into a "
                "polished, ready-to-send reply that conveys EXACTLY that intent — nothing more, "
                "don't invent facts, commitments, dates, or details they didn't give. No "
                "placeholders, no subject line.\n\n"
                f"The user's note: {intent}\n\n"
                f"Replying to — From: {sender}\nSubject: {subject}\nBody: {snippet}"
            )
        else:
            task = (
                "Draft a brief reply to this email. Ready to send, no placeholders, no "
                "subject line.\n\n"
                f"From: {sender}\nSubject: {subject}\nBody: {snippet}"
            )
        result = client.chat(
            [{"role": "user", "content": task + voice_block}],
            temperature=0.5,
            max_tokens=500,
            system=(
                "You write email replies that sound exactly like the user. When given samples of "
                "their writing, match their voice precisely. When given a scrappy note of intent, "
                "expand it faithfully without inventing anything. Output only the reply body."
            ),
        )
        text = (getattr(result, "content", "") or "").strip()
        if text:
            return text
    except Exception as e:  # unconfigured proxy / budget / error
        # WARNING (not info): the generic template below is NOT the user's voice —
        # if this fires often, drafts silently read robotic. Callers key off
        # DRAFT_FALLBACK_MARK to flag it as a placeholder in the UI.
        logger.warning(f"reply draft: LLM unavailable, using placeholder template ({e})")

    # No-LLM fallback: echo the intent politely if given, else a safe holding note.
    # Prefixed with the sentinel so the caller can mark it low-confidence.
    if intent:
        return DRAFT_FALLBACK_MARK + f"Hi {first},\n\n{intent}\n\n{signature or 'Best'}"
    return DRAFT_FALLBACK_MARK + (
        f"Hi {first},\n\nThanks for your message — I saw this and will follow up shortly.\n\n{signature or 'Best'}"
    )
