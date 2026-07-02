"""
Email triage — decide an incoming email's attention tier.

`classify_email` fuses the user's rules (natural-language, VIP senders, keywords)
with deadline/action detection. It asks the LLM via the Claritty proxy
(`claritty_sdk.llm.get_llm_client`) for a nuanced judgement, and falls back to a
deterministic heuristic when the proxy isn't configured (local dev / CI) or the
call fails — so the Sentry always produces a result, never a hard error.

Tiers: "urgent" > "needs_reply" > "fyi".
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

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


def heuristic_classify(
    rules: List[Dict[str, Any]], sender: str, subject: str, snippet: str
) -> Dict[str, Any]:
    """Deterministic, no-LLM triage. Returns {tier, reason, matched_rules}."""
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
    return {"tier": best_tier, "reason": reason, "matched_rules": list(dict.fromkeys(matched))}


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
        'Respond with ONLY a JSON object: '
        '{"tier": "urgent|needs_reply|fyi", "reason": "<one short sentence>", '
        '"matched_rules": ["<rule names that applied>"]}'
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
            max_tokens=200,
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
        return {"tier": tier, "reason": reason, "matched_rules": matched, "source": "ai"}
    except Exception as e:  # unconfigured proxy, 402 budget, parse error, etc.
        logger.info(f"triage: falling back to heuristic ({e})")
        out = heuristic_classify(rules, sender, subject, snippet)
        out["source"] = "heuristic"
        return out
