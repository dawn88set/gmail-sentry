"""
Tests for B4 — persist_item (backend/shared/agent_tools.py).

Verifies the shared save-tool logic: it creates a PENDING_APPROVAL spine item +
an audit row, derives priority from score, applies known domain fields via
`extra`, and ignores unknown ones (so the same helper works across models).
"""

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.shared.spine import ItemMixin, LifecycleMixin, ItemStatus, AuditEvent
from backend.shared.agent_tools import persist_item, derive_priority


class _Ticket(Base, ItemMixin, LifecycleMixin):
    __tablename__ = "test_tickets"
    score = Column(Integer)
    contact_email = Column(String)


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine, tables=[_Ticket.__table__, AuditEvent.__table__])
    return sessionmaker(bind=engine)()


def test_derive_priority_buckets():
    assert derive_priority(90) == "urgent"
    assert derive_priority(70) == "high"
    assert derive_priority(40) == "medium"
    assert derive_priority(10) == "low"
    assert derive_priority(None) == "medium"


def test_persist_item_creates_pending_with_audit_and_fields():
    db = _session()
    tid = persist_item(
        db, _Ticket, user_id="u1",
        title="Refund request", body="Drafted reply…", kind="ticket",
        source="gmail", score=82, reason="explicit refund ask",
        payload={"thread_id": "t9"},
        extra={"contact_email": "buyer@acme.com", "nonexistent": "ignored"},
    )
    assert tid

    row = db.query(_Ticket).filter(_Ticket.id == tid).one()
    assert row.status == ItemStatus.PENDING_APPROVAL
    assert row.priority == "urgent"            # derived from score 82
    assert row.score == 82                      # applied (model has the column)
    assert row.contact_email == "buyer@acme.com"  # extra applied
    assert row.payload["thread_id"] == "t9"
    assert not hasattr(row, "nonexistent")      # unknown extra ignored, no crash

    events = db.query(AuditEvent).filter(AuditEvent.item_id == tid).all()
    assert len(events) == 1
    assert events[0].action == "drafted" and events[0].actor == "agent"


def test_persist_item_explicit_priority_wins():
    db = _session()
    tid = persist_item(db, _Ticket, user_id="u1", title="x", priority="low", score=99)
    row = db.query(_Ticket).filter(_Ticket.id == tid).one()
    assert row.priority == "low"  # explicit priority overrides score-derived
