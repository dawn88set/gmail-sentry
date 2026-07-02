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

from backend import models
from backend.services.triage import classify_email, TIER_RANK
from backend.shared.adapters import IntegrationNotConnected, IntegrationError
from backend.integrations import gmail_ops as gmail_adapter
from backend.integrations import notify

logger = logging.getLogger(__name__)

MAX_MESSAGES = 20
TIER_LABEL = {"urgent": "🔴 Urgent", "needs_reply": "🟡 Needs reply", "fyi": "FYI"}


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

    run = models.ScanRun(user_id=user_id)

    try:
        stubs = gmail_adapter.search(
            db, user_id, "in:inbox newer_than:2d", max_results=max_messages
        )
    except IntegrationNotConnected:
        # Don't persist a ScanRun here — a failed attempt shouldn't clobber the
        # last good cleanup snapshot / scan time with zeros. Just signal upward.
        raise

    notify_floor = TIER_RANK.get(cfg.notify_tier or "urgent", 2)
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

        flagged += 1
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
        db.add(alert)
        new_alerts.append(alert)

    # Persist alerts before notifying so they have ids.
    db.commit()

    # 3) Fan out fresh alerts at/above the notify tier to EVERY configured
    #    channel (Slack, Telegram, Discord, Teams, WhatsApp). Plain text so it
    #    reads well everywhere (URLs auto-link on all of them).
    for alert in new_alerts:
        if TIER_RANK.get(alert.tier, 0) < notify_floor:
            continue
        text = (
            f"🔔 {TIER_LABEL.get(alert.tier, alert.tier)} — {alert.subject or '(no subject)'}\n"
            f"From: {alert.sender}\n"
            f"{alert.reason or ''}\n"
            f"{alert.deep_link or ''}"
        ).strip()
        results = notify.notify_all(db, user_id, cfg, text)
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
