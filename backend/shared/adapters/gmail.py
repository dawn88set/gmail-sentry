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


# --- Gmail Sentry helpers ---------------------------------------------------
# Higher-level reads/writes used by the scan engine. All go through _client()
# (the self-host client path), which works locally (encrypted store / FAKE_CREDS)
# AND on-platform (creds resolved from platform KMS via load_credentials).


def search(db, user_id: str, query: str, max_results: int = 25) -> List[Dict[str, Any]]:
    """Message stubs ({id, threadId}) matching a Gmail query string."""
    client = _client(db, user_id)
    try:
        msgs = client.list_messages(query=query, max_results=max_results)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"search failed: {e}")
    _save(db, user_id, client)
    return msgs


def list_page(db, user_id: str, query: str, max_results: int = 20, page_token: str = "") -> Dict[str, Any]:
    """One page of {messages, nextPageToken} for a query (infinite scroll)."""
    client = _client(db, user_id)
    try:
        page = client.list_page(query=query, max_results=max_results, page_token=page_token)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"list_page failed: {e}")
    _save(db, user_id, client)
    return page


def count(db, user_id: str, query: str) -> int:
    """Estimated count of messages matching a Gmail query (for category sizes)."""
    client = _client(db, user_id)
    try:
        n = client.count_messages(query)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"count failed: {e}")
    _save(db, user_id, client)
    return n


def _header(headers: List[Dict[str, str]], name: str) -> str:
    low = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == low:
            return h.get("value") or ""
    return ""


def get_meta(db, user_id: str, message_id: str) -> Dict[str, Any]:
    """Parsed metadata for one message: sender, subject, snippet, Message-ID
    header, thread id, and label ids."""
    client = _client(db, user_id)
    try:
        msg = client.get_message(message_id, fmt="metadata")
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"get_meta failed: {e}")
    _save(db, user_id, client)
    headers = (msg.get("payload") or {}).get("headers") or []
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "snippet": msg.get("snippet") or "",
        "label_ids": msg.get("labelIds") or [],
        "sender": _header(headers, "From"),
        "subject": _header(headers, "Subject"),
        "rfc822_msgid": _header(headers, "Message-ID").strip("<>"),
    }


def apply_label(db, user_id: str, message_id: str, label_name: str, *, archive: bool = False) -> bool:
    """Add a (user) label to a message, creating the label if needed. When
    archive=True, also remove it from the inbox."""
    client = _client(db, user_id)
    try:
        label_id = client.ensure_label(label_name)
        remove = ["INBOX"] if archive else []
        client.modify_labels(message_id, add=[label_id], remove=remove)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"apply_label failed: {e}")
    _save(db, user_id, client)
    return True


def archive(db, user_id: str, message_id: str) -> bool:
    """Remove a message from the inbox (Gmail's 'archive')."""
    client = _client(db, user_id)
    try:
        client.modify_labels(message_id, remove=["INBOX"])
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"archive failed: {e}")
    _save(db, user_id, client)
    return True


def trash(db, user_id: str, message_id: str) -> bool:
    """Move a message to Trash."""
    client = _client(db, user_id)
    try:
        client.trash(message_id)
    except (httpx.HTTPError, GmailNotConnected) as e:
        raise IntegrationError(SERVICE, f"trash failed: {e}")
    _save(db, user_id, client)
    return True


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
