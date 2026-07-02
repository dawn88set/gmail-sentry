"""
Smart onboarding — turn a little intent (a role, a noise preference, an optional
sentence) plus the user's *real inbox signals* into a complete Gmail Sentry
setup: urgency rules + filing rules + notify tier.

Mirrors backend/services/triage.py: try the LLM via claritty_sdk.llm, fall back
to a deterministic, grounded heuristic so it always yields a usable draft — even
offline and even before Gmail is connected.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.services.triage import MODEL, _parse_json, _norm_tier
from backend.shared.adapters import IntegrationNotConnected, IntegrationError
from backend.integrations import gmail_ops as gmail_adapter

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Local-parts that signal a non-personal / bulk sender (not a VIP human).
_BULK_LOCALPARTS = {
    "no-reply", "noreply", "do-not-reply", "donotreply", "notifications",
    "notification", "updates", "update", "news", "newsletter", "newsletters",
    "hello", "team", "info", "mailer", "mailer-daemon", "marketing", "digest",
    "alerts", "alert", "community", "social", "help",
}

# Role → a starter keyword pack (used to seed keyword rules when we can't ground).
_ROLE_KEYWORDS: Dict[str, List[str]] = {
    "founder": ["invoice", "investor", "contract", "board", "term sheet"],
    "exec": ["board", "contract", "escalation", "quarterly", "approval"],
    "manager": ["deadline", "review", "approval", "1:1", "blocker"],
    "sales": ["demo", "proposal", "contract", "renewal", "pricing"],
    "support": ["outage", "bug", "refund", "urgent", "downtime"],
    "individual": ["invoice", "appointment", "deadline", "offer"],
}


def _valid_tier(t: str) -> str:
    return _norm_tier(t)


def _parse_addr(frm: str) -> Dict[str, str]:
    frm = frm or ""
    m = EMAIL_RE.search(frm)
    email = m.group(0).lower() if m else ""
    domain = email.split("@", 1)[1] if "@" in email else ""
    name = frm.split("<", 1)[0].strip().strip('"') if "<" in frm else (frm.strip() if not email else "")
    return {"email": email, "domain": domain, "name": name}


# ---------------------------------------------------------------------------
# 1) Real-inbox signals (metadata only — no bodies)
# ---------------------------------------------------------------------------


def collect_inbox_signals(db: Session, user_id: str, sample: int = 30) -> Optional[Dict[str, Any]]:
    """Gather grounding signals from the user's actual inbox. Metadata only.

    Best-effort — returns None on ANY error (not connected, API hiccup, parse
    issue) so /suggest never fails because of a Gmail read.
    """
    try:
        return _collect_inbox_signals(db, user_id, sample)
    except Exception as e:  # noqa: BLE001 — never let a Gmail read break onboarding
        logger.info(f"onboarding signals skipped ({type(e).__name__}: {e})")
        return None


def _collect_inbox_signals(db: Session, user_id: str, sample: int) -> Optional[Dict[str, Any]]:
    try:
        stubs = gmail_adapter.search(db, user_id, "in:inbox newer_than:30d", max_results=sample)
    except (IntegrationNotConnected, IntegrationError):
        return None

    senders: Counter = Counter()
    names: Dict[str, str] = {}
    subjects: List[str] = []
    for stub in stubs[:sample]:
        mid = stub.get("id")
        if not mid:
            continue
        try:
            meta = gmail_adapter.get_meta(db, user_id, mid)
        except IntegrationError:
            continue
        info = _parse_addr(meta.get("sender", ""))
        if info["email"]:
            senders[info["email"]] += 1
            if info["name"]:
                names.setdefault(info["email"], info["name"])
        subj = (meta.get("subject") or "").strip()
        if subj and len(subjects) < 8:
            subjects.append(subj)

    top_senders = []
    for email, count in senders.most_common(12):
        local = email.split("@", 1)[0]
        top_senders.append({
            "email": email,
            "domain": email.split("@", 1)[1] if "@" in email else "",
            "name": names.get(email, ""),
            "count": count,
            "personal": local not in _BULK_LOCALPARTS,
        })

    # Category sizes + promo domains for filing suggestions.
    counts = {}
    for key, q in (("promotions", "category:promotions"), ("social", "category:social"), ("spam", "in:spam")):
        try:
            counts[key] = gmail_adapter.count(db, user_id, q)
        except (IntegrationError, IntegrationNotConnected):
            counts[key] = 0

    promo_domains: List[str] = []
    try:
        promo_stubs = gmail_adapter.search(db, user_id, "category:promotions", max_results=12)
        pd: Counter = Counter()
        for s in promo_stubs[:12]:
            mid = s.get("id")
            if not mid:
                continue
            try:
                meta = gmail_adapter.get_meta(db, user_id, mid)
            except IntegrationError:
                continue
            dom = _parse_addr(meta.get("sender", ""))["domain"]
            if dom:
                pd[dom] += 1
        promo_domains = [d for d, _ in pd.most_common(6)]
    except (IntegrationError, IntegrationNotConnected):
        promo_domains = []

    return {
        "top_senders": top_senders,
        "sample_subjects": subjects,
        "promo_domains": promo_domains,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# 2) Draft generation (LLM → heuristic fallback)
# ---------------------------------------------------------------------------


def _build_prompt(
    description: str,
    role: str,
    noise: str,
    signals: Optional[Dict[str, Any]],
    current_draft: Optional[Dict[str, Any]],
) -> str:
    parts = [
        "Design a complete Gmail Sentry setup for this user. Gmail Sentry watches "
        "an inbox, flags what needs attention (Slack ping with a deep link), and "
        "auto-files low-value mail.\n",
        f"User role: {role or 'unknown'}",
        f"How noisy they want alerts: {noise or 'balanced'} "
        "(urgent = only true fire; balanced = also needs-reply; everything = be generous).",
    ]
    if description:
        parts.append(f"\nWhat they told us (verbatim): {description}")
    if signals:
        ts = ", ".join(
            f"{s['email']}({s['count']})" for s in signals.get("top_senders", [])[:8]
        )
        parts.append(f"\nMost frequent senders in their inbox: {ts or 'n/a'}")
        if signals.get("promo_domains"):
            parts.append(f"Promotional/newsletter domains: {', '.join(signals['promo_domains'])}")
        if signals.get("sample_subjects"):
            parts.append("Recent subjects: " + " | ".join(signals["sample_subjects"][:6]))
    if current_draft:
        import json as _json
        parts.append(
            "\nRefine THIS existing draft using the new instruction above; keep good "
            "items, add/adjust as asked:\n" + _json.dumps(current_draft)[:2000]
        )
    parts.append(
        "\nReturn ONLY JSON:\n"
        '{"triage_rules":[{"name":"","kind":"nl|vip_sender|keyword","value":"",'
        '"tier":"urgent|needs_reply|fyi","reason":""}],'
        '"label_rules":[{"name":"","match_type":"sender|domain|subject_keyword",'
        '"match_value":"","target_label":"","archive_after":true,"reason":""}],'
        '"notify_tier":"urgent|needs_reply","scan_minutes":5,"summary":""}\n'
        "Prefer concrete, grounded rules (use the real senders/domains above). Keep "
        "reasons to a short phrase. 3-6 triage rules, 1-4 label rules."
    )
    return "\n".join(parts)


def _normalize(draft: Dict[str, Any]) -> Dict[str, Any]:
    tri, seen = [], set()
    for r in draft.get("triage_rules") or []:
        kind = str(r.get("kind", "nl")).lower()
        if kind not in ("nl", "vip_sender", "keyword"):
            kind = "nl"
        value = str(r.get("value", "")).strip()
        name = str(r.get("name", "")).strip() or value[:40]
        if not value or (kind, value.lower()) in seen:
            continue
        seen.add((kind, value.lower()))
        tri.append({
            "name": name, "kind": kind, "value": value,
            "tier": _valid_tier(r.get("tier", "urgent")),
            "reason": str(r.get("reason", "")).strip(),
        })
    lab, seenl = [], set()
    for r in draft.get("label_rules") or []:
        mt = str(r.get("match_type", "sender")).lower()
        if mt not in ("sender", "domain", "subject_keyword"):
            mt = "sender"
        mv = str(r.get("match_value", "")).strip()
        label = str(r.get("target_label", "")).strip()
        if not mv or not label or (mt, mv.lower()) in seenl:
            continue
        seenl.add((mt, mv.lower()))
        lab.append({
            "name": str(r.get("name", "")).strip() or label,
            "match_type": mt, "match_value": mv, "target_label": label,
            "archive_after": bool(r.get("archive_after", False)),
            "reason": str(r.get("reason", "")).strip(),
        })
    notify = str(draft.get("notify_tier", "urgent")).lower()
    if notify not in ("urgent", "needs_reply"):
        notify = "urgent"
    try:
        scan = int(draft.get("scan_minutes", 5))
    except Exception:
        scan = 5
    scan = max(1, min(scan, 60))
    return {
        "triage_rules": tri[:8],
        "label_rules": lab[:6],
        "notify_tier": notify,
        "scan_minutes": scan,
        "summary": str(draft.get("summary", "")).strip(),
    }


def _heuristic(
    description: str, role: str, noise: str, signals: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    tri: List[Dict[str, Any]] = []
    lab: List[Dict[str, Any]] = []
    default_tier = "urgent" if (noise or "balanced") == "urgent" else "needs_reply"

    # Grounded: top personal senders → VIP; promo domains → filing.
    if signals:
        for s in signals.get("top_senders", []):
            if s.get("personal") and len(tri) < 3:
                who = s.get("name") or s["email"]
                tri.append({
                    "name": f"From {who}", "kind": "vip_sender", "value": s["email"],
                    "tier": "urgent", "reason": f"You get a lot of mail from {s['email']} ({s['count']} recently)",
                })
        for dom in signals.get("promo_domains", [])[:3]:
            lab.append({
                "name": f"File {dom}", "match_type": "domain", "match_value": dom,
                "target_label": "Newsletters", "archive_after": True,
                "reason": f"{dom} sends you promotions — file & archive them",
            })

    # Role keyword pack.
    role_key = (role or "").lower()
    for k, words in _ROLE_KEYWORDS.items():
        if k in role_key:
            for w in words[:4]:
                tri.append({
                    "name": f"Keyword: {w}", "kind": "keyword", "value": w,
                    "tier": default_tier, "reason": f"Common priority for a {role}",
                })
            break

    # Anything explicit in the free-text (emails → VIP, quoted words → nl).
    for email in dict.fromkeys(EMAIL_RE.findall(description or "")):
        tri.append({
            "name": f"From {email}", "kind": "vip_sender", "value": email.lower(),
            "tier": "urgent", "reason": "You mentioned this sender",
        })
    if description and not EMAIL_RE.search(description):
        tri.append({
            "name": "Your instruction", "kind": "nl", "value": description.strip()[:180],
            "tier": default_tier, "reason": "From what you described",
        })

    if not tri:
        tri.append({
            "name": "Invoices & payments", "kind": "keyword", "value": "invoice",
            "tier": "needs_reply", "reason": "A safe default worth catching",
        })

    return _normalize({
        "triage_rules": tri,
        "label_rules": lab,
        "notify_tier": default_tier if default_tier == "urgent" else "needs_reply",
        "scan_minutes": 5,
        "summary": "Starter setup based on your inbox and role — tweak anything below.",
    })


def generate_setup(
    description: str = "",
    role: str = "",
    noise: str = "balanced",
    signals: Optional[Dict[str, Any]] = None,
    current_draft: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Produce a normalized setup draft. LLM first, grounded heuristic fallback."""
    try:
        from claritty_sdk.llm import get_llm_client

        client = get_llm_client(MODEL)
        result = client.chat(
            [{"role": "user", "content": _build_prompt(description, role, noise, signals, current_draft)}],
            temperature=0.2,
            max_tokens=900,
            system=(
                "You are an expert email-management assistant. You configure a Gmail "
                "triage app precisely and conservatively, grounding rules in the user's "
                "real senders when provided. Output strict JSON only."
            ),
        )
        parsed = _parse_json(getattr(result, "content", "") or "")
        draft = _normalize(parsed)
        if draft["triage_rules"] or draft["label_rules"]:
            draft["source"] = "ai"
            return draft
    except Exception as e:  # unconfigured proxy, budget, parse error, etc.
        logger.info(f"onboarding: falling back to heuristic ({e})")

    out = _heuristic(description, role, noise, signals)
    out["source"] = "heuristic"
    return out
