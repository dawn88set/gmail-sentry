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
from sqlalchemy import or_, func
from typing import Optional, List
from datetime import datetime, timedelta
from urllib.parse import quote
import logging
import re
import time

from backend.database import get_db
from backend.security import require_user
from backend import models
from backend.services.sentry import run_scan, get_config
from backend.services.reply import draft_reply, style_for
from backend.services.learn import get_profile, learn_patterns
from backend.shared.adapters import IntegrationNotConnected, IntegrationError
from backend.services import activity
from backend.services import mail as mail_service
from backend.services import worklist as worklist_service
from backend.services import insights as insights_service
from backend.services import accounts as accounts_service
from backend.services import counterparty as counterparty_service
from backend.services import ledger
from backend.services import followups
from backend.services import filing
from backend.services import nudges
from backend.services.reply import split_fallback as nudges_split
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


def _sender_email(sender: str) -> str:
    """The bare email address out of a "Name <a@b.com>" sender string."""
    import re as _re

    match = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", sender or "")
    return match.group(0) if match else ""


def _reply_subject(subject: str) -> str:
    su = subject or ""
    return su if su.lower().startswith("re:") else f"Re: {su}".strip()


class DraftReplyBody(BaseModel):
    # Optional scrappy note of what the user wants to say — the draft expands it
    # into a polished email in their voice. Omit for an auto-drafted reply.
    intent: Optional[str] = None


class RefineBody(BaseModel):
    #: The passage to rewrite — the whole draft, or just what the user selected.
    text: str
    #: shorter | warmer | firmer | formal (see reply.REFINEMENTS)
    how: str
    #: What the email is about, so a mid-email fragment can be rewritten sensibly.
    context: Optional[str] = None


@router.post("/api/reply/refine")
async def refine_reply(
    payload: RefineBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Rewrite part of a draft the user is already looking at — shorter, warmer,
    firmer, more formal — keeping their voice.

    This is the edit people make after reading a draft that's nearly right. Without
    it they retype it themselves, which throws away the voice matching entirely.

    Persists nothing: the caller holds the text, and the user still has to approve
    and send. A refusal comes back as 503 with a sentence to show, never as the
    input handed back unchanged — a button that silently does nothing is worse
    than one that says why it can't.
    """
    from backend.services.reply import refine_draft, RefusedToRefine

    samples, tone, _sig = style_for(db, user_id)
    try:
        return {
            "text": refine_draft(
                payload.text,
                payload.how,
                style_samples=samples,
                tone=tone,
                context=(payload.context or ""),
            )
        }
    except RefusedToRefine as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/api/alerts/{alert_id}/draft-reply")
async def draft_reply_alert(
    alert_id: str,
    payload: DraftReplyBody = DraftReplyBody(),
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Draft a reply in the user's own voice and persist it on the alert (so the
    user can approve & send it in-app, and so a scan-time draft is reusable). When
    an `intent` note is given, the draft conveys that intent, expanded in their
    voice. Also returns a Gmail compose deep link as a fallback for hand-editing."""
    alert = _get_alert(db, alert_id, user_id)
    from backend.services.reply import split_fallback

    samples, tone, signature = style_for(db, user_id)
    draft, is_fallback = split_fallback(
        draft_reply(
            alert.sender or "",
            alert.subject or "",
            alert.snippet or "",
            style_samples=samples,
            tone=tone,
            intent=(payload.intent or ""),
            signature=signature,
        )
    )
    alert.reply_draft = draft
    if (alert.reply_status or "none") in ("none", "failed"):
        alert.reply_status = "drafted"
    alert.reply_error = None
    db.commit()

    to = _sender_email(alert.sender or "")
    compose_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(to)}&su={quote(_reply_subject(alert.subject or ''))}&body={quote(draft)}"
    )
    # voice_matched=False when the LLM was unavailable (placeholder text) so the UI
    # can tell the user this isn't their learned voice yet.
    return {
        "draft": draft,
        "compose_url": compose_url,
        "voice_matched": bool(samples or tone) and not is_fallback,
    }


class ReplySendBody(BaseModel):
    body: Optional[str] = None  # the (possibly edited) reply text; falls back to the stored draft


