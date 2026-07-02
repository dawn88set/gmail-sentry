"""
Draft a short reply to an email — human-in-the-loop (never sent automatically;
the app opens Gmail's compose prefilled). LLM via the Claritty proxy, with a
safe deterministic fallback so it works offline.

When `style_samples` (excerpts of the user's own sent emails) are provided, the
draft mirrors THEIR voice — greeting, tone, formality, sign-off.
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)
MODEL = "claude-sonnet-4-6"


def draft_reply(
    sender: str,
    subject: str,
    snippet: str,
    style_samples: Optional[List[str]] = None,
) -> str:
    name = (sender or "there").split("<")[0].strip().strip('"') or "there"
    first = name.split(" ")[0] if name else "there"
    samples = [s.strip() for s in (style_samples or []) if s and s.strip()][:6]

    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        voice_block = ""
        if samples:
            joined = "\n\n".join(f"— {s}" for s in samples)
            voice_block = (
                "\n\nWrite it in the USER'S OWN VOICE. Here are excerpts of emails the user "
                "has written — mirror their greeting, tone, warmth, formality, sentence length, "
                "and sign-off (don't copy content, match style):\n" + joined
            )
        result = client.chat(
            [
                {
                    "role": "user",
                    "content": (
                        "Draft a brief reply to this email. Ready to send, no placeholders, no "
                        "subject line.\n\n"
                        f"From: {sender}\nSubject: {subject}\nBody: {snippet}" + voice_block
                    ),
                }
            ],
            temperature=0.5,
            max_tokens=280,
            system=(
                "You write email replies that sound exactly like the user. When given samples of "
                "their writing, match their voice precisely. Output only the reply body."
            ),
        )
        text = (getattr(result, "content", "") or "").strip()
        if text:
            return text
    except Exception as e:  # unconfigured proxy / budget / error
        logger.info(f"reply draft: falling back to template ({e})")

    return (
        f"Hi {first},\n\nThanks for your message — I saw this and will follow up shortly.\n\nBest"
    )
