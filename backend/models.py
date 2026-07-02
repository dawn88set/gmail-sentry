"""
Database models for Gmail Sentry.

Domain models (all user-scoped — every row carries `user_id` and every query
filters by it):
- TriageRule    — how the user defines "urgent": nl rule | vip sender | keyword
- LabelRule     — "mail from X → apply label Y (optionally archive)"
- Alert         — one flagged email surfaced to the user (+ Slack send state)
- ScanRun       — one inbox scan: counts + a snapshot of cleanup category sizes
- SentryConfig  — per-user settings (Slack channel, notify tier)

Kept from the seed (used by the SDK runtime + integrations layer):
- UserIntegration, WorkflowExecution
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text
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
    # "needs_reply" pings urgent + needs_reply.
    notify_tier = Column(String, default="urgent")

    # Extra notification channels. Each holds the NON-SECRET destination for that
    # channel (the credential lives in the platform broker). A channel is active
    # when its destination is set AND the integration is connected. Alerts fan
    # out to every active channel (see backend/integrations/notify.py).
    telegram_chat_id = Column(String, default="")   # Telegram chat/channel id
    discord_channel_id = Column(String, default="")  # Discord channel id
    teams_chat_id = Column(String, default="")       # MS Teams chat/thread id
    whatsapp_to = Column(String, default="")         # WhatsApp recipient (+E.164)

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
            "telegram_chat_id": self.telegram_chat_id or "",
            "discord_channel_id": self.discord_channel_id or "",
            "teams_chat_id": self.teams_chat_id or "",
            "whatsapp_to": self.whatsapp_to or "",
            "onboarded": bool(self.onboarded),
            "intent": self.intent or "",
            "role": self.role or "",
            "muted_senders": list(self.muted_senders or []),
        }


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
