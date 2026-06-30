"""
Tests for B2 — the item/lifecycle route factory (backend/shared/item_routes.py).

Spins up a FastAPI app wired to the factory over in-memory SQLite, overriding the
db + identity dependencies, and asserts the lifecycle + the non-negotiable
honest-publish semantics:
  - publish returns an external id           -> 200, status=published, audit
  - publish raises IntegrationNotConnected   -> 409, status unchanged (no fake)
  - publish raises a real error              -> 502, status=failed, audit
  - publish returns no external id           -> 502, status=failed (not success)
  - reject / edit transitions + widget shape
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.security import require_user
from backend.shared.spine import ItemMixin, LifecycleMixin, ItemStatus, AuditEvent
from backend.shared.item_routes import make_item_router
from backend.shared.adapters import IntegrationNotConnected, IntegrationError


class _Lead(Base, ItemMixin, LifecycleMixin):
    __tablename__ = "test_leads"


def _make_client(publish):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[_Lead.__table__, AuditEvent.__table__])
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _seed_one(**kw):
        db = TestSession()
        lead = _Lead(user_id="u1", kind="lead", title="Acme inbound",
                     body="hi", status=ItemStatus.PENDING_APPROVAL, **kw)
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lid = lead.id
        db.close()
        return lid

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(make_item_router(_Lead, publish=publish, kind="lead"))
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_user] = lambda: "u1"
    return TestClient(app), _seed_one, TestSession


def test_approve_publishes_with_external_id():
    def publish(db, user_id, item):
        return {"external_id": "msg_123", "account": "rep@acme.com"}

    client, seed, Session = _make_client(publish)
    lid = seed()

    r = client.post(f"/api/items/{lid}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == ItemStatus.PUBLISHED
    assert r.json()["external_id"] == "msg_123"

    db = Session()
    events = db.query(AuditEvent).filter(AuditEvent.item_id == lid).all()
    assert any(e.action == "published" for e in events)


def test_approve_not_connected_returns_409_and_does_not_publish():
    def publish(db, user_id, item):
        raise IntegrationNotConnected("gmail")

    client, seed, Session = _make_client(publish)
    lid = seed()

    r = client.post(f"/api/items/{lid}/approve")
    assert r.status_code == 409
    assert r.json()["detail"]["service"] == "gmail"

    # Status must NOT have advanced — no faked success.
    got = client.get(f"/api/items/{lid}").json()
    assert got["status"] == ItemStatus.PENDING_APPROVAL
    assert got["external_id"] is None


def test_approve_real_failure_returns_502_and_marks_failed():
    def publish(db, user_id, item):
        raise IntegrationError("gmail", "SMTP exploded")

    client, seed, Session = _make_client(publish)
    lid = seed()

    r = client.post(f"/api/items/{lid}/approve")
    assert r.status_code == 502

    got = client.get(f"/api/items/{lid}").json()
    assert got["status"] == ItemStatus.FAILED
    assert "exploded" in (got["error_message"] or "")

    db = Session()
    events = db.query(AuditEvent).filter(AuditEvent.item_id == lid).all()
    assert any(e.action == "dispatch_failed" for e in events)


def test_approve_without_external_id_is_not_success():
    def publish(db, user_id, item):
        return {}  # no external id -> must be treated as failure

    client, seed, Session = _make_client(publish)
    lid = seed()

    r = client.post(f"/api/items/{lid}/approve")
    assert r.status_code == 502
    assert client.get(f"/api/items/{lid}").json()["status"] == ItemStatus.FAILED


def test_reject_and_edit_and_widget():
    def publish(db, user_id, item):
        return {"external_id": "x"}

    client, seed, Session = _make_client(publish)
    lid = seed()

    # edit keeps it open and pending
    r = client.post(f"/api/items/{lid}/edit", json={"body": "revised"})
    assert r.status_code == 200
    assert r.json()["body"] == "revised"
    assert r.json()["status"] == ItemStatus.PENDING_APPROVAL

    # widget reflects one open + one pending
    w = client.get("/api/widget?size=large").json()
    assert w["open_count"] == 1
    assert w["pending_count"] == 1
    assert len(w["items"]) == 1

    # reject closes it
    r = client.post(f"/api/items/{lid}/reject")
    assert r.json()["status"] == ItemStatus.REJECTED
    # cannot approve a rejected item
    assert client.post(f"/api/items/{lid}/approve").status_code == 409


def test_no_publish_app_approves_locally():
    client, seed, Session = _make_client(None)
    lid = seed()
    r = client.post(f"/api/items/{lid}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == ItemStatus.PUBLISHED
