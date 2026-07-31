"""
Email triage — decide an incoming email's attention tier.

`classify_email` fuses the user's rules (natural-language, VIP senders, keywords)
with deadline/action detection. It asks the LLM via the Claritty proxy
(`claritty_sdk.llm.get_llm_client`) for a nuanced judgement, and falls back to a
deterministic heuristic when the proxy isn't configured (local dev / CI) or the
call fails — so the Sentry always produces a result, never a hard error.

Tiers: "urgent" > "needs_reply" > "fyi".

It also extracts the ASK — one line saying what the sender actually wants —
and any explicit deadline. Those ride along in the same model call that was
already being made, so they cost ~60% more output tokens on a call we make
~97% less often since the ledger landed. The ask is what makes a follow-up
row worth reading: "Re: Q3" tells you nothing, "needs the revised quote by
Friday" tells you everything.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TIER_RANK = {"urgent": 2, "needs_reply": 1, "fyi": 0}
MODEL = "claude-sonnet-4-6"

# Cues that an email contains an explicit ask or a deadline.
_URGENT_CUES = re.compile(
    r"\b(asap|urgent|immediately|today|eod|by end of day|right away|deadline|overdue|past due|final notice)\b",
    re.IGNORECASE,
)
_ACTION_CUES = re.compile(
    r"\b(can you|could you|please (?:review|reply|respond|confirm|approve|send|sign)|"
    r"need(?:ed)? (?:your|a) (?:reply|response|approval|sign-?off)|let me know|"
    r"awaiting|follow up|due (?:on|by|in)|invoice|payment|sign[- ]?off|rsvp)\b",
    re.IGNORECASE,
)


def _norm_tier(value: str) -> str:
    v = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if v in TIER_RANK:
        return v
    if v in ("needs_response", "reply", "respond"):
        return "needs_reply"
    if v in ("important", "high", "critical"):
        return "urgent"
    return "fyi"


def _matches_rule(kind: str, value: str, sender: str, subject: str, snippet: str) -> bool:
    value = (value or "").strip().lower()
    if not value:
        return False
    sender_l = (sender or "").lower()
    haystack = f"{subject} {snippet}".lower()
    if kind == "vip_sender":
        return value in sender_l
    if kind == "keyword":
        return value in haystack
    # nl rules can't be matched deterministically; the LLM path handles them.
    return False


#: Explicit deadline phrasings we can resolve without a model.
_DUE_CUES = re.compile(
    r"\b(?:by|before|due(?:\s+(?:on|by))?)\s+"
    r"(today|tomorrow|eod|end of day|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|next week|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2})\b",
    re.IGNORECASE,
)

_DAY_OFFSETS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def extract_ask(subject: str, snippet: str) -> str:
    """The first sentence that actually asks for something, trimmed to one line.

    Deterministic counterpart to the model's `ask`. Deliberately conservative:
    returns "" rather than guessing, because a wrong one-line summary on a
    follow-up row is worse than none — the user acts on it.
    """
    for sentence in _sentences(snippet) + _sentences(subject):
        if _ACTION_CUES.search(sentence) or _URGENT_CUES.search(sentence):
            one_line = " ".join(sentence.split())
            return one_line[:117] + "…" if len(one_line) > 118 else one_line
    return ""


def resolve_due(raw: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """Turn an extracted deadline into a datetime. None when we can't be sure.

    Anything ambiguous returns None on purpose: a fabricated deadline would make
    the app chase people early, which is the failure mode users don't forgive.
    """
    raw = (raw or "").strip().lower()
    if not raw:
        return None
    ref = now or datetime.utcnow()
    end_of = ref.replace(hour=17, minute=0, second=0, microsecond=0)

    if raw in ("today", "eod", "end of day"):
        return end_of
    if raw == "tomorrow":
        return end_of + timedelta(days=1)
    if raw == "next week":
        return end_of + timedelta(days=7)
    if raw in _DAY_OFFSETS:
        delta = (_DAY_OFFSETS[raw] - ref.weekday()) % 7
        return end_of + timedelta(days=delta or 7)

    # ISO-ish, from the model path.
    for fmt in ("%Y-%m-%d", "%Y-%m-%dt%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            pass
    # d/m or m/d — genuinely ambiguous across locales, so we decline to guess.
    return None


def heuristic_classify(
    rules: List[Dict[str, Any]], sender: str, subject: str, snippet: str
) -> Dict[str, Any]:
    """Deterministic, no-LLM triage. Returns {tier, reason, matched_rules, ask, due}."""
    matched: List[str] = []
    best_tier = "fyi"

    for r in rules:
        if r.get("kind") in ("vip_sender", "keyword") and _matches_rule(
            r.get("kind", ""), r.get("value", ""), sender, subject, snippet
        ):
            matched.append(r.get("name") or r.get("value", ""))
            tier = _norm_tier(r.get("tier", "urgent"))
            if TIER_RANK[tier] > TIER_RANK[best_tier]:
                best_tier = tier

    text = f"{subject} {snippet}"
    if _URGENT_CUES.search(text):
        if TIER_RANK["urgent"] > TIER_RANK[best_tier]:
            best_tier = "urgent"
        matched.append("deadline cue")
    elif _ACTION_CUES.search(text):
        if TIER_RANK["needs_reply"] > TIER_RANK[best_tier]:
            best_tier = "needs_reply"
        matched.append("action requested")

    if matched:
        reason = "Matched: " + ", ".join(dict.fromkeys(matched))
    else:
        reason = "No urgency signals matched"

    ask = extract_ask(subject, snippet)
    due_match = _DUE_CUES.search(text)
    return {
        "tier": best_tier,
        "reason": reason,
        "matched_rules": list(dict.fromkeys(matched)),
        "ask": ask,
        # Low by construction — a regex found a phrase, it didn't understand the
        # email. The UI can show the ask while letting the user correct it.
        "ask_confidence": 45 if ask else 0,
        "due": due_match.group(1) if due_match else "",
        "expects_reply": bool(ask) or TIER_RANK[best_tier] > TIER_RANK["fyi"],
    }


def _build_prompt(rules: List[Dict[str, Any]], sender: str, subject: str, snippet: str) -> str:
    rule_lines = []
    for r in rules:
        kind = r.get("kind")
        if kind == "nl":
            rule_lines.append(f"- (rule) {r.get('value')} → implies tier {r.get('tier')}")
        elif kind == "vip_sender":
            rule_lines.append(f"- VIP sender: {r.get('value')} → implies tier {r.get('tier')}")
        elif kind == "keyword":
            rule_lines.append(f"- Keyword: {r.get('value')} → implies tier {r.get('tier')}")
    rules_text = "\n".join(rule_lines) or "(no custom rules defined)"
    return (
        "Classify this email into exactly one attention tier: "
        "urgent, needs_reply, or fyi.\n\n"
        "The user's rules:\n"
        f"{rules_text}\n\n"
        "Also flag as needs_reply (or urgent) any email that contains an explicit "
        "ask, a deadline, or a meeting/payment request, even if no rule matches.\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Body preview: {snippet}\n\n"
        "Also extract what the sender is ASKING the user to do, as one short "
        "line the user could act on without opening the email — 'needs the "
        "revised quote by Friday', not 'Re: Q3'. If nothing is being asked, "
        'return an empty string rather than inventing one.\n\n'
        'Respond with ONLY a JSON object: '
        '{"tier": "urgent|needs_reply|fyi", "reason": "<one short sentence>", '
        '"matched_rules": ["<rule names that applied>"], '
        '"ask": "<one line, max 100 chars, or empty>", '
        '"ask_confidence": <0-100>, '
        '"due": "<YYYY-MM-DD if an explicit deadline is stated, else empty>", '
        '"expects_reply": true|false}'
    )


def _parse_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    # Tolerate code fences / surrounding prose: grab the first {...} block.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def classify_email(
    rules: List[Dict[str, Any]], sender: str, subject: str, snippet: str
) -> Dict[str, Any]:
    """Classify one email. LLM first, heuristic fallback. Always returns
    {tier, reason, matched_rules, source}."""
    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        result = client.chat(
            [{"role": "user", "content": _build_prompt(rules, sender, subject, snippet)}],
            temperature=0.0,
            max_tokens=320,  # the ask + due fields grew the contract
            system=(
                "You are an inbox triage assistant. You are precise and conservative: "
                "only mark something urgent when it truly needs attention now."
            ),
        )
        parsed = _parse_json(getattr(result, "content", "") or "")
        tier = _norm_tier(str(parsed.get("tier", "fyi")))
        reason = str(parsed.get("reason") or "").strip() or "Classified by AI"
        matched = parsed.get("matched_rules") or []
        if not isinstance(matched, list):
            matched = [str(matched)]
        ask = " ".join(str(parsed.get("ask") or "").split())[:180]
        try:
            confidence = max(0, min(100, int(parsed.get("ask_confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0
        return {
            "tier": tier,
            "reason": reason,
            "matched_rules": matched,
            "ask": ask,
            "ask_confidence": confidence if ask else 0,
            "due": str(parsed.get("due") or "").strip(),
            "expects_reply": bool(parsed.get("expects_reply", TIER_RANK[tier] > 0)),
            "source": "ai",
        }
    except Exception as e:  # unconfigured proxy, 402 budget, parse error, etc.
        logger.info(f"triage: falling back to heuristic ({e})")
        out = heuristic_classify(rules, sender, subject, snippet)
        out["source"] = "heuristic"
        return out
