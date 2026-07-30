"""
Tests for B1 — the shared data-model spine (backend/shared/spine.py).

Exercises the real ORM mapping against in-memory SQLite: a model built from the
mixins gets the lifecycle defaults, serializes via to_dict(), and record_audit()
writes an append-only AuditEvent row.
"""

from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.shared.spine import (
    ItemMixin,
    LifecycleMixin,
    ItemStatus,
    AuditEvent,
    record_audit,
)


# A throwaway domain model that uses the spine exactly as a real app would.
class _SpineTestItem(Base, ItemMixin, LifecycleMixin):
    __tablename__ = "spine_test_items"
    score = Column(Integer)  # a domain-specific extra column

    def to_dict(self):  # apps extend the spine serializer like this
        return {**super().to_dict(), "score": self.score}


def _session():
    engine = create_engine("sqlite://")  # in-memory
    # Create only the tables this test needs.
    Base.metadata.create_all(
        bind=engine,
        tables=[_SpineTestItem.__table__, AuditEvent.__table__],
    )
    return sessionmaker(bind=engine)()


def test_item_defaults_and_serialization():
    db = _session()
    item = _SpineTestItem(user_id="u1", kind="lead", title="Acme inbound", score=7)
    db.add(item)
    db.commit()
    db.refresh(item)

    # Lifecycle defaults applied on insert.
    assert item.id  # uuid default
    assert item.status == ItemStatus.NEW
    assert item.priority == "medium"
    assert item.created_at is not None

    d = item.to_dict()
    # Spans both mixins + the domain extra.
    for key in ("id", "kind", "title", "source", "external_id", "status", "priority", "score"):
        assert key in d
    assert d["kind"] == "lead"
    assert d["score"] == 7


def test_record_audit_appends_event_from_item():
    db = _session()
    item = _SpineTestItem(user_id="u1", kind="lead", title="Acme inbound")
    db.add(item)
    db.commit()

    record_audit(
        db,
        item=item,
        action="published",
        actor="user:u1",
        before={"status": "approved"},
        after={"status": "published", "external_id": "msg_123"},
        detail="sent via gmail",
    )
    db.commit()

    events = db.query(AuditEvent).filter(AuditEvent.item_id == item.id).all()
    assert len(events) == 1
    ev = events[0]
    assert ev.user_id == "u1"
    assert ev.item_kind == "lead"
    assert ev.action == "published"
    assert ev.actor == "user:u1"
    assert ev.after["external_id"] == "msg_123"
    assert ev.to_dict()["action"] == "published"


def test_record_audit_requires_user_id():
    db = _session()
    try:
        record_audit(db, action="created")  # no item, no user_id
    except ValueError:
        return
    raise AssertionError("record_audit should require a user_id")


def test_status_sets_are_disjoint_and_complete():
    assert set(ItemStatus.OPEN).isdisjoint(ItemStatus.CLOSED)
    # APPROVED and SCHEDULED are transient (post-approval, pre-publish) and are
    # deliberately in neither set — the sweep advances them with no human
    # attention. spine.py groups them as SCHEDULED_PENDING; assert against that
    # rather than restating the members, so a new transient status can't make
    # ALL silently incomplete again.
    assert set(ItemStatus.OPEN).isdisjoint(ItemStatus.SCHEDULED_PENDING)
    assert set(ItemStatus.CLOSED).isdisjoint(ItemStatus.SCHEDULED_PENDING)
    assert (
        set(ItemStatus.OPEN) | set(ItemStatus.CLOSED) | set(ItemStatus.SCHEDULED_PENDING)
        == set(ItemStatus.ALL)
    )
