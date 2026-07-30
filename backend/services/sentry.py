"""
The Gmail Sentry scan engine.

`run_scan` is the heart of the app — one pass over recent inbox mail:
  1. fetch recent inbox messages,
  2. apply the user's filing (label) rules,
  3. triage each with services.triage.classify_email,
  4. persist an Alert for each urgent / needs_reply email,
  5. Slack-ping the user (configured channel) for new alerts at/above notify tier,
  6. refresh the cleanup category counts (Promotions / Social / Spam),
  7. record a ScanRun.

It's called from POST /api/scan/run (route), the app.run_inbox_scan tool, and the
scheduled workflow — the same engine on every path. It uses the bundled Gmail/Slack
adapters, which surface IntegrationNotConnected (→ 409) when a service isn't
connected. Never fakes success.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend import models
from backend.services.triage import classify_email, TIER_RANK
from backend.services.reply import draft_reply, style_for
from backend.services.learn import get_profile
from backend.shared.adapters import IntegrationNotConnected, IntegrationError
from backend.integrations import gmail_ops as gmail_adapter
from backend.integrations import notify

logger = logging.getLogger(__name__)

MAX_MESSAGES = 20
TIER_LABEL = {"urgent": "🔴 Urgent", "needs_reply": "🟡 Needs reply", "fyi": "FYI"}


def _alert_message(alert: models.Alert) -> str:
    """The notification text for one alert. For needs_reply alerts that already
    have a drafted reply, it carries a preview + a one-tap approve deep link; for
    everything else it's the attention line + Gmail deep link. Plain text so it
    renders on every channel."""
    lines = [
        f"🔔 {TIER_LABEL.get(alert.tier, alert.tier)} — {alert.subject or '(no subject)'}",
        f"From: {alert.sender}",
    ]
    if alert.reason:
        lines.append(alert.reason)
    draft = (alert.reply_draft or "").strip()
    if alert.tier == "needs_reply" and draft:
        preview = draft if len(draft) <= 240 else draft[:240].rstrip() + "…"
        approve = notify.app_focus_link(alert.id) or alert.deep_link or ""
        lines += ["", "✍️ Draft reply ready:", f"“{preview}”", "", f"👉 Approve & send: {approve}"]
    else:
        lines.append(alert.deep_link or "")
    return "\n".join(x for x in lines if x is not None).strip()


def _latest_scan_run(db: Session, user_id: str) -> Optional[models.ScanRun]:
    """The user's most recent ScanRun (for carrying forward cleanup counts)."""
    return (
        db.query(models.ScanRun)
        .filter(models.ScanRun.user_id == user_id)
        .order_by(models.ScanRun.started_at.desc())
        .first()
    )


def get_config(db: Session, user_id: str) -> models.SentryConfig:
    cfg = (
        db.query(models.SentryConfig)
        .filter(models.SentryConfig.user_id == user_id)
        .first()
    )
    if cfg is None:
        cfg = models.SentryConfig(user_id=user_id, slack_channel="", notify_tier="urgent")
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _deep_link(rfc822_msgid: Optional[str], gmail_message_id: str) -> str:
    if rfc822_msgid:
        return f"https://mail.google.com/mail/u/0/#search/rfc822msgid:{rfc822_msgid}"
    return f"https://mail.google.com/mail/u/0/#all/{gmail_message_id}"


def _label_rule_matches(rule: models.LabelRule, sender: str, subject: str) -> bool:
    val = (rule.match_value or "").strip().lower()
    if not val:
        return False
    sender_l = (sender or "").lower()
    if rule.match_type == "sender":
        return val in sender_l
    if rule.match_type == "domain":
        return val in sender_l
    if rule.match_type == "subject_keyword":
        return val in (subject or "").lower()
    return False