@router.post("/api/alerts/{alert_id}/reply/send")
async def send_reply_alert(
    alert_id: str,
    payload: ReplySendBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Approve & SEND the drafted reply through Gmail (threaded). Honest lifecycle:
    Gmail not connected → 409 (row untouched); a real send failure → 5xx with the
    error recorded (row survives for retry); only a real returned message id flips
    reply_status to 'sent' and closes the alert."""
    alert = _get_alert(db, alert_id, user_id)
    body = (payload.body if payload.body is not None else alert.reply_draft) or ""
    body = body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="No reply body to send — draft one first.")
    to = _sender_email(alert.sender or "")
    if not to:
        raise HTTPException(status_code=400, detail="No recipient address on this email.")

    alert.reply_draft = body
    try:
        result = gmail_adapter.send(
            db,
            user_id,
            to=to,
            subject=_reply_subject(alert.subject or ""),
            body=body,
            thread_id=alert.thread_id or "",
            in_reply_to=alert.rfc822_msgid or "",
        )
    except IntegrationNotConnected:
        db.commit()  # persist the possibly-edited draft; don't mark sent/failed
        _not_connected("gmail")
    except IntegrationError as e:
        alert.reply_status = "failed"
        alert.reply_error = str(e)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Couldn’t send the reply: {e}")

    message_id = (result or {}).get("message_id") or ""
    if not message_id:
        alert.reply_status = "failed"
        alert.reply_error = "Gmail returned no message id."
        db.commit()
        raise HTTPException(status_code=502, detail="Gmail didn’t confirm the send. Try again.")

    alert.reply_status = "sent"
    alert.reply_external_id = message_id
    alert.reply_sent_at = datetime.utcnow()
    alert.reply_error = None
    alert.status = "done"
    # Only after a real Gmail message id — the feed must never claim a send that
    # didn't happen, which is the whole point of the 502 branches above.
    activity.record(
        db, user_id, "reply_sent",
        f"You replied to {activity.short_sender(alert.sender or '')}",
        detail=alert.subject or "",
        subject_type="alert", subject_id=alert.id,
        counterparty_email=_sender_email(alert.sender or ""),
        at=alert.reply_sent_at,
        meta={"message_id": message_id},
    )
    db.commit()

    # Tell the ledger straight away rather than waiting for the next `in:sent`
    # sweep to notice: the thread flips to "waiting on them" immediately, and the
    # sweep's later pass over the same message becomes a no-op against the unique
    # index. Best-effort — the mail is already sent, so a bookkeeping failure here
    # must not turn a successful send into an error.
    fu = followups.record_outbound(
        db,
        user_id,
        thread_id=alert.thread_id or "",
        message_id=message_id,
        to_email=_sender_email(alert.sender or ""),
        subject=alert.subject or "",
        sent_at=alert.reply_sent_at,
        alert_id=alert.id,
    )
    return {
        "success": True,
        "reply_status": "sent",
        "message_id": message_id,
        # The message-level alert is done, but the LOOP is now on them. Returning
        # it lets the UI say "Sent — I'll watch for their reply" instead of the
        # thread just vanishing, which is how an unanswered quote used to go
        # unnoticed for weeks.
        "followup": fu.to_dict() if fu else None,
    }


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
    auto_draft: Optional[bool] = None
    channel_tiers: Optional[dict] = None


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
        chan = payload.slack_channel.strip()
        # Reject a Slack name/@handle server-side — only an ID (C…/U…/W…/G…/D…)
        # routes; a name is silently unreachable (channel_not_found on every send).
        # Empty clears the destination. Mirrors the client-side slackDestError.
        if chan and not re.fullmatch(r"[CDGUW][A-Z0-9]{6,}", chan):
            raise HTTPException(
                status_code=400,
                detail="Slack needs a channel ID (starts with C) or member ID (starts with U), not a name. Open the channel → About → Channel ID, or pick from the list.",
            )
        cfg.slack_channel = chan
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
    if payload.auto_draft is not None:
        cfg.auto_draft = bool(payload.auto_draft)
    if payload.channel_tiers is not None:
        # Keep only known channels + valid tiers; "" / other → drop (falls back to
        # the global notify_tier for that channel).
        valid = {"urgent", "needs_reply"}
        known = {"slack", "telegram", "discord", "whatsapp"}
        cfg.channel_tiers = {
            k: v
            for k, v in payload.channel_tiers.items()
            if k in known and v in valid
        }
    db.commit()
    db.refresh(cfg)
    return cfg.to_dict()


# ---------------------------------------------------------------------------
# Communication-pattern profile ("what I've learned about you")
# ---------------------------------------------------------------------------


@router.get("/api/profile")
async def get_comm_profile(user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    """What Gmail Sentry has learned about how the user communicates (VIPs, tone,
    style). Empty-but-valid shape when nothing's been learned yet."""
    prof = get_profile(db, user_id)
    if prof is None:
        return {
            "vip_senders": [],
            "response_habits": {},
            "tone": "",
            "style_exemplars": [],
            "signature": "",
            "refreshed_at": None,
        }
    return prof.to_dict()


@router.post("/api/profile/learn")
async def learn_comm_profile(user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    """Re-learn the user's communication patterns from their real sent + inbox mail.
    Best-effort — returns the (possibly unchanged) profile; a 409 only if reading
    the mailbox is impossible because Gmail isn't connected."""
    try:
        return learn_patterns(db, user_id)
    except IntegrationNotConnected:
        _not_connected("gmail")


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
    typing a name (free-text names cause `channel_not_found`). Also returns the
    connected `workspace` name so the user can confirm they're on the right
    workspace (a channel id from another workspace fails even with the bot present).
    Returns ``{connected, workspace, channels:[{id,name}]}``; a not-connected Slack
    yields ``connected: false`` (not an error) so the UI can prompt to connect."""
    from backend.shared.adapters import execute_tool
    from backend.shared.adapters import slack as slack_adapter

    # Which workspace is the token on — best-effort, shown regardless of list result.
    workspace = slack_adapter.connected_workspace(db, user_id).get("team", "")

    try:
        res = execute_tool("slack", "list_channels", user_id, {})
        chans = res.get("channels", []) if isinstance(res, dict) else []
        # Sort by name for a predictable dropdown.
        chans = sorted(
            [{"id": c.get("id", ""), "name": c.get("name", "")} for c in chans if c.get("id")],
            key=lambda c: c["name"].lower(),
        )
        return {"connected": True, "workspace": workspace, "channels": chans}
    except IntegrationNotConnected:
        return {"connected": False, "workspace": workspace, "channels": []}
    except IntegrationError as e:
        # Surface the real reason (e.g. missing channels:read scope) but don't 500.
        return {"connected": True, "workspace": workspace, "channels": [], "error": str(e)}


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
    """Latest known category sizes (snapshot from the last scan) + scan time.
    `last_scan_error` is set when the most recent run couldn't complete (e.g. Gmail
    disconnected) so the UI can show why 'last scan' isn't advancing normally."""
    run = _latest_run(db, user_id)
    return {
        "promotions": (run.promo_count if run else 0) or 0,
        "social": (run.social_count if run else 0) or 0,
        "spam": (run.spam_count if run else 0) or 0,
        "last_scan": _relative_time(run.started_at if run else None),
        "last_scan_error": (run.error if run else None) or None,
    }


@router.get("/api/scans/recent")
async def recent_scans(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The last few scan runs (newest first) so the user can SEE the actual cadence
    — the interval is owned by the Claritty platform, and this makes any drift or
    gaps visible + diagnosable.

    Returns [{at, ago, scanned, flagged, labeled, notified, error}]. `labeled` was
    written on every run and then dropped here, so the filing volume the app was
    proudest of never reached the client."""
    runs = (
        db.query(models.ScanRun)
        .filter(models.ScanRun.user_id == user_id)
        .order_by(models.ScanRun.started_at.desc())
        .limit(10)
        .all()
    )
    return {
        "runs": [
            {
                "at": r.started_at.isoformat() if r.started_at else None,
                "ago": _relative_time(r.started_at),
                "scanned": r.scanned or 0,
                "flagged": r.flagged or 0,
                "labeled": r.labeled or 0,
                "notified": r.notified or 0,
                "error": r.error or None,
            }
            for r in runs
        ]
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
                # A reply is drafted and waiting for one-tap approval in-app.
                "reply_ready": bool((a.reply_draft or "").strip()) and a.reply_status != "sent",
            }
            for a in ranked[:3]
        ]

        # Open loops come from one shared helper so the widget and the app can
        # never disagree about the headline number — a drift between the two
        # destroys trust in both.
        loops = followups.counts(db, user_id)

        # The account slipping furthest, by name. "3 going quiet" is a number;
        # "Northwind, silent 12d" is a decision — and a company name is what the
        # owner recognises at a glance on a home screen.
        top_account = None
        if size in ("medium", "large"):
            ranked_accounts = accounts_service.build(db, user_id)
            at_risk = [a for a in ranked_accounts if a.chasing > 0]
            if at_risk:
                top_account = {
                    "key": at_risk[0].key,
                    "name": at_risk[0].name,
                    "silent_days": at_risk[0].silent_days,
                }

        return {
            "urgent_count": len(urgent),
            "needs_reply_count": len(needs_reply),
            # all_clear now requires the loops to be closed too: "nothing needs
            # you" while a customer has been waiting nine days would be a lie.
            "all_clear": len(urgent) == 0 and len(needs_reply) == 0 and loops["open_loops"] == 0,
            "last_scan": _relative_time(run.started_at if run else None),
            "top_alerts": top_alerts,
            "open_loops": loops["open_loops"],
            "owed_count": loops["owed"],
            "waiting_count": loops["waiting"],
            "cold_count": loops["cold"],
            "top_account": top_account,
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
            "open_loops": 0,
            "owed_count": 0,
            "waiting_count": 0,
            "cold_count": 0,
            "top_account": None,
            "cleanup": {"promo": 0, "social": 0, "spam": 0},
            "slack_configured": False,
        }


# ---------------------------------------------------------------------------
# Follow-ups — thread-level open loops
# ---------------------------------------------------------------------------


def _get_followup(db, followup_id, user_id) -> models.FollowUp:
    fu = (
        db.query(models.FollowUp)
        .filter(models.FollowUp.id == followup_id, models.FollowUp.user_id == user_id)
        .first()
    )
    if not fu:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return fu


@router.get("/api/followups")
async def list_followups_route(
    state: str = "open",
    limit: int = 100,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Open loops, worst first.

    state: open | owed | waiting | cold | snoozed | done | all. Owed views
    exclude threads still being handled as a fresh alert, so this list and the
    alert list partition rather than double-count.
    """
    rows = followups.list_followups(db, user_id, state=state, limit=max(1, min(limit, 200)))
    return {
        "followups": [f.to_dict() for f in rows],
        "counts": followups.counts(db, user_id),
    }


@router.post("/api/followups/{followup_id}/snooze")
async def snooze_followup(
    followup_id: str,
    body: SnoozeBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    fu = followups.snooze(db, _get_followup(db, followup_id, user_id), body.hours)
    return {"success": True, "followup": fu.to_dict()}


@router.post("/api/followups/{followup_id}/done")
async def done_followup(
    followup_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Close the loop without sending anything — often the right answer for a
    thread that's simply over."""
    fu = followups.mark_done(db, _get_followup(db, followup_id, user_id))
    return {"success": True, "followup": fu.to_dict()}


@router.post("/api/followups/{followup_id}/ignore")
async def ignore_followup(
    followup_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """"This isn't a follow-up." Sticky — the sweep won't resurrect it."""
    fu = followups.mark_ignored(db, _get_followup(db, followup_id, user_id))
    return {"success": True, "followup": fu.to_dict()}


@router.post("/api/followups/sync")
async def sync_followups_route(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Re-derive loops from the ledger on demand. Pure SQL — no Gmail calls."""
    closed = followups.close_alerts_replied_elsewhere(db, user_id)
    stats = followups.sync_followups(db, user_id)
    return {"success": True, "alerts_closed": closed, **stats, "counts": followups.counts(db, user_id)}


@router.get("/api/counterparties")
async def list_counterparties(
    limit: int = 50,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Who matters, ranked — derived from the ledger, not from message volume."""
    rows = (
        db.query(models.Counterparty)
        .filter(models.Counterparty.user_id == user_id)
        .order_by(models.Counterparty.importance.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {"counterparties": [c.to_dict() for c in rows]}


class CounterpartyBody(BaseModel):
    relationship: Optional[str] = None
    pinned: Optional[bool] = None
    muted: Optional[bool] = None
    notes: Optional[str] = None


@router.put("/api/counterparties/{cp_id}")
async def update_counterparty(
    cp_id: str,
    payload: CounterpartyBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """User corrections. A stated relationship is marked as such so inference
    never overwrites it later."""
    row = (
        db.query(models.Counterparty)
        .filter(models.Counterparty.id == cp_id, models.Counterparty.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Counterparty not found")
    if payload.relationship is not None:
        valid = ("customer", "prospect", "internal", "vendor", "bulk", "unknown")
        if payload.relationship not in valid:
            raise HTTPException(status_code=400, detail=f"relationship must be one of {valid}")
        row.relationship = payload.relationship
        row.relationship_source = "user"
    if payload.pinned is not None:
        row.pinned = bool(payload.pinned)
    if payload.muted is not None:
        row.muted = bool(payload.muted)
    if payload.notes is not None:
        row.notes = payload.notes[:2000]
    db.commit()
    return {"success": True, "counterparty": row.to_dict()}


# ---------------------------------------------------------------------------
# Folders — smart filing, approval-gated
# ---------------------------------------------------------------------------


def _get_folder(db, folder_id, user_id) -> models.MailFolder:
    row = (
        db.query(models.MailFolder)
        .filter(models.MailFolder.id == folder_id, models.MailFolder.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")
    return row


@router.get("/api/folders")
async def list_folders(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Folders this app files into, plus the ones waiting on a decision.

    Nothing is ever labelled with a folder in `proposed` — that's the gate that
    keeps automatic filing from sprawling through someone's real mailbox.
    """
    rows = (
        db.query(models.MailFolder)
        .filter(models.MailFolder.user_id == user_id)
        .order_by(models.MailFolder.status.asc(), models.MailFolder.name.asc())
        .limit(200)
        .all()
    )
    filed_counts = dict(
        db.query(models.ThreadFolder.folder_name, func.count(models.ThreadFolder.id))
        .filter(
            models.ThreadFolder.user_id == user_id,
            models.ThreadFolder.status == "filed",
        )
        .group_by(models.ThreadFolder.folder_name)
        .all()
    )
    # When each folder last received something. A count alone can't tell an
    # active folder from one that stopped being used in April.
    last_filed = dict(
        db.query(models.ThreadFolder.folder_name, func.max(models.ThreadFolder.filed_at))
        .filter(
            models.ThreadFolder.user_id == user_id,
            models.ThreadFolder.status == "filed",
        )
        .group_by(models.ThreadFolder.folder_name)
        .all()
    )
    cfg = get_config(db, user_id)
    out = []
    for f in rows:
        d = f.to_dict()
        d["thread_count"] = int(filed_counts.get(f.name, 0))
        when = last_filed.get(f.name)
        d["last_filed_at"] = when.isoformat() if when else None
        d["last_filed_ago"] = _relative_time(when) if when else ""
        out.append(d)
    return {
        "folders": out,
        "filing_enabled": bool(cfg.filing_enabled),
        "pending": sum(1 for f in rows if f.status == "proposed"),
    }


@router.get("/api/folders/{folder_id}/threads")
async def folder_threads(
    folder_id: str,
    limit: int = 50,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The conversations filed into one folder.

    A folder that shows only a number is a claim the user can't check. This is
    what makes filing auditable: they can see exactly what was put where, and
    open any of it in Gmail if the answer is "not that one".

    Subject and counterparty come from the ledger rather than from Gmail — the
    rows are already local, so browsing a folder costs no broker calls.
    """
    folder = _get_folder(db, folder_id, user_id)
    rows = (
        db.query(models.ThreadFolder)
        .filter(
            models.ThreadFolder.user_id == user_id,
            models.ThreadFolder.folder_name == folder.name,
        )
        .order_by(models.ThreadFolder.filed_at.desc().nullslast())
        .limit(max(1, min(limit, 200)))
        .all()
    )

    ids = [r.thread_id for r in rows]
    identity: dict = {}
    if ids:
        for m in (
            db.query(models.ThreadMessage)
            .filter(
                models.ThreadMessage.user_id == user_id,
                models.ThreadMessage.thread_id.in_(ids),
            )
            .order_by(models.ThreadMessage.ts_hi.asc())
            .all()
        ):
            slot = identity.setdefault(m.thread_id, {"subject": "", "email": "", "name": ""})
            if not slot["subject"] and m.subject:
                slot["subject"] = m.subject
            if not slot["email"] and m.direction == "in" and m.counterparty_email:
                slot["email"] = m.counterparty_email
                slot["name"] = activity.short_sender(m.sender or "")

    return {
        "folder": folder.to_dict(),
        "threads": [
            {
                "thread_id": r.thread_id,
                "subject": identity.get(r.thread_id, {}).get("subject") or "(no subject)",
                "counterparty_email": identity.get(r.thread_id, {}).get("email") or "",
                "counterparty_name": identity.get(r.thread_id, {}).get("name") or "",
                "status": r.status,
                "filed_count": int(r.filed_count or 0),
                "filed_at": r.filed_at.isoformat() if r.filed_at else None,
                "filed_ago": _relative_time(r.filed_at) if r.filed_at else "",
                "error": r.error or "",
                "deep_link": f"https://mail.google.com/mail/u/0/#all/{r.thread_id}",
            }
            for r in rows
        ],
    }


@router.get("/api/activity")
async def get_activity(
    days: int = 14,
    limit: int = 120,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """What this app actually did, newest first, grouped by day.

    Changes only — never runs. A scan that found nothing writes nothing, so
    every line here is worth reading. Scan cadence lives on the dashboard.
    """
    events = activity.feed(db, user_id, days=days, limit=limit)
    return {
        "days": activity.by_day(events),
        "summary": activity.summary(db, user_id, days=7),
        "total": len(events),
        "window_days": days,
    }


# ---------------------------------------------------------------------------
# Mail — reading and writing, the client half of the app
# ---------------------------------------------------------------------------


@router.get("/api/mail")
async def list_mail(
    box: str = "inbox",
    q: str = "",
    page_token: str = "",
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """One page of a mailbox, or of a search when `q` is given.

    `box` is a closed set (inbox | unread | sent | starred | archive) rather than
    a free-text Gmail query, because an arbitrary query from the URL is both a
    performance footgun and a way to ask for mail the UI can't render.
    """
    try:
        return mail_service.list_box(db, user_id, box=box, query=q, page_token=page_token)
    except IntegrationNotConnected:
        return _not_connected("gmail")


@router.get("/api/mail/thread/{thread_id}")
async def read_mail_thread(
    thread_id: str,
    seed: str = "",
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """A whole conversation, oldest first. `partial` is true when the ledger
    didn't know this thread, so what comes back is one message rather than the
    exchange — the UI says so rather than implying completeness."""
    try:
        return mail_service.read_thread(db, user_id, thread_id, seed_id=seed)
    except IntegrationNotConnected:
        return _not_connected("gmail")


class SendMailBody(BaseModel):
    to: str
    subject: str = ""
    body: str
    #: Set both to keep a reply in its Gmail conversation.
    thread_id: str = ""
    in_reply_to: str = ""


@router.post("/api/mail/send")
async def send_mail_route(
    payload: SendMailBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Send an email. Same honest contract as every other outbound action: a
    real Gmail message id, or an error — never an optimistic success."""
    if not payload.to.strip() or not payload.body.strip():
        raise HTTPException(status_code=400, detail="A recipient and a message are required.")
    try:
        return {"success": True, **mail_service.send_mail(
            db, user_id,
            to=payload.to.strip(), subject=payload.subject.strip(), body=payload.body,
            thread_id=payload.thread_id, in_reply_to=payload.in_reply_to,
        )}
    except IntegrationNotConnected:
        raise HTTPException(status_code=409, detail="Connect Gmail, then try again.")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=f"Couldn’t send: {e}")


@router.post("/api/mail/{message_id}/archive")
async def archive_mail(message_id: str, user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    try:
        gmail_adapter.archive(db, user_id, message_id)
        return {"success": True}
    except IntegrationNotConnected:
        raise HTTPException(status_code=409, detail="Connect Gmail, then try again.")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/worklist")
async def get_worklist(
    limit: int = 12,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """What your email needs from you, ranked — one list, not four inventories.

    Merges the two things that represent an obligation (mail waiting on an
    answer, and open loops) into a single ordered plan, each row phrased as the
    thing to DO rather than the thing that arrived, carrying the deadline the
    app already parses and previously showed nowhere.

    The two sources are disjoint by construction, so the count can be trusted —
    see followups.py on the Alert/FollowUp boundary.
    """
    return worklist_service.build(db, user_id, limit=max(1, min(limit, 50)))


@router.get("/api/insights")
async def get_insights(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """True statements about how this mailbox works.

    Countable facts only — no modelled hours saved, no imputed money value. One
    invented number a user can disprove makes every other number in the app
    suspect, including the ones their mail depends on.
    """
    return insights_service.build(db, user_id)


@router.get("/api/accounts")
async def list_accounts_route(
    limit: int = 100,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The mailbox grouped into the companies behind it, worst first.

    Counts are rolled up from the same worklist rows Today renders, so an
    account card and the list beneath it can never disagree.
    """
    return accounts_service.list_accounts(db, user_id, limit=limit)


@router.get("/api/accounts/{key:path}")
async def get_account_route(
    key: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """One account: its people and its threads.

    404 rather than an empty shell when the key is gone — a domain-keyed account
    becomes CRM-keyed as soon as a CRM lookup lands, and a stale bookmark should
    say so instead of rendering a company with nothing in it.
    """
    account = accounts_service.get_account(db, user_id, key)
    if account is None:
        raise HTTPException(status_code=404, detail="No such account")
    return account


def _onboarding_progress(db: Session, user_id: str) -> dict:
    st = ledger.get_sync_state(db, user_id)
    threads = (
        db.query(func.count(func.distinct(models.ThreadMessage.thread_id)))
        .filter(models.ThreadMessage.user_id == user_id)
        .scalar()
    ) or 0
    return {
        "messages_indexed": int(st.messages_indexed or 0),
        "threads": int(threads),
        "backfill_done": bool(st.backfill_done),
        "horizon_days": int(st.horizon_days or 45),
        "last_error": st.last_error or "",
    }


@router.get("/api/onboarding/progress")
async def onboarding_progress_route(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """How much of the mailbox has been read so far."""
    return _onboarding_progress(db, user_id)


@router.post("/api/onboarding/backfill")
async def onboarding_backfill_route(
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Read a chunk of history now, instead of over the next two hours.

    A normal scan indexes `sentry.MAX_MESSAGES` and `sync_ledger` walks
    `BACKFILL_BUCKETS_PER_RUN` six-hour buckets, so a fresh mailbox takes hours
    to become useful — which is indistinguishable from the app being broken, and
    was exactly the "I connected Gmail and nothing showed" report.

    So: sweep in a loop under a wall-clock budget and return progress. The client
    calls this until `backfill_done`, which keeps every request short (no
    gateway timeout, no background worker on a platform that doesn't offer one)
    while still filling a mailbox in a minute or two.

    On the call that finishes the walk, recompute the derived layers once so
    accounts, relationships and open loops exist the moment the bar fills —
    landing on an empty app after watching a progress bar would be worse than
    the wait.
    """
    budget_s = 20.0
    started = time.monotonic()
    swept = 0
    try:
        while time.monotonic() - started < budget_s:
            st = ledger.get_sync_state(db, user_id)
            if st.backfill_done:
                break
            ledger.sync_ledger(db, user_id)
            swept += 1
    except IntegrationNotConnected:
        raise HTTPException(status_code=409, detail="Gmail isn’t connected")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=f"Couldn’t read Gmail: {e}")

    progress = _onboarding_progress(db, user_id)
    if progress["backfill_done"]:
        # Cheap relative to the sweeps above, and it is what turns an index of
        # messages into people, loops and accounts.
        counterparty_service.recompute(db, user_id)
        followups.sync_followups(db, user_id)
        progress = _onboarding_progress(db, user_id)
    progress["swept"] = swept
    return progress


class FolderBody(BaseModel):
    name: Optional[str] = None


@router.post("/api/folders/{folder_id}/approve")
async def approve_folder_route(
    folder_id: str,
    payload: FolderBody = FolderBody(),
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Approve a proposed folder, optionally renaming it first — the user's
    wording should win over ours."""
    folder = _get_folder(db, folder_id, user_id)
    if payload.name and payload.name.strip() != folder.name:
        try:
            filing.rename_folder(db, folder, payload.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    filing.approve_folder(db, folder)
    return {"success": True, "folder": folder.to_dict()}


@router.post("/api/folders/{folder_id}/reject")
async def reject_folder_route(
    folder_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Decline a folder. It won't be proposed again, and any threads queued
    against it are dropped."""
    folder = _get_folder(db, folder_id, user_id)
    filing.reject_folder(db, folder)
    return {"success": True, "folder": folder.to_dict()}


class FilingToggleBody(BaseModel):
    enabled: bool


@router.put("/api/folders/settings")
async def set_filing(
    payload: FilingToggleBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Turn smart filing on or off.

    Switching it on stamps `filing_started_at`, which is what makes filing
    forward-only: the ledger holds weeks of backfilled history, and relabelling
    all of it the moment someone flips a switch would be an unpleasant surprise
    in a real mailbox. The backlog is a separate, previewable action.
    """
    cfg = get_config(db, user_id)
    was = bool(cfg.filing_enabled)
    cfg.filing_enabled = bool(payload.enabled)
    if cfg.filing_enabled and not was:
        cfg.filing_started_at = datetime.utcnow()
    db.commit()
    return {"success": True, "filing_enabled": cfg.filing_enabled}


@router.get("/api/folders/backlog-preview")
async def backlog_preview(
    days: int = 30,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """What organising the recent backlog WOULD do. Writes nothing."""
    return {"preview": filing.preview_backlog(db, user_id, days=max(1, min(days, 90)))}


class OrganizeBacklogBody(BaseModel):
    days: int = 30
    #: Exactly the folders the user ticked in the preview. Picking one here IS
    #: the approval — a deliberate choice against a preview that says how many
    #: conversations go where.
    folders: List[str] = []


@router.post("/api/folders/organize-backlog")
async def organize_backlog_route(
    payload: OrganizeBacklogBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """File the mail that was already there.

    Automatic filing is forward-only from the moment it's switched on, which is
    right — nobody wants an app relabelling four thousand old threads because
    they flipped a toggle. But that left the actual backlog untouched forever,
    which is the mail someone installed this to get organised.

    Capped per run; anything left over comes back as `remaining` so the UI can
    offer to continue rather than silently stopping halfway.
    """
    if not payload.folders:
        raise HTTPException(status_code=400, detail="Pick at least one folder to organize into.")
    try:
        return {
            "success": True,
            **filing.organize_backlog(
                db, user_id,
                days=max(1, min(payload.days, 90)),
                folders=payload.folders[:50],
            ),
        }
    except IntegrationNotConnected:
        raise HTTPException(status_code=409, detail="Connect Gmail, then try again.")
    except IntegrationError as e:
        raise HTTPException(status_code=502, detail=f"Gmail couldn’t apply the labels: {e}")


# ---------------------------------------------------------------------------
# Nudges — chasing a thread that's gone quiet. Draft-only until approved.
# ---------------------------------------------------------------------------


class NudgeDraftBody(BaseModel):
    # gentle | direct | closing. Omit to let the attempt number choose.
    tone: Optional[str] = None


@router.post("/api/followups/{followup_id}/nudge")
async def draft_nudge(
    followup_id: str,
    payload: NudgeDraftBody = NudgeDraftBody(),
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Draft a nudge for this loop. Never sends.

    A refusal comes back as 409 with the reason in prose, because every guard
    here has to be explained: silently disabling the button teaches people the
    app is broken, while "you nudged them 2 days ago, give it 2 more" teaches
    them it's careful.
    """
    fu = _get_followup(db, followup_id, user_id)
    nudge, refusal = nudges.generate_nudge(db, user_id, fu, tone=(payload.tone or ""))
    if nudge is None:
        raise HTTPException(status_code=409, detail=refusal)
    return {"success": True, "nudge": nudges.nudge_payload(nudge)}


@router.get("/api/followups/{followup_id}/nudge")
async def get_nudge(
    followup_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The live proposal for this loop, if any, plus whether a new one is allowed
    (and why not, when it isn't)."""
    fu = _get_followup(db, followup_id, user_id)
    existing = nudges.open_proposal(db, user_id, fu.id)
    return {
        "nudge": nudges.nudge_payload(existing) if existing else None,
        "blocked_reason": nudges.why_not_eligible(db, user_id, fu),
        "nudge_count": int(fu.nudge_count or 0),
    }


class NudgeSendBody(BaseModel):
    # The edited body, when the user changed it before approving.
    body: Optional[str] = None


@router.post("/api/nudges/{nudge_id}/send")
async def send_nudge(
    nudge_id: str,
    payload: NudgeSendBody = NudgeSendBody(),
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Send an approved nudge, in-thread.

    Same honest-failure contract as replying: not connected leaves the row
    untouched and returns 409, a real failure returns 502 with the error
    recorded so it survives for retry, and only a genuine Gmail message id
    marks it sent.
    """
    nudge = (
        db.query(models.Nudge)
        .filter(models.Nudge.id == nudge_id, models.Nudge.user_id == user_id)
        .first()
    )
    if not nudge:
        raise HTTPException(status_code=404, detail="Nudge not found")
    if nudge.status == "sent":
        raise HTTPException(status_code=409, detail="That nudge has already been sent.")

    fu = _get_followup(db, nudge.followup_id, user_id)

    # Re-check the guards at send time, not just at draft time — a draft can sit
    # on screen while another thread's nudge goes out to the same person.
    refusal = nudges.why_not_eligible(db, user_id, fu)
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)

    body = (payload.body or "").strip()
    if not body:
        body, _is_fallback = nudges_split(nudge.draft or "")
    if not body:
        raise HTTPException(status_code=400, detail="Nothing to send.")
    nudge.draft = body
    db.commit()

    to = nudge.to_email or _sender_email(fu.counterparty_email or "")
    if not to:
        raise HTTPException(status_code=400, detail="No recipient address for this thread.")

    try:
        result = gmail_adapter.send(
            db, user_id,
            to=to,
            subject=nudge.subject or _reply_subject(fu.subject or ""),
            body=body,
            thread_id=fu.thread_id or "",
            in_reply_to=nudge.in_reply_to or "",
        )
    except IntegrationNotConnected:
        db.commit()  # keep the edited draft; don't mark sent or failed
        _not_connected("gmail")
    except IntegrationError as e:
        nudge.status = "failed"
        nudge.error = str(e)[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=f"Couldn’t send the nudge: {e}")

    message_id = (result or {}).get("message_id") or ""
    if not message_id:
        nudge.status = "failed"
        nudge.error = "Gmail returned no message id."
        db.commit()
        raise HTTPException(status_code=502, detail="Gmail didn’t confirm the send. Try again.")

    nudges.mark_sent(db, user_id, nudge, fu, message_id)
    followups.record_outbound(
        db, user_id,
        thread_id=fu.thread_id or "",
        message_id=message_id,
        to_email=to,
        subject=nudge.subject or "",
    )
    db.refresh(fu)
    return {
        "success": True,
        "message_id": message_id,
        "nudge": nudges.nudge_payload(nudge),
        "followup": fu.to_dict(),
    }


@router.post("/api/nudges/{nudge_id}/skip")
async def skip_nudge(
    nudge_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    nudge = (
        db.query(models.Nudge)
        .filter(models.Nudge.id == nudge_id, models.Nudge.user_id == user_id)
        .first()
    )
    if not nudge:
        raise HTTPException(status_code=404, detail="Nudge not found")
    nudge.status = "skipped"
    db.commit()
    return {"success": True}
