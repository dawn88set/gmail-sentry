"""Gmail Sentry tools.

`app.run_inbox_scan` runs the full scan engine for the calling user. The agent
(and, on-platform, the scheduled workflow) call this; locally the route
POST /api/scan/run calls the same `run_scan` engine directly.
"""
from typing import Any, Dict

from claritty_sdk import tool, ToolCtx

from backend.database import SessionLocal
from backend.services.sentry import run_scan
from backend.services.digest import run_digest
from backend.shared.adapters import IntegrationNotConnected


@tool(id="app.run_inbox_scan")
def run_inbox_scan(input: Dict[str, Any], ctx: ToolCtx) -> Dict[str, Any]:
    """Scan the user's inbox: triage new mail, file by label rules, raise alerts,
    and Slack-ping urgent ones. Returns a summary of what happened."""
    uid = getattr(ctx, "user_id", None) or (input or {}).get("user_id")
    if not uid:
        return {"ok": False, "error": "no_user"}
    db = SessionLocal()
    try:
        summary = run_scan(db, uid, respect_interval=True)
        summary["ok"] = True
        return summary
    except IntegrationNotConnected:
        # Honest not-connected signal — never a faked success.
        return {"ok": False, "error": "gmail_not_connected"}
    finally:
        db.close()


@tool(id="app.send_digest")
def send_digest(input: Dict[str, Any], ctx: ToolCtx) -> Dict[str, Any]:
    """Send the user's inbox digest (a grouped report of urgent + to-reply mail,
    with one-tap approve links) to every configured channel. Sends nothing when
    the inbox is calm. Returns a delivery summary."""
    uid = getattr(ctx, "user_id", None) or (input or {}).get("user_id")
    if not uid:
        return {"ok": False, "error": "no_user"}
    db = SessionLocal()
    try:
        return run_digest(db, uid)
    finally:
        db.close()
