"""
Gmail adapter — the reference, fully-real provider wrapper.

Wraps backend.integrations.gmail_client.GmailClient with the 3-4 verbs apps
actually use, and translates its outcomes into the shared signals the HITL
route factory understands:
  - no usable credential        -> IntegrationNotConnected (→ 409)
  - a real API/HTTP failure     -> IntegrationError (→ 5xx, retryable)

Every call persists any refreshed access token (the client refreshes on 401),
so tokens stay alive across requests.

Usage from a publish callable:
    from backend.shared.adapters import gmail
    def _send(db, user_id, item):
        return gmail.send(db, user_id, to=item.payload["to"],
                          subject=item.title, body=item.body,
                          thread_id=item.payload.get("thread_id"))
    # returns {"external_id": "<gmail message id>", "account": "<from email>"}
"""
from typing import Any, Dict, List, Optional

import httpx

from backend.integrations.gmail_client import GmailClient, GmailNotConnected
from backend.shared.adapters import (
    IntegrationNotConnected,
    IntegrationError,
    load_credentials,
    persist_refreshed,
    execute_tool,
    _use_executor,
)

SERVICE = "gmail"


def _client(db, user_id: str) -> GmailClient:
    creds = load_credentials(db, user_id, SERVICE)  # raises IntegrationNotConnected
    try:
        return GmailClient(creds)
    except GmailNotConnected as e:
        raise IntegrationNotConnected(SERVICE, str(e))


def _save(db, user_id: str, client: GmailClient) -> None:
    persist_refreshed(db, user_id, SERVICE, {
        "access_token": client.credentials.get("access_token"),
        "token_expiry": client.credentials.get("token_expiry"),
    })


def list_unread(db, user_id: str, max_results: int = 25) -> List[Dict[str, Any]]:
    """Message stubs ({id, threadId}) for unread inbox mail."""
    client = _client(db, user_id)
    try:
        msgs = client.list_messages(query="is:unread in:inbox", max_results=max_results)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"list_unread failed: {e}")
    _save(db, user_id, client)
    return msgs


def get_message(db, user_id: str, message_id: str, fmt: str = "full") -> Dict[str, Any]:
    client = _client(db, user_id)
    try:
        msg = client.get_message(message_id, fmt=fmt)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"get_message failed: {e}")
    _save(db, user_id, client)
    return msg


def send(
    db,
    user_id: str,
    *,
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an email; returns {"external_id": <message id>, "account": <from>}.

    Raises IntegrationNotConnected if Gmail isn't connected, IntegrationError on
    a real send failure — never returns a fake success.
    """
    if not to:
        raise IntegrationError(SERVICE, "recipient (to) is required")

    # Managed/platform path: delegate to the platform executor — it holds the
    # token and performs the send server-side; the app never sees the credential.
    if _use_executor():
        res = execute_tool(
            SERVICE,
            "send",
            user_id,
            {
                "to": to,
                "subject": subject,
                "body": body,
                "threadId": thread_id,
                "inReplyTo": in_reply_to,
            },
        )
        msg_id = res.get("message_id") or res.get("id")
        if not msg_id:
            raise IntegrationError(SERVICE, "Gmail executor returned no message id")
        return {"external_id": msg_id, "account": res.get("account")}

    # Self-host path: call Gmail directly with the locally-stored credential.
    client = _client(db, user_id)
    try:
        resp = client.send(to, subject, body, thread_id=thread_id, in_reply_to=in_reply_to)
        account = client.profile_email()
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"send failed: {e}")
    _save(db, user_id, client)
    msg_id = resp.get("id")
    if not msg_id:
        raise IntegrationError(SERVICE, "Gmail send returned no message id")
    return {"external_id": msg_id, "account": account}


def test_connection(db, user_id: str) -> Dict[str, Any]:
    """Per-provider liveness check (used by /api/integrations/{id}/test)."""
    try:
        client = _client(db, user_id)
        email = client.profile_email()
    except IntegrationNotConnected as e:
        return {"ok": False, "detail": str(e)}
    except Exception as e:  # noqa: BLE001 — surface a friendly message
        return {"ok": False, "detail": str(e)}
    _save(db, user_id, client)
    return {"ok": True, "account": email}
