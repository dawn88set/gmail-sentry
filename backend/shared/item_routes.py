"""
B2 — Item/lifecycle route factory + human-in-the-loop approval.

`make_item_router(Model, publish=...)` returns a FastAPI router with the API
every department app needs, so an app's backend/routes/app.py shrinks to a few
lines:

    from backend.shared.item_routes import make_item_router
    from backend.shared.adapters import gmail
    from backend import models

    def _send(db, user_id, item):
        return gmail.send(db, user_id, to=item.payload["to"], subject=item.title, body=item.body)

    router = make_item_router(models.Lead, publish=_send, kind="lead")

Endpoints (all owner-scoped via require_user; every query filters user_id):
    GET    /api/items            list (optional ?status= &kind=)
    GET    /api/items/{id}       one item
    POST   /api/items/{id}/edit  revise a draft (title/body/payload)
    POST   /api/items/{id}/approve  HONEST publish via the app's `publish` callable
    POST   /api/items/{id}/reject   user declines
    GET    /api/widget          summary the B5 widgets render

The `/approve` handler is the whole point: it performs the real external action
and only then flips status — encoding the platform's non-negotiable rule
(INTEGRATIONS.md): not-connected → 409, real failure → 5xx (row stays open),
genuine external id → published. It can never fake success because the status
flip is gated on `publish` returning an `external_id`.

`publish` contract — a callable `(db, user_id, item) -> dict` returning at least
`{"external_id": "<id>"}` (optionally `{"account": "..."}`). It must raise
`IntegrationNotConnected` when the service isn't connected and `IntegrationError`
(or any exception) on a real failure. Omit `publish` for read-only/no-external
apps: approve then just marks the item approved/published locally.
"""

from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.security import require_user
from backend.shared.spine import ItemStatus, PRIORITY_RANK, record_audit
from backend.shared.adapters import IntegrationNotConnected, IntegrationError

PublishFn = Callable[[Session, str, Any], dict]


def _relative_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "never"
    secs = max(0, int((datetime.utcnow() - dt).total_seconds()))
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = secs // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = secs // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


