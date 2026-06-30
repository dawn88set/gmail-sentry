"""
Generic, integration-agnostic API for connecting and managing integrations.

Drives the Settings → Integrations UI for ANY catalog entry:
  GET    /api/integrations                      catalog + per-user status
  GET    /api/integrations/{id}                 one entry + status
  POST   /api/integrations/{id}/credentials     save BYO credentials
  POST   /api/integrations/{id}/oauth/auth-url   build the user's OAuth consent URL
  POST   /api/integrations/{id}/oauth/callback   exchange code -> tokens
  POST   /api/integrations/{id}/test            liveness check
  DELETE /api/integrations/{id}                 disconnect

All routes require a trusted, edge-verified user (backend.security.require_user).
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.security import require_user
from backend.integrations import catalog, oauth_state, store
from backend.integrations.crypto import CredentialEncryptionUnavailable

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _entry_or_404(integration_id: str) -> Dict[str, Any]:
    entry = catalog.get_integration(integration_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown integration '{integration_id}'")
    return entry


def _public_entry(entry: Dict[str, Any], db: Session, user_id: str) -> Dict[str, Any]:
    """Catalog metadata + connection status. Never includes secret values."""
    out: Dict[str, Any] = {
        "id": entry["id"],
        "name": entry["name"],
        "icon": entry.get("icon"),
        "authKind": entry["authKind"],
        "summary": entry.get("summary"),
        "capabilities": entry.get("capabilities", []),
        "credentialFields": entry.get("credentialFields", []),
        "setupGuide": entry.get("setupGuide", []),
        "status": store.get_status(db, user_id, entry["id"]),
    }
    ru = catalog.redirect_uri(entry)
    if ru:
        out["redirectUri"] = ru
    return out


@router.get("")
def list_all(user_id: str = Depends(require_user), db: Session = Depends(get_db)):
    return {
        "integrations": [
            _public_entry(e, db, user_id) for e in catalog.list_integrations()
        ]
    }


@router.get("/{integration_id}")
def get_one(
    integration_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _public_entry(_entry_or_404(integration_id), db, user_id)


class CredentialsBody(BaseModel):
    credentials: Dict[str, str]


@router.post("/{integration_id}/credentials")
def save_creds(
    integration_id: str,
    body: CredentialsBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    entry = _entry_or_404(integration_id)
    required = [f["key"] for f in entry.get("credentialFields", [])]
    missing = [k for k in required if not (body.credentials.get(k) or "").strip()]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing required fields: {', '.join(missing)}"
        )
    cleaned = {k: body.credentials[k].strip() for k in required if k in body.credentials}
    # apikey / basic are usable immediately; byo-oauth only stores the client creds
    # here and becomes "connected" after the OAuth round-trip.
    connected = entry["authKind"] in ("apikey", "basic", "webhook")
    try:
        store.save_credentials(
            db, user_id, integration_id, entry["authKind"], cleaned, connected=connected
        )
    except CredentialEncryptionUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return _public_entry(entry, db, user_id)


@router.post("/{integration_id}/oauth/auth-url")
def oauth_auth_url(
    integration_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    entry = _entry_or_404(integration_id)
    if entry["authKind"] != "byo-oauth":
        raise HTTPException(status_code=400, detail="This integration does not use OAuth.")
    creds = store.get_credentials(db, user_id, integration_id) or {}
    client_id = creds.get("client_id")
    if not client_id:
        raise HTTPException(
            status_code=400, detail="Save your Client ID and Client secret first."
        )
    ru = catalog.redirect_uri(entry)
    if not ru:
        raise HTTPException(status_code=500, detail="App origin (APP_URL) is not configured.")
    oauth = entry.get("oauth", {})
    params = {
        "client_id": client_id,
        "redirect_uri": ru,
        "response_type": "code",
        "scope": " ".join(entry.get("scopes", [])),
        "state": oauth_state.create_state(user_id, integration_id),
    }
    if oauth.get("accessType"):
        params["access_type"] = oauth["accessType"]
    if oauth.get("prompt"):
        params["prompt"] = oauth["prompt"]
    return {"authUrl": f"{oauth.get('authUrl')}?{urlencode(params)}", "redirectUri": ru}


class OAuthCallbackBody(BaseModel):
    code: str
    state: str


@router.post("/{integration_id}/oauth/callback")
def oauth_callback(
    integration_id: str,
    body: OAuthCallbackBody,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    entry = _entry_or_404(integration_id)
    if entry["authKind"] != "byo-oauth":
        raise HTTPException(status_code=400, detail="This integration does not use OAuth.")
    if not oauth_state.verify_state(body.state, user_id, integration_id):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    creds = store.get_credentials(db, user_id, integration_id) or {}
    client_id, client_secret = creds.get("client_id"), creds.get("client_secret")
    if not (client_id and client_secret):
        raise HTTPException(status_code=400, detail="Missing stored client credentials.")
    ru = catalog.redirect_uri(entry)
    oauth = entry.get("oauth", {})

    try:
        resp = httpx.post(
            oauth.get("tokenUrl"),
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": body.code,
                "redirect_uri": ru,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        resp.raise_for_status()
        tok = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {e}")

    updates: Dict[str, Any] = {"access_token": tok.get("access_token")}
    if tok.get("refresh_token"):
        updates["refresh_token"] = tok["refresh_token"]
    expires_at: Optional[datetime] = None
    if tok.get("expires_in"):
        expires_at = datetime.utcnow() + timedelta(seconds=int(tok["expires_in"]))

    # Best-effort: record the connected account for display.
    if oauth.get("userinfoUrl") and tok.get("access_token"):
        try:
            ui = httpx.get(
                oauth["userinfoUrl"],
                headers={"Authorization": f"Bearer {tok['access_token']}"},
                timeout=30,
            )
            if ui.status_code == 200:
                updates["account_email"] = ui.json().get("email")
        except httpx.HTTPError:
            pass

    store.merge_credentials(
        db,
        user_id,
        integration_id,
        updates,
        connected=True,
        scopes=entry.get("scopes"),
        expires_at=expires_at,
    )
    return _public_entry(entry, db, user_id)


@router.post("/{integration_id}/test")
def test_connection(
    integration_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    _entry_or_404(integration_id)
    status = store.get_status(db, user_id, integration_id)
    if not status.get("connected"):
        return {"ok": False, "detail": "Not connected."}

    # Per-provider liveness via the shared adapter registry (gmail, slack, …).
    # Returns None when no adapter ships a check; then "connected" is the best
    # signal we have.
    from backend.shared.adapters import run_liveness

    result = run_liveness(db, user_id, integration_id)
    if result is not None:
        return result
    return {"ok": True}


@router.delete("/{integration_id}")
def disconnect(
    integration_id: str,
    user_id: str = Depends(require_user),
    db: Session = Depends(get_db),
):
    _entry_or_404(integration_id)
    store.delete(db, user_id, integration_id)
    return {"ok": True}
