"""
App-specific API routes (the regenerable API layer).

This file is the SINGLE place app data endpoints live. The frontend client at
frontend/src/lib/api.ts calls exactly these routes — keep the two in sync (same
paths, methods, and response shapes). backend/main.py auto-includes `router`.

Generated apps OVERWRITE this file with their own endpoints. The default below
is a self-contained "Tasks" example — replace it for your app, but ALWAYS keep
a `GET /api/widget` that returns the data your frontend Widget renders.

Conventions:
- Multi-tenancy: get the caller with `user_id: str = Depends(require_user)`
  (from backend.security) — the edge-verified identity. NEVER read X-User-ID by
  hand and NEVER fall back to a shared default like "test-user" (that silently
  merges every user's data). Filter EVERY query by `user_id`.
- Query backend.models with SQLAlchemy via the `db` dependency.
- Return plain dicts/lists (FastAPI serializes to JSON).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from backend.database import get_db
from backend.security import require_user
from backend import models

logger = logging.getLogger(__name__)

router = APIRouter()

PRIORITY_RANK = {"urgent": 3, "high": 2, "medium": 1, "low": 0}


async def prioritize_task(title: str, notes: str = "") -> dict:
    """Safe, dependency-free task enrichment used at create time.

    The v1 helper this replaces lived in backend/agents/example_agent.py, which
    became a v2 manifest-first agent class (no module-level function) — leaving
    this route importing a symbol that no longer exists and silently failing to
    register (every /api/* route, incl. the required /api/widget, 404'd). This
    local fallback keeps the example self-contained and the router always live;
    a generated app wires real AI prioritization through an agent/workflow.
    """
    text = f"{title} {notes}".lower()
    if any(w in text for w in ("urgent", "asap", "critical", "today", "now")):
        priority = "urgent"
    elif any(w in text for w in ("important", "high", "deadline", "soon")):
        priority = "high"
    elif any(w in text for w in ("someday", "maybe", "later", "low priority")):
        priority = "low"
    else:
        priority = "medium"
    return {"priority": priority, "suggested_action": None}


def _relative_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "no tasks yet"
    delta = datetime.utcnow() - dt
    secs = max(0, int(delta.total_seconds()))
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


# ---------------------------------------------------------------------------
# Tasks CRUD
# ---------------------------------------------------------------------------


class TaskCreate(BaseModel):
    title: str
    notes: Optional[str] = None


@router.get("/api/tasks")
async def list_tasks(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List the caller's tasks — open first, then by newest."""
    tasks = (
        db.query(models.Task)
        .filter(models.Task.user_id == user_id)
        .order_by(models.Task.done.asc(), models.Task.created_at.desc())
        .all()
    )
    return {"tasks": [t.to_dict() for t in tasks]}


@router.post("/api/tasks")
async def create_task(
    payload: TaskCreate,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Create a task. The prioritize-task agent (Claude, with a safe local
    fallback) sets the priority + a suggested next action at create time.
    """
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required")

    enrichment = await prioritize_task(title, payload.notes or "")

    task = models.Task(
        user_id=user_id,
        title=title,
        notes=payload.notes,
        priority=enrichment.get("priority", "medium"),
        suggested_action=enrichment.get("suggested_action"),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info(f"Created task {task.id} (priority={task.priority}) for {user_id}")
    return task.to_dict()


@router.post("/api/tasks/{task_id}/toggle")
async def toggle_task(
    task_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Toggle a task's done state (owner-scoped)."""
    task = (
        db.query(models.Task)
        .filter(models.Task.id == task_id, models.Task.user_id == user_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.done = not task.done
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete a task (owner-scoped)."""
    task = (
        db.query(models.Task)
        .filter(models.Task.id == task_id, models.Task.user_id == user_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# Widget — REQUIRED by the Claritty platform
# ---------------------------------------------------------------------------


@router.get("/api/widget")
async def get_widget_data(
    size: str = "large",
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Widget data endpoint. Returns a summary of the caller's tasks. Supports
    small | medium | large. Replace the body for your app, but keep the route.
    """
    try:
        open_tasks = (
            db.query(models.Task)
            .filter(models.Task.user_id == user_id, models.Task.done == False)  # noqa: E712
            .order_by(models.Task.created_at.desc())
            .all()
        )
        open_tasks.sort(key=lambda t: PRIORITY_RANK.get(t.priority, 1), reverse=True)

        last = (
            db.query(models.Task)
            .filter(models.Task.user_id == user_id)
            .order_by(models.Task.updated_at.desc())
            .first()
        )
        last_updated = _relative_time(last.updated_at if last else None)

        # "Done today" — honest: completed tasks whose last change was today (UTC),
        # not the all-time completed count.
        start_of_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        done_today = (
            db.query(models.Task)
            .filter(
                models.Task.user_id == user_id,
                models.Task.done == True,  # noqa: E712
                models.Task.updated_at >= start_of_today,
            )
            .count()
        )

        open_count = len(open_tasks)
        top_priority = open_tasks[0].priority if open_tasks else None

        if size == "small":
            return {
                "open_count": open_count,
                "top_priority": top_priority,
                "top_task": open_tasks[0].title if open_tasks else None,
                "top_task_id": open_tasks[0].id if open_tasks else None,
                "last_updated": last_updated,
            }

        return {
            "open_count": open_count,
            "done_today": done_today,
            "top_priority": top_priority,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "done": t.done,
                    # Used by the large widget's richer rows; harmless for medium.
                    "suggested_action": t.suggested_action,
                }
                for t in open_tasks[:8]
            ],
            "last_updated": last_updated,
        }
    except Exception:
        # A widget is rendered in a tiny dashboard iframe — it must NEVER 500.
        # On ANY data/DB/model error (a bad query, a missing column, a model
        # attribute that doesn't exist), log it and return a calm EMPTY payload
        # so the widget shows its empty state instead of a broken tile.
        logger.exception("widget data build failed; returning empty payload")
        empty = {
            "open_count": 0,
            "top_priority": None,
            "top_task": None,
            "top_task_id": None,
            "last_updated": _relative_time(None),
        }
        if size != "small":
            empty["done_today"] = 0
            empty["tasks"] = []
        return empty