def _refresh_cleanup_counts(db: Session, user_id: str, run: models.ScanRun) -> None:
    """Best-effort category sizes — a failure here never fails the whole scan."""
    queries = {
        "promo_count": "category:promotions",
        "social_count": "category:social",
        "spam_count": "in:spam",
    }
    for attr, q in queries.items():
        try:
            setattr(run, attr, gmail_adapter.count(db, user_id, q))
        except (IntegrationError, IntegrationNotConnected) as e:
            logger.info(f"cleanup count {q} skipped: {e}")


def run_scan(db: Session, user_id: str, *, max_messages: int = MAX_MESSAGES) -> Dict[str, Any]:
    """Run one inbox scan for `user_id`. Returns a summary dict.

    Raises IntegrationNotConnected when Gmail isn't connected (caller maps to 409).
    A ScanRun row is always written (with `error` set on the not-connected path).
    """
    cfg = get_config(db, user_id)
    rules = [
        r.to_dict()
        for r in db.query(models.TriageRule)
        .filter(models.TriageRule.user_id == user_id, models.TriageRule.active == True)  # noqa: E712
        .all()
    ]
    label_rules = (
        db.query(models.LabelRule)
        .filter(models.LabelRule.user_id == user_id, models.LabelRule.active == True)  # noqa: E712
        .all()
    )

    # Behavioral VIPs from the learned communication profile: surface mail from the
    # people the user actually corresponds with, even without an explicit rule.
    prof = get_profile(db, user_id)
    if prof:
        for v in (prof.vip_senders or [])[:5]:
            email = (v.get("email") or "").strip()
            if email:
                rules.append({
                    "name": f"Frequent contact {email}",
                    "kind": "vip_sender",
                    "value": email,
                    "tier": "needs_reply",
                })

    run = models.ScanRun(user_id=user_id)

    try:
        stubs = gmail_adapter.search(
            db, user_id, "in:inbox newer_than:2d", max_results=max_messages
        )
    except IntegrationNotConnected:
        # Record the attempt (with an error) so the widget's "last scan" reflects
        # that scans ARE firing — otherwise a run that fires while Gmail is
        # disconnected writes nothing and the UI looks like scheduling stopped.
        # Carry forward the last-good cleanup counts so the snapshot isn't zeroed.
        prev = _latest_scan_run(db, user_id)
        run.error = "gmail_not_connected"
        if prev:
            run.promo_count = prev.promo_count or 0
            run.social_count = prev.social_count or 0
            run.spam_count = prev.spam_count or 0
        db.add(run)
        db.commit()
        raise

    muted = [m.lower() for m in (cfg.muted_senders or []) if m]
    scanned = flagged = labeled = notified = 0
    new_alerts: List[models.Alert] = []

    for stub in stubs:
        msg_id = stub.get("id")
        if not msg_id:
            continue
        scanned += 1

        # Dedupe: skip messages we've already turned into an alert.
        existing = (
            db.query(models.Alert)
            .filter(
                models.Alert.user_id == user_id,
                models.Alert.gmail_message_id == msg_id,
            )
            .first()
        )
        if existing:
            continue

        try:
            meta = gmail_adapter.get_meta(db, user_id, msg_id)
        except Exception as e:  # noqa: BLE001 — a single unreadable message is skippable
            logger.info(f"get_meta failed for {msg_id}: {type(e).__name__}: {e}")
            continue

        sender = meta.get("sender", "")
        subject = meta.get("subject", "")
        snippet = meta.get("snippet", "")

        # Muted senders never become attention alerts.
        if muted and any(m in sender.lower() for m in muted):
            continue

        # 1) Filing rules (deterministic).
        archived = False
        for lr in label_rules:
            if _label_rule_matches(lr, sender, subject):
                try:
                    gmail_adapter.apply_label(
                        db, user_id, msg_id, lr.target_label, archive=lr.archive_after
                    )
                    labeled += 1
                    archived = archived or lr.archive_after
                except Exception as e:  # noqa: BLE001 — filing one message can fail alone
                    logger.info(f"apply_label failed for {msg_id}: {type(e).__name__}: {e}")

        # An archived email left the inbox — don't also raise an attention alert.
        if archived:
            continue

        # 2) Triage.
        verdict = classify_email(rules, sender, subject, snippet)
        tier = verdict["tier"]
        if TIER_RANK.get(tier, 0) <= TIER_RANK["fyi"]:
            continue  # only urgent / needs_reply become alerts

        deep = _deep_link(meta.get("rfc822_msgid"), msg_id)
        alert = models.Alert(
            user_id=user_id,
            gmail_message_id=msg_id,
            thread_id=meta.get("thread_id"),
            rfc822_msgid=meta.get("rfc822_msgid"),
            sender=sender,
            subject=subject,
            snippet=snippet,
            tier=tier,
            reason=verdict.get("reason"),
            deep_link=deep,
            slack_sent=False,
            status="new",
        )
        # Insert inside a savepoint so a concurrent scan that already created this
        # alert (unique (user_id, gmail_message_id)) drops just THIS row — never the
        # whole batch, and never a duplicate alert/ping. Belt to the pre-insert
        # SELECT's suspenders (which races under overlapping runs).
        try:
            with db.begin_nested():
                db.add(alert)
                db.flush()
        except IntegrityError:
            logger.info(f"duplicate alert skipped for {msg_id} (concurrent scan)")
            continue
        flagged += 1
        new_alerts.append(alert)

    # Persist alerts before notifying so they have ids.
    db.commit()

    # 2.5) Pre-draft replies for needs_reply alerts (in the user's voice) so the
    #      notification can carry the reply and the user can approve in one tap.
    #      Best-effort and NEVER auto-sends — approval is always explicit.
    if cfg.auto_draft:
        to_reply = [a for a in new_alerts if a.tier == "needs_reply"]
        if to_reply:
            from backend.services.reply import split_fallback

            samples, tone, signature = style_for(db, user_id)
            for a in to_reply:
                try:
                    draft, is_fallback = split_fallback(
                        draft_reply(
                            a.sender or "", a.subject or "", a.snippet or "",
                            style_samples=samples, tone=tone, signature=signature,
                        )
                    )
                    a.reply_draft = draft
                    # Only advertise a ready draft when it's the real (LLM) voice —
                    # a template placeholder shouldn't claim "draft ready".
                    a.reply_status = "drafted" if not is_fallback else a.reply_status
                except Exception as e:  # noqa: BLE001 — drafting is best-effort
                    logger.info(f"pre-draft failed for alert {a.id}: {type(e).__name__}: {e}")
            db.commit()

    # 3) Fan each fresh alert out to the channels whose urgency routing accepts it
    #    (per-channel tier, falling back to the global notify_tier). Plain text so
    #    it reads well everywhere; needs_reply pings carry the drafted reply + a
    #    one-tap approve link (see _alert_message).
    for alert in new_alerts:
        results = notify.notify_all(db, user_id, cfg, _alert_message(alert), tier=alert.tier)
        if any(r["ok"] for r in results):
            alert.slack_sent = True  # reused as the "notified" flag
            notified += 1
    db.commit()

    # 4) Cleanup counts + finalize the run.
    try:
        _refresh_cleanup_counts(db, user_id, run)
    except Exception as e:  # noqa: BLE001 — a counts hiccup shouldn't fail the whole scan
        logger.info(f"cleanup counts refresh failed: {type(e).__name__}: {e}")
    run.scanned = scanned
    run.flagged = flagged
    run.labeled = labeled
    run.notified = notified
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "scanned": scanned,
        "flagged": flagged,
        "labeled": labeled,
        "notified": notified,
        "slack_configured": bool(cfg.slack_channel),
        "promo_count": run.promo_count or 0,
        "social_count": run.social_count or 0,
        "spam_count": run.spam_count or 0,
    }
