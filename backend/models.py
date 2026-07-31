"""
Database models for Gmail Sentry.

Domain models (all user-scoped — every row carries `user_id` and every query
filters by it):
- TriageRule    — how the user defines "urgent": nl rule | vip sender | keyword
- LabelRule     — "mail from X → apply label Y (optionally archive)"
- Alert         — one flagged email surfaced to the user (+ Slack send state)
- ScanRun       — one inbox scan: counts + a snapshot of cleanup category sizes
- SentryConfig  — per-user settings (Slack channel, notify tier)
- CommProfile   — the learned voice + the people the user actually replies to
- ThreadMessage — the thread ledger: every observed message, in and out
- ThreadSyncState — the ledger's per-user sweep cursor

Kept from the seed (used by the SDK runtime + integrations layer):
- UserIntegration, WorkflowExecution
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text, UniqueConstraint
from datetime import datetime
import uuid
from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TriageRule(Base):
    """A user-defined signal for deciding an email needs attention.

    kind:
      - "nl"         → free-text rule judged by the LLM (value = the rule text)
      - "vip_sender" → an email address or domain (value = "boss@acme.com" / "acme.com")
      - "keyword"    → a substring matched in subject/snippet (value = "invoice")
    tier: which tier a match implies — "urgent" | "needs_reply" | "fyi".
    """
    __tablename__ = "triage_rules"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, default="nl")  # nl | vip_sender | keyword
    value = Column(Text, nullable=False)
    tier = Column(String, nullable=False, default="urgent")  # urgent | needs_reply | fyi
    active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "value": self.value,
            "tier": self.tier,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LabelRule(Base):
    """Filing rule: when a new email matches, apply a Gmail label (and optionally
    archive it out of the inbox)."""
    __tablename__ = "label_rules"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    name = Column(String, nullable=False)
    match_type = Column(String, nullable=False, default="sender")  # sender | domain | subject_keyword
    match_value = Column(Text, nullable=False)
    target_label = Column(String, nullable=False)
    archive_after = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "match_type": self.match_type,
            "match_value": self.match_value,
            "target_label": self.target_label,
            "archive_after": self.archive_after,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Alert(Base):
    """A flagged email the Sentry wants the user to see."""
    __tablename__ = "alerts"
    # One alert per message per user — the DB rejects duplicate inserts from
    # overlapping scan runs (see migration 0006 + run_scan's IntegrityError catch).
    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_alerts_user_msg"),
    )

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    gmail_message_id = Column(String, nullable=False, index=True)
    thread_id = Column(String)
    rfc822_msgid = Column(String)  # the Message-ID header → robust Gmail deep link

    sender = Column(String)
    subject = Column(String)
    snippet = Column(Text)

    tier = Column(String, nullable=False, default="urgent", index=True)  # urgent | needs_reply | fyi
    reason = Column(Text)
    deep_link = Column(Text)

    slack_sent = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String, nullable=False, default="new", index=True)  # new | seen | snoozed | done | dismissed
    snoozed_until = Column(DateTime)  # when a snoozed alert should resurface

    # Reply lifecycle. The app drafts a reply (in the user's voice), the user
    # approves, and the app SENDS it through the broker. reply_status only reaches
    # "sent" on a real returned Gmail message id — never faked.
    reply_draft = Column(Text)          # the current drafted reply body
    reply_status = Column(String, nullable=False, default="none")  # none | drafted | sent | failed
    reply_sent_at = Column(DateTime)    # when the reply was actually sent
    reply_external_id = Column(String)  # Gmail message id of the sent reply
    reply_error = Column(Text)          # last send failure (row survives for retry)

    #: The thread-level open loop this message belongs to, if any. An alert is
    #: a notification event; the follow-up is the state that outlives it.
    followup_id = Column(String, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "gmail_message_id": self.gmail_message_id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "subject": self.subject,
            "snippet": self.snippet,
            "tier": self.tier,
            "reason": self.reason,
            "deep_link": self.deep_link,
            "slack_sent": self.slack_sent,
            "status": self.status,
            "snoozed_until": self.snoozed_until.isoformat() if self.snoozed_until else None,
            "reply_draft": self.reply_draft or "",
            "reply_status": self.reply_status or "none",
            "reply_sent_at": self.reply_sent_at.isoformat() if self.reply_sent_at else None,
            "followup_id": self.followup_id or None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScanRun(Base):
    """Audit + snapshot of one inbox scan. The latest row drives the widget's
    'last scan' and cleanup counts without re-hitting Gmail."""
    __tablename__ = "scan_runs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    scanned = Column(Integer, default=0)
    flagged = Column(Integer, default=0)
    labeled = Column(Integer, default=0)
    notified = Column(Integer, default=0)

    promo_count = Column(Integer, default=0)
    social_count = Column(Integer, default=0)
    spam_count = Column(Integer, default=0)

    error = Column(Text)  # set when the scan couldn't run (e.g. gmail not connected)

    started_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "scanned": self.scanned,
            "flagged": self.flagged,
            "labeled": self.labeled,
            "notified": self.notified,
            "promo_count": self.promo_count,
            "social_count": self.social_count,
            "spam_count": self.spam_count,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }


class SentryConfig(Base):
    """Per-user settings. One row per user."""
    __tablename__ = "sentry_config"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, unique=True, index=True)

    # Where Slack pings go: a channel id/name (e.g. "#gmail-sentry") or a Slack
    # member id (e.g. "U0123") to DM yourself. Empty → no pings (UI prompts to set it).
    slack_channel = Column(String, default="")
    # Lowest tier that triggers a ping: "urgent" pings only urgent,
    # "needs_reply" pings urgent + needs_reply. Acts as the DEFAULT floor for any
    # channel without its own override in `channel_tiers`.
    notify_tier = Column(String, default="urgent")

    # Per-channel urgency routing (overrides notify_tier per channel), e.g.
    # {"whatsapp": "urgent", "slack": "needs_reply"}. A channel absent here falls
    # back to notify_tier. Lets urgent go to one channel and replies to another.
    channel_tiers = Column(JSON, default=dict)

    # Extra notification channels. Each holds the NON-SECRET destination for that
    # channel (the credential lives in the platform broker). A channel is active
    # when its destination is set AND the integration is connected. Alerts fan
    # out to every active channel (see backend/integrations/notify.py).
    telegram_chat_id = Column(String, default="")   # Telegram chat/channel id
    discord_channel_id = Column(String, default="")  # Discord channel id
    teams_chat_id = Column(String, default="")       # MS Teams chat/thread id
    whatsapp_to = Column(String, default="")         # WhatsApp recipient (+E.164)

    # When true, the scan pre-drafts a reply (in the user's voice) for each
    # needs_reply alert so the notification can carry it and the user can approve
    # in one tap. The app never auto-SENDS — approval is always explicit.
    auto_draft = Column(Boolean, nullable=False, default=True)

    # Smart-onboarding state. `onboarded` gates the setup wizard; `intent`/`role`
    # remember what the user asked the assistant to do so it can be refined later.
    onboarded = Column(Boolean, nullable=False, default=False)
    intent = Column(Text, default="")
    role = Column(String, default="")
    # Senders (email or domain) to never flag as attention. Fed by the
    # "Mute sender" action on an alert.
    muted_senders = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "slack_channel": self.slack_channel or "",
            "notify_tier": self.notify_tier or "urgent",
            "channel_tiers": dict(self.channel_tiers or {}),
            "telegram_chat_id": self.telegram_chat_id or "",
            "discord_channel_id": self.discord_channel_id or "",
            "teams_chat_id": self.teams_chat_id or "",
            "whatsapp_to": self.whatsapp_to or "",
            "auto_draft": bool(self.auto_draft),
            "onboarded": bool(self.onboarded),
            "intent": self.intent or "",
            "role": self.role or "",
            "muted_senders": list(self.muted_senders or []),
        }


class CommProfile(Base):
    """What Gmail Sentry has learned about how the user actually communicates.
    One row per user, refreshed periodically from real sent + inbox signals. Used
    to (a) boost triage for the people they actually correspond with and (b) draft
    replies in their real voice (tone + a few of their own sent-mail exemplars)."""
    __tablename__ = "comm_profiles"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, unique=True, index=True)

    # People the user actually corresponds with — behavioral VIPs. [{email,name,count}]
    vip_senders = Column(JSON, default=list)
    # Lightweight, honestly-derivable habits (e.g. {"frequent_contacts": [...]}).
    response_habits = Column(JSON, default=dict)
    # A short natural-language descriptor of their writing voice, e.g.
    # "warm, concise, first-name greeting, signs off 'Best'".
    tone = Column(String, default="")
    # A few excerpts of the user's own sent mail, to mirror their style in drafts.
    style_exemplars = Column(JSON, default=list)
    signature = Column(String, default="")

    refreshed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "vip_senders": list(self.vip_senders or []),
            "response_habits": dict(self.response_habits or {}),
            "tone": self.tone or "",
            "style_exemplars": list(self.style_exemplars or []),
            "signature": self.signature or "",
            "refreshed_at": self.refreshed_at.isoformat() if self.refreshed_at else None,
        }


class ThreadMessage(Base):
    """One observed Gmail message — the local reconstruction of the mailbox.

    Why this exists: the app used to have memory of *alerts* but not of *mail*,
    which cost it three things at once.

    1. **Cost.** A message classified `fyi` produced no row, so every 5-minute
       scan re-fetched and re-classified it for two days. `triage_tier` here is
       the permanent receipt: a message is judged by the LLM exactly once, ever.
    2. **Incremental sync.** The scan re-queried a fixed `newer_than:2d` window
       every time. The sweep now advances a watermark.
    3. **Thread state.** Grouping these rows by `thread_id` says who owes whom a
       reply — including replies the user sent from their phone, which the app
       could not previously see at all.

    **Time.** The broker's `gmail.get_message` returns no date, so we recover it
    from the *query window* instead of the message: each row records the
    `after:`/`before:` bounds it was found in. The working clock is `ts_hi` (the
    latest the message could be), which is deliberately conservative — an aging
    clock built on it under-ages, so we never chase someone too early.

    Rows are append-only; identity fields fill in later (see `hydrated`) because
    `gmail.search` hands us `{id, threadId}` for free while sender/subject cost a
    metered `get_message` call each.
    """
    __tablename__ = "thread_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_tmsg_user_msg"),
    )

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    gmail_message_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)
    # "in" = the user received it; "out" = the user sent it (from anywhere —
    # this app, Gmail on the web, or their phone).
    direction = Column(String, nullable=False)

    # The query window this message was found in — NOT the message's own date.
    ts_lo = Column(DateTime, nullable=False)
    ts_hi = Column(DateTime, nullable=False, index=True)
    # True only for sends this app performed itself, where we know the instant.
    ts_exact = Column(Boolean, nullable=False, default=False)

    # Identity — NULL until hydrated. The state machine never needs it.
    hydrated = Column(Boolean, nullable=False, default=False, index=True)
    sender = Column(String)
    counterparty_email = Column(String, index=True)
    subject = Column(String)
    snippet = Column(Text)
    rfc822_msgid = Column(String)
    label_ids = Column(JSON, default=list)

    # Triage memoization. Set for EVERY judged message, including `fyi` and
    # muted senders — a missing verdict is what caused the re-classification bug.
    triage_tier = Column(String, index=True)
    triage_source = Column(String)  # ai | heuristic | skipped
    triaged_at = Column(DateTime, index=True)

    first_seen_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return (
            f"<ThreadMessage {self.direction} thread={self.thread_id} "
            f"tier={self.triage_tier}>"
        )


class ThreadSyncState(Base):
    """Per-user cursor for the ledger sweep. One row per user.

    Watermarks advance only after a window completes successfully — a
    mid-pagination failure must not leave a permanent hole in the ledger.
    """
    __tablename__ = "thread_sync_state"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, unique=True, index=True)

    # Forward sweep: how far we've indexed each mailbox.
    inbox_watermark = Column(DateTime)
    sent_watermark = Column(DateTime)

    # Backward sweep: walks back to `horizon_days`, a bounded number of buckets
    # per run so the first sync can't stall a scan. NULL once complete.
    backfill_cursor = Column(DateTime)
    backfill_done = Column(Boolean, nullable=False, default=False)
    backfill_done_at = Column(DateTime)
    horizon_days = Column(Integer, nullable=False, default=45)

    # Learned once, from any sent message: who "the user" is, so an outbound
    # message can be told from an inbound one and internal from external.
    self_address = Column(String, default="")
    self_domain = Column(String, default="")
    alias_addresses = Column(JSON, default=list)

    # get_message calls allowed per sweep (identity is the metered part).
    hydration_budget = Column(Integer, nullable=False, default=25)

    messages_indexed = Column(Integer, default=0)
    last_sweep_at = Column(DateTime)
    last_error = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "inbox_watermark": self.inbox_watermark.isoformat() if self.inbox_watermark else None,
            "sent_watermark": self.sent_watermark.isoformat() if self.sent_watermark else None,
            "backfill_done": bool(self.backfill_done),
            "horizon_days": int(self.horizon_days or 45),
            "self_address": self.self_address or "",
            "messages_indexed": int(self.messages_indexed or 0),
            "last_sweep_at": self.last_sweep_at.isoformat() if self.last_sweep_at else None,
            "last_error": self.last_error or "",
        }

    def __repr__(self):
        return f"<ThreadSyncState user={self.user_id} indexed={self.messages_indexed}>"


class Counterparty(Base):
    """A person the user corresponds with, and what their behaviour says.

    This replaces the top-5 `vip_senders` list the scan used to inject as
    synthetic rules. That list answered "who does this user email a lot?"; this
    answers the question that actually matters — **who would it cost them to
    ignore?** — and it does so from revealed preference rather than volume:
    someone the user always replies to, quickly, over many threads, matters.
    A newsletter that sends daily does not.

    Everything here is derived from the thread ledger by plain SQL. No Gmail
    calls, no LLM calls. The CRM columns are the one exception and are strictly
    optional enrichment — every one of them is nullable and the app is complete
    without them.

    Two honest caveats:
      * Latency figures inherit the ledger's window resolution, so treat them as
        "about this many hours", not a stopwatch.
      * Outbound messages carry no recipient unless this app sent them, so a
        reply is attributed to the counterparty of its THREAD. That is right for
        ordinary correspondence and approximate on large group threads.
    """
    __tablename__ = "counterparties"
    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_cp_user_email"),)

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    email = Column(String, nullable=False, index=True)
    domain = Column(String, index=True)
    display_name = Column(String, default="")
    # Same domain as the user — colleagues, not customers.
    is_internal = Column(Boolean, nullable=False, default=False)

    # ── behavioural facts, recomputed from the ledger ──────────────────────
    msg_in_count = Column(Integer, default=0)
    msg_out_count = Column(Integer, default=0)
    thread_count = Column(Integer, default=0)
    threads_you_replied = Column(Integer, default=0)
    #: Of their threads, how many you answered. The strongest single signal of
    #: whether this person matters to the user — it's a choice they already made.
    your_reply_rate = Column(Integer, default=0)   # 0-100
    #: Of the threads you started, how many they answered. Whether YOU matter to
    #: THEM — which is what makes a silence meaningful rather than routine.
    their_reply_rate = Column(Integer, default=0)  # 0-100
    your_median_reply_h = Column(Integer)
    their_median_reply_h = Column(Integer)

    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime, index=True)

    # ── derived judgement ──────────────────────────────────────────────────
    relationship = Column(String, default="unknown")
    # customer | prospect | internal | vendor | personal | bulk | unknown
    relationship_source = Column(String, default="inferred")  # inferred | crm | user
    importance = Column(Integer, default=0, index=True)  # 0-100

    # ── optional CRM enrichment (fail-soft; never a dependency) ────────────
    crm_source = Column(String, default="")
    crm_id = Column(String, default="")
    crm_company = Column(String, default="")
    crm_stage = Column(String, default="")
    crm_owner = Column(String, default="")
    crm_checked_at = Column(DateTime)
    crm_status = Column(String, default="")  # ok | not_connected | not_found | error | unsupported

    # ── user overrides — always win over inference ─────────────────────────
    pinned = Column(Boolean, nullable=False, default=False)
    muted = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "domain": self.domain or "",
            "display_name": self.display_name or "",
            "is_internal": bool(self.is_internal),
            "thread_count": int(self.thread_count or 0),
            "msg_in_count": int(self.msg_in_count or 0),
            "msg_out_count": int(self.msg_out_count or 0),
            "your_reply_rate": int(self.your_reply_rate or 0),
            "their_reply_rate": int(self.their_reply_rate or 0),
            "your_median_reply_h": self.your_median_reply_h,
            "their_median_reply_h": self.their_median_reply_h,
            "relationship": self.relationship or "unknown",
            "relationship_source": self.relationship_source or "inferred",
            "importance": int(self.importance or 0),
            "pinned": bool(self.pinned),
            "muted": bool(self.muted),
            "crm": {
                "source": self.crm_source or "",
                "company": self.crm_company or "",
                "stage": self.crm_stage or "",
                "status": self.crm_status or "",
            },
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }

    def __repr__(self):
        return f"<Counterparty {self.email} importance={self.importance} rel={self.relationship}>"


class FollowUp(Base):
    """An open loop on one thread — the thing the user actually wants to see.

    `Alert` and `FollowUp` answer different questions and neither replaces the
    other:

      Alert     one MESSAGE   "does this need your eyes right now?"
      FollowUp  one THREAD    "is there an unresolved loop here?"

    An alert dies when the user handles the message. A follow-up lives until the
    loop actually closes — which is why sending a reply *advances* it to
    `awaiting_them` rather than ending it. Before this existed, the moment a
    reply was sent the thread vanished from the app entirely, so "I sent them a
    quote and never heard back" was invisible.

    **The boundary that stops double-counting.** A newly-arrived message that
    needs a reply is an Alert for its first `owed_after_hours`; after that the
    alert has served its purpose and the THREAD becomes an owed follow-up. Lists
    exclude threads whose latest inbound still has a live alert, so
    `active alerts + owed + overdue-waiting` is a partition and the headline
    number can be trusted.
    """
    __tablename__ = "followups"
    __table_args__ = (UniqueConstraint("user_id", "thread_id", name="uq_followups_user_thread"),)

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)

    counterparty_email = Column(String, index=True)
    counterparty_name = Column(String, default="")
    subject = Column(String, default="")

    #: awaiting_you | awaiting_them | going_cold | snoozed | done | ignored
    state = Column(String, nullable=False, default="awaiting_you", index=True)
    #: The raw ledger fact the state is derived from: "you" | "them".
    ball = Column(String, nullable=False, default="you")
    #: When the ball last changed hands — the clock everything ages against.
    state_changed_at = Column(DateTime, default=datetime.utcnow, index=True)

    #: One line saying what is actually being asked, extracted during triage at
    #: no extra model cost. This is the payload of a follow-up row: "Re: Q3"
    #: tells you nothing, "needs the budget approved before Friday" tells you
    #: everything.
    ask_summary = Column(String(280), default="")
    ask_confidence = Column(Integer, default=0)
    due_at = Column(DateTime, index=True)
    due_source = Column(String, default="")  # explicit | inferred

    last_inbound_at = Column(DateTime, index=True)
    last_outbound_at = Column(DateTime, index=True)
    last_activity_at = Column(DateTime, index=True)

    #: How long silence is normal FOR THIS PERSON, from their median reply time.
    #: A lawyer who answers in three days shouldn't be chased after one; a
    #: customer who normally answers in two hours is already cold at two days.
    stale_after_hours = Column(Integer, default=72)
    importance = Column(Integer, default=0, index=True)
    risk = Column(Integer, default=0, index=True)

    nudge_count = Column(Integer, nullable=False, default=0)
    last_nudge_at = Column(DateTime)
    snoozed_until = Column(DateTime)

    closed_reason = Column(String, default="")
    # they_replied | you_closed | archived | muted | expired | replied_externally
    closed_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "counterparty_email": self.counterparty_email or "",
            "counterparty_name": self.counterparty_name or "",
            "subject": self.subject or "",
            "state": self.state,
            "ball": self.ball,
            "ask_summary": self.ask_summary or "",
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "due_source": self.due_source or "",
            "last_inbound_at": self.last_inbound_at.isoformat() if self.last_inbound_at else None,
            "last_outbound_at": self.last_outbound_at.isoformat() if self.last_outbound_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "stale_after_hours": int(self.stale_after_hours or 72),
            "importance": int(self.importance or 0),
            "risk": int(self.risk or 0),
            "nudge_count": int(self.nudge_count or 0),
            "snoozed_until": self.snoozed_until.isoformat() if self.snoozed_until else None,
            "closed_reason": self.closed_reason or "",
        }

    def __repr__(self):
        return f"<FollowUp {self.state} thread={self.thread_id} risk={self.risk}>"


class Nudge(Base):
    """A proposed follow-up message on a thread that has gone quiet.

    Draft-only by construction. There is no code path that sends one without an
    explicit request from the user, and none is ever pre-generated — unlike a
    reply, a nudge answers no incoming message, so a pre-drafted one sitting in
    a list is a single mis-tap away from an unrequested email to a client.
    """
    __tablename__ = "nudges"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    followup_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, index=True)

    attempt_no = Column(Integer, nullable=False, default=1)
    tone = Column(String, default="gentle")  # gentle | direct | closing

    draft = Column(Text, default="")
    subject = Column(String, default="")
    to_email = Column(String, default="")
    in_reply_to = Column(String, default="")

    #: proposed | sent | skipped | failed. Never "approved-and-queued" — there
    #: is deliberately no state in which a nudge is waiting to send itself.
    status = Column(String, nullable=False, default="proposed", index=True)
    sent_at = Column(DateTime)
    external_id = Column(String, default="")
    error = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "followup_id": self.followup_id,
            "attempt_no": int(self.attempt_no or 1),
            "tone": self.tone or "gentle",
            "draft": self.draft or "",
            "subject": self.subject or "",
            "to_email": self.to_email or "",
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "error": self.error or "",
        }

    def __repr__(self):
        return f"<Nudge {self.status} attempt={self.attempt_no} followup={self.followup_id}>"


class UserIntegration(Base):
    """User-connected integrations (OAuth, API keys). Kept — the integrations
    layer + workflow runtime use it."""
    __tablename__ = "user_integrations"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    service = Column(String, nullable=False, index=True)
    auth_type = Column(String)
    credentials = Column(JSON)
    scopes = Column(JSON)
    connected_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True, index=True)

    def __repr__(self):
        return f"<UserIntegration user={self.user_id} service={self.service}>"


class WorkflowExecution(Base):
    """Workflow execution history (written by the workflow execute endpoint)."""
    __tablename__ = "workflow_executions"

    id = Column(String, primary_key=True, default=_uuid)
    workflow_id = Column(String, nullable=False, index=True)
    trigger_id = Column(String, index=True)
    user_id = Column(String, index=True)

    status = Column(String, index=True)
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)

    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)

    def __repr__(self):
        return f"<WorkflowExecution id={self.id} workflow={self.workflow_id} status={self.status}>"
