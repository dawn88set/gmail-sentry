"""
B4 — Agent-side reuse: persist a triaged/drafted item from a custom tool.

Every "draft → approve → send" app needs one custom tool its agent calls to save
a PENDING_APPROVAL item on the spine (so the /approve route + audit + widgets all
apply). `persist_item` is that logic, once — so an app's save tool shrinks to a
handful of lines that map the agent's tool input onto the model:

    # backend/custom/tools/app_save_<x>/impl.py
    from claritty_sdk import tool, ToolCtx
    from backend.database import SessionLocal
    from backend.models import Ticket
    from backend.shared.agent_tools import persist_item

    @tool(id="app.save_ticket")
    def run(input, ctx: ToolCtx):
        db = SessionLocal()
        try:
            tid = persist_item(
                db, Ticket, user_id=ctx.user_id,
                title=input.get("title") or input.get("subject"),
                body=input.get("draft_text"), source="gmail",
                score=int(input.get("score") or 0),
                reason=input.get("reason"),
                payload={"thread_id": input.get("thread_id"),
                         "in_reply_to": input.get("message_id")},
                extra={"contact_email": input.get("contact_email")},
            )
            return {"ticket_id": tid}
        finally:
            db.close()

See PATTERNS.md (same folder) for the five reusable agent system-prompt patterns.
"""

from typing import Any, Dict, Optional

from backend.shared.spine import ItemStatus, record_audit


def derive_priority(score: Optional[int]) -> str:
    """Map a 0–100 score to the spine's priority bucket (shared so every app
    ranks consistently)."""
    if score is None:
        return "medium"
    if score >= 80:
        return "urgent"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def persist_item(
    db,
    Model,
    *,
    user_id: str,
    title: str,
    body: Optional[str] = None,
    kind: Optional[str] = None,
    source: str = "agent",
    payload: Optional[Dict[str, Any]] = None,
    priority: Optional[str] = None,
    score: Optional[int] = None,
    status: str = ItemStatus.PENDING_APPROVAL,
    actor: str = "agent",
    reason: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a spine item (PENDING_APPROVAL by default) + an audit row; return its id.

    Spine fields are set directly; `score` and any `extra` domain fields are
    applied only if the model actually has that column (so the same helper works
    across Lead/Ticket/Invoice/… without knowing their domain columns). The
    caller owns the session lifecycle; this commits.
    """
    item = Model(
        user_id=user_id,
        title=title,
        body=body,
        kind=kind,
        source=source,
        payload=payload,
        status=status,
        priority=priority or derive_priority(score),
    )
    if score is not None and hasattr(item, "score"):
        item.score = score
    for key, value in (extra or {}).items():
        if hasattr(item, key):
            setattr(item, key, value)

    db.add(item)
    db.flush()  # assign id before auditing
    record_audit(
        db, item=item, action="drafted", actor=actor,
        after={"status": status, "score": score}, detail=reason,
    )
    db.commit()
    return item.id