class EditBody(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    payload: Optional[dict] = None


def make_item_router(
    Model,
    *,
    publish: Optional[PublishFn] = None,
    kind: Optional[str] = None,
    serialize: Optional[Callable[[Any], dict]] = None,
    widget_title: Optional[str] = None,
) -> APIRouter:
    """Build the standard item lifecycle router for `Model`.

    Args:
        Model: a SQLAlchemy model using ItemMixin + LifecycleMixin.
        publish: callable performing the external action on approve (see module
            docstring). If None, approve just flips status locally.
        kind: optional default `kind` filter for this app's items.
        serialize: row -> dict (defaults to `Model.to_dict`).
        widget_title: optional label echoed in the widget payload.
    """
    router = APIRouter()
    to_dict = serialize or (lambda row: row.to_dict())

    def _owned(db: Session, user_id: str, item_id: str):
        q = db.query(Model).filter(Model.id == item_id, Model.user_id == user_id)
        item = q.first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item

    def _base_query(db: Session, user_id: str):
        q = db.query(Model).filter(Model.user_id == user_id)
        if kind is not None and hasattr(Model, "kind"):
            q = q.filter(Model.kind == kind)
        return q

    # ----- list / read -----------------------------------------------------
    @router.get("/api/items")
    async def list_items(
        status: Optional[str] = None,
        user_id: str = Depends(require_user),
        db: Session = Depends(get_db),
    ):
        q = _base_query(db, user_id)
        if status:
            q = q.filter(Model.status == status)
        rows = q.order_by(Model.created_at.desc()).all()
        # Open items first, then by priority, then newest (Python-side so it
        # works across SQLite/Postgres without a CASE expression).
        rows.sort(
            key=lambda r: (
                r.status in ItemStatus.CLOSED,             # open before closed
                -PRIORITY_RANK.get(r.priority, 1),         # higher priority first
            )
        )
        return {"items": [to_dict(r) for r in rows]}

    @router.get("/api/items/{item_id}")
    async def get_item(
        item_id: str,
        user_id: str = Depends(require_user),
        db: Session = Depends(get_db),
    ):
        return to_dict(_owned(db, user_id, item_id))

    # ----- edit a draft ----------------------------------------------------
    @router.post("/api/items/{item_id}/edit")
    async def edit_item(
        item_id: str,
        body: EditBody,
        user_id: str = Depends(require_user),
        db: Session = Depends(get_db),
    ):
        item = _owned(db, user_id, item_id)
        if item.status in ItemStatus.CLOSED:
            raise HTTPException(status_code=409, detail=f"Item is {item.status}; cannot edit.")
        before = {"title": item.title, "body": item.body}
        if body.title is not None:
            item.title = body.title
        if body.body is not None:
            item.body = body.body
        if body.payload is not None:
            merged = dict(item.payload or {})
            merged.update(body.payload)
            item.payload = merged
        # Editing implies the draft is now awaiting a decision.
        if item.status in (ItemStatus.NEW, ItemStatus.TRIAGED, ItemStatus.DRAFT):
            item.status = ItemStatus.PENDING_APPROVAL
        record_audit(
            db, item=item, action="edited", actor=f"user:{user_id}",
            before=before, after={"title": item.title, "body": item.body},
        )
        db.commit()
        db.refresh(item)
        return to_dict(item)

    # ----- approve = HONEST publish ---------------------------------------
    @router.post("/api/items/{item_id}/approve")
    async def approve_item(
        item_id: str,
        user_id: str = Depends(require_user),
        db: Session = Depends(get_db),
    ):
        item = _owned(db, user_id, item_id)
        if item.status == ItemStatus.PUBLISHED:
            raise HTTPException(status_code=409, detail="Item is already published.")
        if item.status == ItemStatus.REJECTED:
            raise HTTPException(status_code=409, detail="Item was rejected.")

        # No external action for this app: approving just records the decision.
        if publish is None:
            item.status = ItemStatus.PUBLISHED
            item.published_at = datetime.utcnow()
            record_audit(db, item=item, action="approved", actor=f"user:{user_id}")
            db.commit()
            db.refresh(item)
            return to_dict(item)

        prior = item.status
        # Do NOT change status before the external action succeeds — an adapter
        # may commit mid-call (e.g. persisting a refreshed token), which would
        # otherwise leak an intermediate status. Only the outcome flips status.
        try:
            result = publish(db, user_id, item) or {}
        except IntegrationNotConnected as e:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail={"error": "not_connected", "service": e.service, "message": str(e)},
            )
        except (IntegrationError, Exception) as e:  # noqa: BLE001 — honest failure
            db.rollback()
            item = _owned(db, user_id, item_id)
            item.status = ItemStatus.FAILED
            item.error_message = str(e)
            record_audit(
                db, item=item, action="dispatch_failed",
                actor=f"user:{user_id}", detail=str(e),
            )
            db.commit()
            raise HTTPException(status_code=502, detail=f"Publish failed: {e}")

        external_id = result.get("external_id")
        if not external_id:
            # A publish that didn't return a real id is NOT a success.
            db.rollback()
            item = _owned(db, user_id, item_id)
            item.status = ItemStatus.FAILED
            item.error_message = "publish returned no external id"
            record_audit(
                db, item=item, action="dispatch_failed", actor=f"user:{user_id}",
                detail="no external id",
            )
            db.commit()
            raise HTTPException(status_code=502, detail="Publish did not return an external id.")

        before = {"status": prior}
        item.external_id = str(external_id)
        item.published_at = datetime.utcnow()
        item.status = ItemStatus.PUBLISHED
        record_audit(
            db, item=item, action="published", actor=f"user:{user_id}",
            before=before, after={"status": item.status, "external_id": item.external_id},
            detail=result.get("account"),
        )
        db.commit()
        db.refresh(item)
        return to_dict(item)

    # ----- reject ----------------------------------------------------------
    @router.post("/api/items/{item_id}/reject")
    async def reject_item(
        item_id: str,
        user_id: str = Depends(require_user),
        db: Session = Depends(get_db),
    ):
        item = _owned(db, user_id, item_id)
        if item.status == ItemStatus.PUBLISHED:
            raise HTTPException(status_code=409, detail="Item is already published.")
        item.status = ItemStatus.REJECTED
        record_audit(db, item=item, action="rejected", actor=f"user:{user_id}")
        db.commit()
        db.refresh(item)
        return to_dict(item)

    # ----- widget (REQUIRED by the platform) ------------------------------
    @router.get("/api/widget")
    async def get_widget_data(
        size: str = "large",
        user_id: str = Depends(require_user),
        db: Session = Depends(get_db),
    ):
        rows = _base_query(db, user_id).all()
        open_rows = [r for r in rows if r.status not in ItemStatus.CLOSED]
        open_rows.sort(key=lambda r: -PRIORITY_RANK.get(r.priority, 1))
        pending = [r for r in open_rows if r.status == ItemStatus.PENDING_APPROVAL]

        start_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        published_today = sum(
            1 for r in rows
            if r.status == ItemStatus.PUBLISHED and r.published_at and r.published_at >= start_today
        )
        last_dt = max((r.updated_at for r in rows if r.updated_at), default=None)
        top = open_rows[0] if open_rows else None

        common = {
            "title": widget_title,
            "open_count": len(open_rows),
            "pending_count": len(pending),
            "published_today": published_today,
            "last_updated": _relative_time(last_dt),
        }

        if size == "small":
            return {
                **common,
                "top_title": top.title if top else None,
                "top_id": top.id if top else None,
                "top_priority": top.priority if top else None,
            }

        by_status = {}
        for r in rows:
            by_status[r.status] = by_status.get(r.status, 0) + 1
        return {
            **common,
            "by_status": by_status,
            "items": [
                {
                    "id": r.id,
                    "title": r.title,
                    "status": r.status,
                    "priority": r.priority,
                    "body": (r.body[:140] if r.body else None),
                }
                for r in open_rows[:8]
            ],
        }

    return router
