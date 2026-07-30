"""
Learn the user's real communication patterns.

`learn_patterns` reads the user's actual inbox + sent mail (metadata / snippets
only) and upserts a CommProfile: the people they truly correspond with
(behavioral VIPs), a short descriptor of their writing voice, and a few of their
own sent-mail exemplars. Two consumers use it:

  - triage (backend/services/sentry.py) boosts mail from these frequent contacts,
  - reply drafting (backend/services/reply.py) mirrors the stored tone + exemplars
    so replies sound like the user without re-deriving them on every draft.

Best-effort and grounded: reuses onboarding.collect_inbox_signals and
reply.voice_samples, and derives tone via the Claritty LLM proxy with a safe
no-op fallback (an empty tone just means drafts fall back to the exemplars).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend import models

logger = logging.getLogger(__name__)
MODEL = "claude-sonnet-4-6"


def get_profile(db: Session, user_id: str) -> Optional[models.CommProfile]:
    return (
        db.query(models.CommProfile)
        .filter(models.CommProfile.user_id == user_id)
        .first()
    )


def _derive_voice(exemplars: List[str]) -> tuple[str, str]:
    """(tone, signature) for the user, from their own full sent emails — one LLM
    call. `tone` is a short descriptor of their voice; `signature` is their actual
    sign-off block (e.g. "Best,\\nShahar") to append verbatim to future drafts.
    ("", "") on any failure — drafts still use the raw exemplars."""
    import json

    samples = [s.strip() for s in exemplars if s and s.strip()][:6]
    if not samples:
        return "", ""
    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        joined = "\n\n".join(f"— {s}" for s in samples)
        result = client.chat(
            [
                {
                    "role": "user",
                    "content": (
                        "Here are full emails this person has written. Return a compact JSON object "
                        '{"tone": "<one short phrase, max ~12 words: greeting style, warmth, '
                        'formality, sentence length>", "signature": "<their exact sign-off block, '
                        "e.g. 'Best,\\nShahar' — the closing line(s) they consistently end with; "
                        'empty string if none is consistent>"}. Output ONLY the JSON.\n\n' + joined
                    ),
                }
            ],
            temperature=0.2,
            max_tokens=160,
            system="You analyze a person's email writing voice and output only the requested JSON.",
        )
        raw = (getattr(result, "content", "") or "").strip()
        # Tolerate code fences / stray prose around the JSON object.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(raw[start : end + 1])
            tone = str(data.get("tone") or "").strip().strip('"')[:120]
            signature = str(data.get("signature") or "").strip()[:200]
            return tone, signature
    except Exception as e:  # noqa: BLE001 — voice derivation is best-effort
        logger.info(f"voice derivation skipped ({type(e).__name__}: {e})")
    return "", ""


def learn_patterns(db: Session, user_id: str) -> Dict[str, Any]:
    """Build/refresh the user's CommProfile from real signals. Never raises —
    returns the (possibly unchanged) profile dict."""
    from backend.services.onboarding import collect_inbox_signals
    from backend.services.reply import voice_samples

    prof = get_profile(db, user_id)
    if prof is None:
        prof = models.CommProfile(user_id=user_id)
        db.add(prof)

    signals = collect_inbox_signals(db, user_id)
    if signals:
        vips = [
            {"email": s["email"], "name": s.get("name", ""), "count": s.get("count", 0)}
            for s in signals.get("top_senders", [])
            if s.get("personal") and s.get("email")
        ][:8]
        if vips:
            prof.vip_senders = vips
            prof.response_habits = {"frequent_contacts": [v["email"] for v in vips]}

    exemplars = voice_samples(db, user_id, limit=6)
    if exemplars:
        prof.style_exemplars = exemplars
        tone, signature = _derive_voice(exemplars)
        if tone:
            prof.tone = tone
        if signature:
            prof.signature = signature

    prof.refreshed_at = datetime.utcnow()
    db.commit()
    db.refresh(prof)
    return prof.to_dict()
