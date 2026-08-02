"""
The Gmail Sentry scan engine.

`run_scan` is the heart of the app — one pass over recent inbox mail:
  1. sync the thread ledger and take the messages it has never judged,
  2. apply the user's filing (label) rules,
  3. triage each with services.triage.classify_email,
  4. persist an Alert for each urgent / needs_reply email,
  5. Slack-ping the user (configured channel) for new alerts at/above notify tier,
  6. refresh the cleanup category counts (Promotions / Social / Spam),
  7. record a ScanRun.

Step 1 is why the scan is cheap. It used to re-query `in:inbox newer_than:2d`
every run and re-classify everything it found, because a message judged `fyi`
left no trace — so a quiet inbox burned an LLM call per message every five
minutes, for two days per message. The ledger records a verdict for EVERY
message it judges, `fyi` included, so each one is judged exactly once and a
quiet inbox costs nothing. Every `continue` in the loop below must therefore
record a verdict first; see backend/services/ledger.py.

It's called from POST /api/scan/run (route), the app.run_inbox_scan tool, and the
scheduled workflow — the same engine on every path. It uses the bundled Gmail/Slack
adapters, which surface IntegrationNotConnected (→ 409) when a service isn't
connected. Never fakes success.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend import models
from backend.services.triage import classify_email, TIER_RANK
from backend.services.reply import draft_reply, style_for
from backend.services.learn import get_profile
from backend.services import activity
from backend.services import ledger
from backend.services import counterparty
from backend.services import followups
from backend.services import filing
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


#: Install-time defaults, declared in app-config.json#configSchema and set by the
#: user (or the platform) at install. They seed a NEW user's SentryConfig row
#: only — once a row exists the in-app Rules screen owns these values, so
#: changing the install config never overwrites a choice someone made in the UI.
_VALID_TIERS = ("urgent", "needs_reply")


def _default_notify_tier() -> str:
    tier = (os.getenv("SENTRY_NOTIFY_TIER") or "").strip().lower()
    return tier if tier in _VALID_TIERS else "urgent"


def _default_filing_enabled() -> bool:
    """Install-time default for smart filing (app-config.json#configSchema).

    Defaults OFF: filing writes labels into a real mailbox, so it should be a
    deliberate yes rather than something that happens to a user who installed
    the app for triage.
    """
    raw = (os.getenv("SENTRY_FILING_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes")


def _default_auto_draft() -> bool:
    raw = (os.getenv("SENTRY_AUTO_DRAFT") or "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    return True  # model default: drafting a reply costs nothing until it's sent


def get_config(db: Session, user_id: str) -> models.SentryConfig:
    cfg = (
        db.query(models.SentryConfig)
        .filter(models.SentryConfig.user_id == user_id)
        .first()
    )
    if cfg is None:
        filing_on = _default_filing_enabled()
        cfg = models.SentryConfig(
            user_id=user_id,
            slack_channel="",
            notify_tier=_default_notify_tier(),
            auto_draft=_default_auto_draft(),
            filing_enabled=filing_on,
            # Stamped up front so filing is forward-only even when it's on from
            # the very first scan — otherwise the ledger's backfilled history
            # would all be fair game on day one.
            filing_started_at=datetime.utcnow() if filing_on else None,
        )
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

    # Surface mail from the people it would cost the user to ignore, even with no
    # explicit rule. This used to be the top five `vip_senders` — a frequency
    # list, which ranks a daily newsletter above a client who writes monthly.
    # Counterparties rank by revealed preference instead (do you reply, how fast,
    # over how many threads), derived from the ledger with no extra API calls.
    rules.extend(counterparty.triage_rules_for(db, user_id))
    if not rules:
        # Nothing learned yet — fall back to the profile's VIP list so a brand-new
        # install still surfaces the obvious people on its very first scans.
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

    # Bring the thread ledger up to date, then take work FROM it rather than
    # re-querying Gmail. Two consequences worth stating plainly:
    #
    #   * Cost. Candidates are messages with no verdict yet. A message that was
    #     judged `fyi` keeps that verdict forever, so it is never sent to the
    #     model again. Previously `fyi` wrote no row at all, so every scan
    #     re-fetched and re-classified the same quiet inbox for two days.
    #   * Reach. The sweep also indexes `in:sent`, which is how a reply the user
    #     sent from their phone becomes visible to the app.
    sync_stats: Dict[str, int] = {}
    try:
        sync_stats = ledger.sync_ledger(db, user_id)
        candidates = ledger.untriaged_inbound(db, user_id, limit=max_messages)
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
    #: thread_id → the ask extracted for it this run, applied after the loops sync.
    _asks: Dict[str, Dict[str, Any]] = {}
    new_alerts: List[models.Alert] = []

    for msg in candidates:
        msg_id = msg.gmail_message_id
        scanned += 1

        # Every path below MUST record a verdict on the ledger row before it
        # moves on — including the ones that produce no alert. A candidate left
        # unjudged comes back on the next scan, which is exactly the loop this
        # rewrite exists to close.
        try:
            ledger.ensure_hydrated(db, user_id, msg)
        except IntegrationNotConnected:
            raise
        except Exception as e:  # noqa: BLE001 — one unreadable message is skippable
            logger.info(f"get_meta failed for {msg_id}: {type(e).__name__}: {e}")
            continue

        sender = msg.sender or ""
        subject = msg.subject or ""
        snippet = msg.snippet or ""

        # Muted senders never become attention alerts — and are cheap to settle,
        # so record the verdict without spending an LLM call on them.
        if muted and any(m in sender.lower() for m in muted):
            ledger.mark_triaged(msg, "fyi", "skipped")
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
            ledger.mark_triaged(msg, "fyi", "skipped")
            continue

        # 2) Triage — the one metered judgement, made exactly once per message.
        verdict = classify_email(rules, sender, subject, snippet)
        tier = verdict["tier"]
        ledger.mark_triaged(msg, tier, verdict.get("source") or "ai")
        if TIER_RANK.get(tier, 0) <= TIER_RANK["fyi"]:
            continue  # only urgent / needs_reply become alerts

        deep = _deep_link(msg.rfc822_msgid, msg_id)
        alert = models.Alert(
            user_id=user_id,
            gmail_message_id=msg_id,
            thread_id=msg.thread_id,
            rfc822_msgid=msg.rfc822_msgid,
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

        # Carry the extracted ask onto the thread's open loop, so a follow-up row
        # reads "needs the revised quote by Friday" rather than "Re: Q3". Cost
        # nothing extra — it rode along in the triage call we already made.
        ask = (verdict.get("ask") or "").strip()
        if ask and msg.thread_id:
            _asks[msg.thread_id] = {
                "ask": ask[:280],
                "confidence": int(verdict.get("ask_confidence") or 0),
                "due": (verdict.get("due") or "").strip(),
            }

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
            drafted = [a for a in to_reply if a.reply_status == "drafted"]
            if drafted:
                activity.record(
                    db, user_id, "replies_drafted",
                    f"Wrote {len(drafted)} repl{'ies' if len(drafted) != 1 else 'y'} in your voice",
                    detail="Waiting for your approval — nothing sends without it.",
                    count=len(drafted),
                )
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

    # One row for the whole scan, not one per alert. The Alerts screen already
    # lists them individually; the feed's job is to say what changed, and a burst
    # of eleven separate "flagged" lines would drown the rarer events that only
    # exist here.
    if new_alerts:
        who = [activity.short_sender(a.sender or "") for a in new_alerts[:3] if a.sender]
        more = len(new_alerts) - len(who)
        activity.record(
            db, user_id, "mail_flagged",
            f"Flagged {len(new_alerts)} email{'s' if len(new_alerts) != 1 else ''} for your attention",
            detail=(", ".join(who) + (f", +{more} more" if more > 0 else "")) if who else "",
            count=len(new_alerts),
            meta={
                "urgent": sum(1 for a in new_alerts if a.tier == "urgent"),
                "needs_reply": sum(1 for a in new_alerts if a.tier == "needs_reply"),
            },
        )
    db.commit()

    # 3.5) Refresh who matters from the ledger we just extended. Pure SQL — no
    #      Gmail calls, no LLM calls — so it can ride along with every scan and
    #      the ranking is never stale by more than one interval.
    try:
        counterparty.recompute(db, user_id)
    except Exception as e:  # noqa: BLE001 — ranking is an optimisation, not the job
        logger.info(f"counterparty recompute skipped: {type(e).__name__}: {e}")

    # 3.6) Re-derive open loops, and retire alerts for threads the user has
    #      already answered somewhere else. That second part is what stops the
    #      app nagging about mail the user replied to from their phone — the
    #      single fastest way to teach someone to ignore it.
    try:
        followups.close_alerts_replied_elsewhere(db, user_id)
        followups.sync_followups(db, user_id)
        if _asks:
            followups.apply_asks(db, user_id, _asks)
    except Exception as e:  # noqa: BLE001 — follow-ups must never fail a scan
        logger.info(f"follow-up sync skipped: {type(e).__name__}: {e}")

    # 3.7) File whole conversations into folders — both directions, so the
    #      user's own replies land beside the mail they answered instead of
    #      being orphaned in Sent. Approval-gated and forward-only; see filing.py.
    filing_result: Dict[str, Any] = {}
    try:
        filing_result = filing.run_filing(db, user_id, cfg)
        labeled += int(filing_result.get("filed") or 0)
    except IntegrationNotConnected:
        raise
    except Exception as e:  # noqa: BLE001 — organising mail must not fail a scan
        logger.info(f"filing skipped: {type(e).__name__}: {e}")

    # 4) Cleanup counts + finalize the run.
    try:
        _refresh_cleanup_counts(db, user_id, run)
    except Exception as e:  # noqa: BLE001 — a counts hiccup shouldn't fail the whole scan
        logger.info(f"cleanup counts refresh failed: {type(e).__name__}: {e}")
    # One batched filing line rather than a ping per message — filing runs every
    # five minutes, so per-message notifications would be unusable. Quiet enough
    # to ignore, specific enough to catch a wrong folder early.
    summary = filing.filing_summary_line(filing_result) if filing_result else ""
    if summary:
        try:
            notify.notify_all(db, user_id, cfg, summary, tier="fyi")
        except Exception as e:  # noqa: BLE001
            logger.info(f"filing summary notify skipped: {type(e).__name__}: {e}")

    run.scanned = scanned
    run.flagged = flagged
    run.labeled = labeled
    run.notified = notified
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        # `scanned` now means "messages newly judged this run", not "messages
        # looked at" — the ledger means we don't re-look at settled mail. On an
        # unchanged inbox this is legitimately 0, so `indexed` is reported
        # alongside it and the UI says "up to date" rather than "scanned 0".
        "scanned": scanned,
        "indexed": int(sync_stats.get("in_new", 0) + sync_stats.get("out_new", 0)),
        "flagged": flagged,
        "labeled": labeled,
        "notified": notified,
        "slack_configured": bool(cfg.slack_channel),
        "promo_count": run.promo_count or 0,
        "social_count": run.social_count or 0,
        "spam_count": run.spam_count or 0,
    }
