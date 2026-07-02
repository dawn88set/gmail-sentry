"""
Gmail Sentry API routes (the regenerable API layer).

The frontend client at frontend/src/lib/api.ts calls exactly these routes — keep
the two in sync (paths, methods, response shapes). backend/main.py auto-includes
`router`. ALWAYS keep `GET /api/widget`.

Multi-tenancy: the caller is `user_id: str = Depends(require_user)` (edge-verified;
"dev-user" locally). Every query filters by user_id. External actions go through
the bundled Gmail/Slack adapters, which raise IntegrationNotConnected → we map to
HTTP 409 (the UI turns it into a connect prompt). We never fake success.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List
from datetime import datetime, timedelta
from urllib.parse import quote
import logging

from backend.database import get_db
from backend.security import require_user
from backend import models
from backend.services.sentry import run_scan, get_config
from backend.services.reply import draft_reply
from backend.shared.adapters import IntegrationNotConnected, IntegrationError
from backend.integrations import gmail_ops as gmail_adapter
from backend.integrations import notify

logger = logging.getLogger(__name__)

router = APIRouter()

TIER_RANK = {"urgent": 2, "needs_reply": 1, "fyi": 0}
_CLEANUP_QUERY = {
    "promotions": "category:promotions",
    "social": "category:social",
    "spam": "in:spam",
}


def _relative_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "never"
    secs = max(0, int((datetime.utcnow() - dt).total_seconds()))
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = secs // 60
        return f"{m} min{'s' if m != 1 else ''} ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = secs // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


def _latest_run(db: Session, user_id: str) -> Optional[models.ScanRun]:
    return (
        db.query(models.ScanRun)
        .filter(models.ScanRun.user_id == user_id)
        .order_by(models.ScanRun.started_at.desc())
        .first()
    )


def _not_connected(service: str):
    raise HTTPException(
        status_code=409,
        detail=(
            f"{service.capitalize()} isn't connected — connect or reconnect it on the "
            "Integrations tab."
        ),
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def _active_filter(q):
    """Alerts that should currently demand attention: new/seen, plus snoozed ones
    whose snooze time has passed. Excludes done/dismissed and still-snoozed."""
    now = datetime.utcnow()
    return q.filter(
        or_(
            models.Alert.status.in_(("new", "seen")),
            (models.Alert.status == "snoozed") & (models.Alert.snoozed_until <= now),
        )
    )


def _get_alert(db, alert_id, user_id) -> models.Alert:
    alert = (
        db.query(models.Alert)
        .filter(models.Alert.id == alert_id, models.Alert.user_id == user_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/api/alerts")
async def list_alerts(
    status: str = "active",
    tier: Optional[str] = None,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The caller's alerts. status=active (default) shows what needs attention;
    also supports snoozed | done | all. Optional tier filter (urgent|needs_reply)."""
    q = db.query(models.Alert).filter(models.Alert.user_id == user_id)
    now = datetime.utcnow()
    if status == "active":
        q = _active_filter(q)
    elif status == "snoozed":
        q = q.filter(models.Alert.status == "snoozed", models.Alert.snoozed_until > now)
    elif status == "done":
        q = q.filter(models.Alert.status == "done")
    # status == "all" → no status filter
    if tier in ("urgent", "needs_reply", "fyi"):
        q = q.filter(models.Alert.tier == tier)
    alerts = q.order_by(models.Alert.created_at.desc()).limit(200).all()
    alerts.sort(key=lambda a: TIER_RANK.get(a.tier, 0), reverse=True)
    return {"alerts": [a.to_dict() for a in alerts]}


