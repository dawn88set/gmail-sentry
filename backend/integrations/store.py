"""
Per-user integration credential storage (encrypted) on top of UserIntegration.

Credentials are encrypted before they touch the database and decrypted only in
memory when an app needs to call the provider. Status views never expose secrets.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend import models
from backend.integrations import crypto

logger = logging.getLogger(__name__)


def _row(db: Session, user_id: str, service: str):
    return (
        db.query(models.UserIntegration)
        .filter(
            models.UserIntegration.user_id == user_id,
            models.UserIntegration.service == service,
        )
        .first()
    )


def save_credentials(
    db: Session,
    user_id: str,
    service: str,
    auth_type: str,
    credentials: Dict[str, Any],
    *,
    scopes: Optional[List[str]] = None,
    connected: bool = False,
    expires_at: Optional[datetime] = None,
):
    """Encrypt + upsert the full credential set for (user, service)."""
    envelope = crypto.encrypt(credentials)
    row = _row(db, user_id, service)
    if row:
        row.credentials = envelope
        row.auth_type = auth_type
        if scopes is not None:
            row.scopes = scopes
        row.is_active = connected
        row.expires_at = expires_at
        row.connected_at = datetime.utcnow()
    else:
        row = models.UserIntegration(
            user_id=user_id,
            service=service,
            auth_type=auth_type,
            credentials=envelope,
            scopes=scopes,
            is_active=connected,
            expires_at=expires_at,
        )
        db.add(row)
    db.commit()
    return row


def merge_credentials(
    db: Session,
    user_id: str,
    service: str,
    updates: Dict[str, Any],
    *,
    connected: Optional[bool] = None,
    scopes: Optional[List[str]] = None,
    expires_at: Optional[datetime] = None,
):
    """Decrypt existing creds, merge in updates (e.g. OAuth tokens), re-encrypt."""
    row = _row(db, user_id, service)
    existing = crypto.decrypt(row.credentials) if row and row.credentials else {}
    existing.update({k: v for k, v in updates.items() if v is not None})
    return save_credentials(
        db,
        user_id,
        service,
        row.auth_type if row else "oauth",
        existing,
        scopes=scopes if scopes is not None else (row.scopes if row else None),
        connected=connected if connected is not None else (bool(row.is_active) if row else False),
        expires_at=expires_at if expires_at is not None else (row.expires_at if row else None),
    )


def get_credentials(db: Session, user_id: str, service: str) -> Optional[Dict[str, Any]]:
    row = _row(db, user_id, service)
    if not row or not row.credentials:
        return None
    return crypto.decrypt(row.credentials)


def get_status(db: Session, user_id: str, service: str) -> Dict[str, Any]:
    """
    Connection status WITHOUT secrets — safe to return to the client.

    Resilient by design: the integrations LIST is built from the static catalog
    and must always render (it tells the user what the app needs). A per-user
    status lookup that fails (e.g. the table isn't provisioned yet, a transient
    DB error, or an unreadable credential envelope) must degrade to
    "not connected" — never 500 the whole page.
    """
    try:
        row = _row(db, user_id, service)
    except SQLAlchemyError:
        # Leave the session usable for the next entry's lookup.
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("integration status lookup failed for %s", service, exc_info=True)
        return {"connected": False}
    if not row:
        return {"connected": False}
    try:
        creds = crypto.decrypt(row.credentials) if row.credentials else {}
    except Exception:  # noqa: BLE001 - a bad/undecryptable envelope must not 500 the list
        creds = {}
    return {
        "connected": bool(row.is_active),
        "connectedAt": row.connected_at.isoformat() if row.connected_at else None,
        "expiresAt": row.expires_at.isoformat() if row.expires_at else None,
        "scopes": row.scopes or [],
        # Non-secret display hint only.
        "account": creds.get("account_email") or creds.get("email_address"),
    }


def delete(db: Session, user_id: str, service: str) -> bool:
    row = _row(db, user_id, service)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
