"""
Smart onboarding API — the intelligent setup assistant.

- GET  /api/onboarding/status  → whether the user has completed setup (+ remembered intent)
- POST /api/onboarding/suggest → propose a full setup, grounded in the real inbox when connected
- POST /api/onboarding/apply   → create the chosen rules and mark onboarding complete

backend/main.py auto-includes `router`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.security import require_user
from backend import models
from backend.services.sentry import get_config
from backend.services import onboarding as onb

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/onboarding/status")
async def onboarding_status(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    cfg = get_config(db, user_id)
    return {"onboarded": bool(cfg.onboarded), "intent": cfg.intent or "", "role": cfg.role or ""}


class SuggestBody(BaseModel):
    description: Optional[str] = ""
    role: Optional[str] = ""
    noise: Optional[str] = "balanced"
    current_draft: Optional[Dict[str, Any]] = None


@router.post("/api/onboarding/suggest")
async def onboarding_suggest(
    body: SuggestBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Propose a complete setup. Best-effort grounds in the real inbox; never 409s
    and never 500s — a Gmail/LLM hiccup still yields a usable draft."""
    signals = onb.collect_inbox_signals(db, user_id)
    try:
        draft = onb.generate_setup(
            description=body.description or "",
            role=body.role or "",
            noise=body.noise or "balanced",
            signals=signals,
            current_draft=body.current_draft,
        )
    except Exception as e:  # noqa: BLE001 — always return a draft
        logger.warning(f"onboarding suggest fell back ({type(e).__name__}: {e})")
        draft = onb.generate_setup(
            description=body.description or "", role=body.role or "", noise=body.noise or "balanced"
        )
    signals_summary = None
    if signals:
        signals_summary = {
            "senders": len(signals.get("top_senders", [])),
            "promo_domains": signals.get("promo_domains", [])[:5],
            "counts": signals.get("counts", {}),
        }
    return {"draft": draft, "grounded": bool(signals), "signals_summary": signals_summary}


class TriageRuleIn(BaseModel):
    name: str
    kind: str = "nl"
    value: str
    tier: str = "urgent"


class LabelRuleIn(BaseModel):
    name: str
    match_type: str = "sender"
    match_value: str
    target_label: str
    archive_after: bool = False


class ApplyBody(BaseModel):
    triage_rules: List[TriageRuleIn] = []
    label_rules: List[LabelRuleIn] = []
    notify_tier: Optional[str] = None
    intent: Optional[str] = ""
    role: Optional[str] = ""


@router.post("/api/onboarding/apply")
async def onboarding_apply(
    body: ApplyBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create the chosen rules and mark onboarding complete."""
    created_rules = 0
    for r in body.triage_rules:
        kind = r.kind if r.kind in ("nl", "vip_sender", "keyword") else "nl"
        tier = r.tier if r.tier in ("urgent", "needs_reply", "fyi") else "urgent"
        name = (r.name or "").strip()
        value = (r.value or "").strip()
        if not name or not value:
            continue
        db.add(models.TriageRule(user_id=user_id, name=name, kind=kind, value=value, tier=tier))
        created_rules += 1

    created_label_rules = 0
    for r in body.label_rules:
        mt = r.match_type if r.match_type in ("sender", "domain", "subject_keyword") else "sender"
        name = (r.name or "").strip()
        mv = (r.match_value or "").strip()
        label = (r.target_label or "").strip()
        if not (name and mv and label):
            continue
        db.add(models.LabelRule(
            user_id=user_id, name=name, match_type=mt, match_value=mv,
            target_label=label, archive_after=bool(r.archive_after),
        ))
        created_label_rules += 1

    cfg = get_config(db, user_id)
    if body.notify_tier in ("urgent", "needs_reply"):
        cfg.notify_tier = body.notify_tier
    if body.intent is not None:
        cfg.intent = body.intent.strip()
    if body.role is not None:
        cfg.role = body.role.strip()
    cfg.onboarded = True

    db.commit()
    return {
        "created_rules": created_rules,
        "created_label_rules": created_label_rules,
        "onboarded": True,
    }