@router.post("/api/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    alert = _get_alert(db, alert_id, user_id)
    alert.status = "dismissed"
    db.commit()
    return {"success": True}


@router.post("/api/alerts/{alert_id}/done")
async def done_alert(alert_id: str, user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    alert = _get_alert(db, alert_id, user_id)
    alert.status = "done"
    db.commit()
    return {"success": True}


class SnoozeBody(BaseModel):
    hours: int = 3


@router.post("/api/alerts/{alert_id}/snooze")
async def snooze_alert(
    alert_id: str, body: SnoozeBody, user_id: str = Depends(require_user), db: Session = Depends(get_db)
):
    alert = _get_alert(db, alert_id, user_id)
    hours = max(1, min(int(body.hours or 3), 24 * 14))
    alert.status = "snoozed"
    alert.snoozed_until = datetime.utcnow() + timedelta(hours=hours)
    db.commit()
    return {"success": True, "snoozed_until": alert.snoozed_until.isoformat()}


@router.post("/api/alerts/{alert_id}/mute")
async def mute_alert(alert_id: str, user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    """Mute this sender (never flag them again) and dismiss the alert."""
    alert = _get_alert(db, alert_id, user_id)
    # Extract a stable sender key (email if present, else raw).
    import re as _re

    m = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", alert.sender or "")
    key = (m.group(0) if m else (alert.sender or "")).lower().strip()
    cfg = get_config(db, user_id)
    muted = list(cfg.muted_senders or [])
    if key and key not in muted:
        muted.append(key)
        cfg.muted_senders = muted
    alert.status = "dismissed"
    db.commit()
    return {"success": True, "muted": key}


def _voice_samples(db, user_id: str, limit: int = 6) -> list:
    """Excerpts of the user's own recent sent emails, to match their voice.
    Best-effort — returns [] if Gmail isn't connected or the read fails."""
    samples: list = []
    try:
        stubs = gmail_adapter.search(db, user_id, "in:sent", max_results=limit)
        for stub in stubs[:limit]:
            mid = stub.get("id")
            if not mid:
                continue
            try:
                meta = gmail_adapter.get_meta(db, user_id, mid)
            except IntegrationError:
                continue
            snip = (meta.get("snippet") or "").strip()
            if snip:
                samples.append(snip)
    except (IntegrationNotConnected, IntegrationError):
        return []
    return samples


@router.post("/api/alerts/{alert_id}/draft-reply")
async def draft_reply_alert(alert_id: str, user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    """Draft a reply (human-in-the-loop) in the user's own voice, and return a
    Gmail compose deep link."""
    alert = _get_alert(db, alert_id, user_id)
    samples = _voice_samples(db, user_id)
    draft = draft_reply(alert.sender or "", alert.subject or "", alert.snippet or "", style_samples=samples)
    m = None
    import re as _re

    match = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", alert.sender or "")
    to = match.group(0) if match else ""
    su = alert.subject or ""
    if su and not su.lower().startswith("re:"):
        su = f"Re: {su}"
    compose_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(to)}&su={quote(su)}&body={quote(draft)}"
    )
    return {"draft": draft, "compose_url": compose_url, "voice_matched": len(samples) > 0}


class AlertRuleBody(BaseModel):
    tier: str = "urgent"


@router.post("/api/alerts/{alert_id}/create-rule")
async def create_rule_from_alert(
    alert_id: str, body: AlertRuleBody, user_id: str = Depends(require_user), db: Session = Depends(get_db)
):
    """Turn this alert's sender into a VIP-sender urgency rule."""
    alert = _get_alert(db, alert_id, user_id)
    import re as _re

    match = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", alert.sender or "")
    value = (match.group(0) if match else (alert.sender or "")).lower().strip()
    if not value:
        raise HTTPException(status_code=400, detail="No sender to build a rule from")
    tier = body.tier if body.tier in TIER_RANK else "urgent"
    name = alert.sender.split("<")[0].strip().strip('"') if alert.sender else value
    rule = models.TriageRule(
        user_id=user_id, name=f"From {name or value}", kind="vip_sender", value=value, tier=tier
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


# ---------------------------------------------------------------------------
# Triage rules
# ---------------------------------------------------------------------------


class TriageRuleCreate(BaseModel):
    name: str
    kind: str = "nl"  # nl | vip_sender | keyword
    value: str
    tier: str = "urgent"  # urgent | needs_reply | fyi


@router.get("/api/rules")
async def list_rules(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    rules = (
        db.query(models.TriageRule)
        .filter(models.TriageRule.user_id == user_id)
        .order_by(models.TriageRule.created_at.desc())
        .all()
    )
    return {"rules": [r.to_dict() for r in rules]}


@router.post("/api/rules")
async def create_rule(
    payload: TriageRuleCreate,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    name = (payload.name or "").strip()
    value = (payload.value or "").strip()
    if not name or not value:
        raise HTTPException(status_code=400, detail="Rule name and value are required")
    if payload.kind not in ("nl", "vip_sender", "keyword"):
        raise HTTPException(status_code=400, detail="Invalid rule kind")
    if payload.tier not in TIER_RANK:
        raise HTTPException(status_code=400, detail="Invalid tier")
    rule = models.TriageRule(
        user_id=user_id, name=name, kind=payload.kind, value=value, tier=payload.tier
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.post("/api/rules/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    rule = (
        db.query(models.TriageRule)
        .filter(models.TriageRule.id == rule_id, models.TriageRule.user_id == user_id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.active = not rule.active
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/api/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    rule = (
        db.query(models.TriageRule)
        .filter(models.TriageRule.id == rule_id, models.TriageRule.user_id == user_id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# Label (filing) rules
# ---------------------------------------------------------------------------


class LabelRuleCreate(BaseModel):
    name: str
    match_type: str = "sender"  # sender | domain | subject_keyword
    match_value: str
    target_label: str
    archive_after: bool = False


@router.get("/api/label-rules")
async def list_label_rules(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    rules = (
        db.query(models.LabelRule)
        .filter(models.LabelRule.user_id == user_id)
        .order_by(models.LabelRule.created_at.desc())
        .all()
    )
    return {"label_rules": [r.to_dict() for r in rules]}


@router.post("/api/label-rules")
async def create_label_rule(
    payload: LabelRuleCreate,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    name = (payload.name or "").strip()
    match_value = (payload.match_value or "").strip()
    target_label = (payload.target_label or "").strip()
    if not (name and match_value and target_label):
        raise HTTPException(status_code=400, detail="Name, match value, and label are required")
    if payload.match_type not in ("sender", "domain", "subject_keyword"):
        raise HTTPException(status_code=400, detail="Invalid match type")
    rule = models.LabelRule(
        user_id=user_id,
        name=name,
        match_type=payload.match_type,
        match_value=match_value,
        target_label=target_label,
        archive_after=bool(payload.archive_after),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.post("/api/label-rules/{rule_id}/toggle")
async def toggle_label_rule(
    rule_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    rule = (
        db.query(models.LabelRule)
        .filter(models.LabelRule.id == rule_id, models.LabelRule.user_id == user_id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Label rule not found")
    rule.active = not rule.active
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/api/label-rules/{rule_id}")
async def delete_label_rule(
    rule_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    rule = (
        db.query(models.LabelRule)
        .filter(models.LabelRule.id == rule_id, models.LabelRule.user_id == user_id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Label rule not found")
    db.delete(rule)
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class ConfigUpdate(BaseModel):
    slack_channel: Optional[str] = None
    notify_tier: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    teams_chat_id: Optional[str] = None
    whatsapp_to: Optional[str] = None


@router.get("/api/config")
async def get_settings(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    return get_config(db, user_id).to_dict()


@router.put("/api/config")
async def update_settings(
    payload: ConfigUpdate,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    cfg = get_config(db, user_id)
    if payload.slack_channel is not None:
        cfg.slack_channel = payload.slack_channel.strip()
    if payload.notify_tier is not None:
        if payload.notify_tier not in ("urgent", "needs_reply"):
            raise HTTPException(status_code=400, detail="Invalid notify tier")
        cfg.notify_tier = payload.notify_tier
    if payload.telegram_chat_id is not None:
        cfg.telegram_chat_id = payload.telegram_chat_id.strip()
    if payload.discord_channel_id is not None:
        cfg.discord_channel_id = payload.discord_channel_id.strip()
    if payload.teams_chat_id is not None:
        cfg.teams_chat_id = payload.teams_chat_id.strip()
    if payload.whatsapp_to is not None:
        cfg.whatsapp_to = payload.whatsapp_to.strip()
    db.commit()
    db.refresh(cfg)
    return cfg.to_dict()


class NotifyTest(BaseModel):
    channel: Optional[str] = None  # None → test every configured channel


@router.post("/api/notify/test")
async def notify_test(
    payload: NotifyTest,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Send a test alert to a channel (or all configured) and return a detailed
    per-channel result so the user can verify delivery + see the exact error."""
    cfg = get_config(db, user_id)
    results = notify.test_notify(db, user_id, cfg, only=(payload.channel or ""))
    return {"results": results}


@router.get("/api/integrations/slack/channels")
async def slack_channels(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Channels the connected Slack bot can see, so the user PICKS one instead of
    typing a name (free-text names cause `channel_not_found`). Returns
    ``{connected, channels:[{id,name}]}``; a not-connected Slack yields
    ``connected: false`` (not an error) so the UI can prompt to connect."""
    from backend.shared.adapters import execute_tool

    try:
        res = execute_tool("slack", "list_channels", user_id, {})
        chans = res.get("channels", []) if isinstance(res, dict) else []
        # Sort by name for a predictable dropdown.
        chans = sorted(
            [{"id": c.get("id", ""), "name": c.get("name", "")} for c in chans if c.get("id")],
            key=lambda c: c["name"].lower(),
        )
        return {"connected": True, "channels": chans}
    except IntegrationNotConnected:
        return {"connected": False, "channels": []}
    except IntegrationError as e:
        # Surface the real reason (e.g. missing channels:read scope) but don't 500.
        return {"connected": True, "channels": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Cleanup (Promotions / Social / Spam)
# ---------------------------------------------------------------------------


class CleanupClear(BaseModel):
    category: str  # promotions | social | spam
    action: str = "trash"  # trash (recoverable) | archive (remove from inbox)
    limit: int = 200  # legacy; ignored by the batched clear


@router.get("/api/cleanup")
async def get_cleanup(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Latest known category sizes (snapshot from the last scan) + scan time."""
    run = _latest_run(db, user_id)
    return {
        "promotions": (run.promo_count if run else 0) or 0,
        "social": (run.social_count if run else 0) or 0,
        "spam": (run.spam_count if run else 0) or 0,
        "last_scan": _relative_time(run.started_at if run else None),
    }


@router.post("/api/cleanup/clear")
async def clear_category(
    payload: CleanupClear,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk-clear a junk category. Archives (removes from inbox) or trashes the
    matching messages. Returns how many were cleared + the remaining count."""
    category = payload.category.lower()
    if category not in _CLEANUP_QUERY:
        raise HTTPException(status_code=400, detail="Unknown category")
    action = payload.action if payload.action in ("archive", "trash") else "trash"
    # Spam is always trashed (it's already out of the inbox).
    if category == "spam":
        action = "trash"

    base_q = _CLEANUP_QUERY[category]
    if action == "trash":
        # Trashed mail leaves the category query → this is idempotent and the
        # full-category count drops. Bulk-trash = add TRASH + remove INBOX.
        query, add, remove = base_q, ["TRASH"], ["INBOX"]
    else:
        # Archive removes from the inbox only; scope to in:inbox so it terminates
        # (removing INBOX drops them from the query) and doesn't re-list forever.
        query, add, remove = f"{base_q} in:inbox", None, ["INBOX"]

    # Batched + paginated mass clear. One request processes up to MAX_PER_CALL
    # messages (list in 500s, modify in Gmail's 1000-id batches); if more remain,
    # `done=False` and the client calls again (each call re-lists from the top —
    # already-cleared mail no longer matches, so it converges).
    PAGE, BATCH, MAX_PER_CALL = 500, 1000, 5000
    try:
        ids: List[str] = []
        page_token = ""
        while len(ids) < MAX_PER_CALL:
            page = gmail_adapter.list_page(db, user_id, query, max_results=PAGE, page_token=page_token)
            ids.extend(s["id"] for s in page.get("messages", []) if s.get("id"))
            page_token = page.get("nextPageToken") or ""
            if not page_token:
                break
        ids = ids[:MAX_PER_CALL]

        cleared = 0
        for i in range(0, len(ids), BATCH):
            cleared += gmail_adapter.batch_modify(
                db, user_id, ids[i : i + BATCH], add=add, remove=remove
            )
        remaining = gmail_adapter.count(db, user_id, base_q)
    except IntegrationNotConnected:
        return _not_connected("gmail")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=f"Gmail error: {e}")

    # More to do only if we stopped because we hit the per-call cap with pages
    # still pending. cleared==0 → nothing matched (or all failed) → stop.
    done = (not page_token) or (cleared == 0)

    # Update the snapshot on the latest run so the widget reflects the change.
    run = _latest_run(db, user_id)
    if run is not None:
        attr = {"promotions": "promo_count", "social": "social_count", "spam": "spam_count"}[category]
        setattr(run, attr, remaining)
        db.commit()

    return {
        "cleared": cleared,
        "remaining": remaining,
        "done": done,
        "category": category,
        "action": action,
    }


@router.get("/api/cleanup/{category}/messages")
async def category_messages(
    category: str,
    page_token: str = "",
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """A page of the actual messages in a junk category (so the user can see
    exactly what 'Clear all' will affect). Infinite-scroll via next_page_token."""
    category = category.lower()
    if category not in _CLEANUP_QUERY:
        raise HTTPException(status_code=400, detail="Unknown category")
    try:
        page = gmail_adapter.list_page(db, user_id, _CLEANUP_QUERY[category], max_results=20, page_token=page_token)
        messages = []
        for stub in page.get("messages", []):
            mid = stub.get("id")
            if not mid:
                continue
            try:
                meta = gmail_adapter.get_meta(db, user_id, mid)
            except IntegrationError:
                continue
            messages.append({
                "id": mid,
                "sender": meta.get("sender", ""),
                "subject": meta.get("subject", "") or "(no subject)",
                "snippet": meta.get("snippet", ""),
            })
        return {"messages": messages, "next_page_token": page.get("nextPageToken")}
    except IntegrationNotConnected:
        return _not_connected("gmail")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=f"Gmail error: {e}")


# ---------------------------------------------------------------------------
# Scan now
# ---------------------------------------------------------------------------


@router.post("/api/scan/run")
async def scan_now(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Run an inbox scan immediately (the same engine the schedule uses)."""
    try:
        return run_scan(db, user_id)
    except IntegrationNotConnected:
        return _not_connected("gmail")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=f"Gmail error: {e}")
    except Exception as e:  # noqa: BLE001 — never surface a raw 500 to the widget
        logger.exception("scan failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=502, detail=f"Scan couldn’t complete: {e}")


# ---------------------------------------------------------------------------
# Widget — REQUIRED by the Claritty platform
# ---------------------------------------------------------------------------


@router.get("/api/widget")
async def get_widget_data(
    size: str = "large",
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The glance: urgent count, last scan, top alerts, and cleanup counts."""
    try:
        active = (
            _active_filter(db.query(models.Alert).filter(models.Alert.user_id == user_id))
            .order_by(models.Alert.created_at.desc())
            .limit(50)
            .all()
        )
        urgent = [a for a in active if a.tier == "urgent"]
        needs_reply = [a for a in active if a.tier == "needs_reply"]
        ranked = sorted(active, key=lambda a: TIER_RANK.get(a.tier, 0), reverse=True)

        run = _latest_run(db, user_id)
        cfg = (
            db.query(models.SentryConfig)
            .filter(models.SentryConfig.user_id == user_id)
            .first()
        )

        top_alerts = [
            {
                "id": a.id,
                "subject": a.subject or "(no subject)",
                "sender": a.sender or "",
                "tier": a.tier,
                "reason": a.reason or "",
                "deep_link": a.deep_link or "",
            }
            for a in ranked[:3]
        ]

        return {
            "urgent_count": len(urgent),
            "needs_reply_count": len(needs_reply),
            "all_clear": len(urgent) == 0 and len(needs_reply) == 0,
            "last_scan": _relative_time(run.started_at if run else None),
            "top_alerts": top_alerts,
            "cleanup": {
                "promo": (run.promo_count if run else 0) or 0,
                "social": (run.social_count if run else 0) or 0,
                "spam": (run.spam_count if run else 0) or 0,
            },
            "slack_configured": bool(cfg and cfg.slack_channel),
        }
    except Exception:
        logger.exception("widget data build failed; returning empty payload")
        return {
            "urgent_count": 0,
            "needs_reply_count": 0,
            "all_clear": True,
            "last_scan": "never",
            "top_alerts": [],
            "cleanup": {"promo": 0, "social": 0, "spam": 0},
            "slack_configured": False,
        }
