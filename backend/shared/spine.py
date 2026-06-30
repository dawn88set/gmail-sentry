"""
B1 — The data-model spine.

Every department app is fundamentally "user-scoped items that move through a
lifecycle, some of which the user approves before we act on the outside world."
This module gives that shape once so each app's models.py is a thin delta:

    from backend.database import Base
    from backend.shared.spine import ItemMixin, LifecycleMixin

    class Lead(Base, ItemMixin, LifecycleMixin):
        __tablename__ = "leads"
        # ...only the domain-specific columns go here...

What you get:
- `ItemMixin`      : id, user_id (multi-tenant key), kind, title, body, payload,
                     source, external_id, created_at, updated_at + base_dict().
- `LifecycleMixin` : status (the seed's draft→approved→published|failed spine),
                     priority, assignee, due_at, published_at, error_message +
                     lifecycle_dict(). Pairs with backend/shared/item_routes.py.
- `AuditEvent`     : an append-only record of every transition (who/what/before/
                     after). Powers the demo-safe audit trail and the honest
                     "it failed" record.
- `record_audit()` : the one helper routes/agents call to append an AuditEvent.

Conventions match the seed (backend/models.py): plain `Column`s, string `id`
defaulting to a uuid4, `user_id` indexed, `to_dict()`-style serializers, UTC
`datetime.utcnow`. Mixins carry only plain columns (no relationships/FKs), so
they compose cleanly and the additive schema reconciler in database.py picks up
new columns on redeploy.
"""

from datetime import datetime
import uuid

from sqlalchemy import Column, String, Text, DateTime, JSON

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Lifecycle status — aligned with the seed's documented approval pattern
# (CLAUDE.md / INTEGRATIONS.md: draft → approved → published | failed). We add
# the two "before a draft exists" states an agent pipeline naturally produces
# (new → triaged) and the explicit user "no" (rejected). Keep these as the
# canonical vocabulary so every app's lifecycle reads the same.
# ---------------------------------------------------------------------------
class ItemStatus:
    NEW = "new"                      # ingested, not yet processed by an agent
    TRIAGED = "triaged"             # classified/scored, no draft yet
    PLANNED = "planned"             # a dated calendar slot reserved, no body yet
    DRAFT = "draft"                 # an agent produced a draft to review
    PENDING_APPROVAL = "pending_approval"  # draft awaiting a human decision
    APPROVED = "approved"           # human said yes; about to act externally
    SCHEDULED = "scheduled"         # approved + scheduled_for set; awaiting the sweep
    PUBLISHED = "published"         # the real external action succeeded
    FAILED = "failed"               # the external action genuinely failed
    REJECTED = "rejected"           # human said no

    #: Statuses an item can be in while it still wants human attention.
    OPEN = (NEW, TRIAGED, PLANNED, DRAFT, PENDING_APPROVAL, FAILED)
    #: Terminal statuses — no further action expected.
    CLOSED = (PUBLISHED, REJECTED)
    #: Transient/automatic states between approval and publish — in neither set
    #: (the scheduled sweep advances them without human attention).
    SCHEDULED_PENDING = (APPROVED, SCHEDULED)

    ALL = (NEW, TRIAGED, PLANNED, DRAFT, PENDING_APPROVAL, APPROVED, SCHEDULED, PUBLISHED, FAILED, REJECTED)


class ItemMixin:
    """
    The common columns every user-facing item carries.

    `payload` is the escape hatch for domain-specific structured fields that
    don't deserve their own column (e.g. the parsed fields of an invoice, the
    enrichment an agent attached). `source` records which integration/origin
    produced the row; `external_id` is set ONLY when the item has been pushed to
    a real external system (an email message id, a CRM record id) — never faked.
    """

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)  # multi-tenancy key

    kind = Column(String, index=True)        # app-defined item type, e.g. "lead"
    title = Column(String, nullable=False)   # one-line human label
    body = Column(Text)                       # the main text (draft, email body…)
    payload = Column(JSON)                    # arbitrary structured domain fields

    source = Column(String, index=True)       # which integration/origin produced it
    external_id = Column(String, index=True)  # set only after a real external action

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def base_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "payload": self.payload,
            "source": self.source,
            "external_id": self.external_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LifecycleMixin:
    """
    The approve-before-act lifecycle. Defaults to `new` so freshly ingested
    items start at the top of the funnel. `published_at`/`external_id`
    (ItemMixin) are set together only on a genuine external success;
    `error_message` records an honest failure (the row stays open for retry).
    """

    status = Column(String, default=ItemStatus.NEW, index=True)
    priority = Column(String, default="medium", index=True)  # low|medium|high|urgent
    assignee = Column(String, index=True)
    due_at = Column(DateTime, index=True)
    published_at = Column(DateTime)
    error_message = Column(Text)

    def lifecycle_dict(self) -> dict:
        return {
            "status": self.status,
            "priority": self.priority,
            "assignee": self.assignee,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "error_message": self.error_message,
        }

    def to_dict(self) -> dict:
        """Full serialization for apps whose item inherits both mixins.

        Apps that need extra fields override `to_dict` and spread this in:
            return {**super().to_dict(), "score": self.score}
        """
        # base_dict comes from ItemMixin when both are mixed in.
        base = self.base_dict() if hasattr(self, "base_dict") else {"id": getattr(self, "id", None)}
        return {**base, **self.lifecycle_dict()}


PRIORITY_RANK = {"urgent": 3, "high": 2, "medium": 1, "low": 0}


class AuditEvent(Base):
    """
    Append-only audit trail shared by every app. One row per lifecycle
    transition (created, triaged, drafted, edited, approved, published,
    dispatch_failed, rejected). This is what makes the human-in-the-loop story
    demo-safe: every action is attributable and the honest failures are on the
    record. Never updated or deleted.
    """

    __tablename__ = "audit_events"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)

    item_id = Column(String, index=True)
    item_kind = Column(String, index=True)

    action = Column(String, nullable=False, index=True)
    actor = Column(String)   # "agent" | "user:<id>" | "system"
    before = Column(JSON)    # relevant fields before the transition
    after = Column(JSON)     # relevant fields after the transition
    detail = Column(Text)    # free-text note (e.g. an error message)

    at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_kind": self.item_kind,
            "action": self.action,
            "actor": self.actor,
            "before": self.before,
            "after": self.after,
            "detail": self.detail,
            "at": self.at.isoformat() if self.at else None,
        }


def record_audit(
    db,
    *,
    item=None,
    action: str,
    actor: str = "system",
    user_id: str = None,
    item_id: str = None,
    item_kind: str = None,
    before: dict = None,
    after: dict = None,
    detail: str = None,
) -> AuditEvent:
    """
    Append an AuditEvent. Pass an `item` (an ItemMixin row) to auto-fill
    user_id/item_id/item_kind, or pass them explicitly. The caller is
    responsible for committing the session (so the audit row commits atomically
    with the transition it describes).
    """
    if item is not None:
        user_id = user_id or getattr(item, "user_id", None)
        item_id = item_id or getattr(item, "id", None)
        item_kind = item_kind or getattr(item, "kind", None) or getattr(item, "__tablename__", None)

    if not user_id:
        raise ValueError("record_audit requires a user_id (directly or via item)")

    event = AuditEvent(
        user_id=user_id,
        item_id=item_id,
        item_kind=item_kind,
        action=action,
        actor=actor,
        before=before,
        after=after,
        detail=detail,
    )
    db.add(event)
    return event
