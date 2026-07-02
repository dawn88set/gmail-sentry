"""
Gmail Sentry's Gmail reads/writes — APP-OWNED and BROKER-ONLY.

Two rules this module exists to honor:

1. Don't add app-specific verbs to `backend/shared/adapters/gmail.py`. The
   Claritty build materializes a *canonical* copy of `backend/shared/` at deploy
   time, so anything extra there is dropped in production (symptom:
   `module 'backend.shared.adapters.gmail' has no attribute 'search'`). App verbs
   live here, in code the platform never rewrites.

2. Operate through the BROKER, not raw credentials. Every call goes through the
   platform executor via `execute_tool("gmail", <tool>, user_id, args)` — the
   platform holds the decrypted OAuth token and performs the Gmail API call
   server-side; the token never enters app code. We do NOT call
   `load_credentials` / touch the provider directly.

The broker's gmail tools live in the private platform
(`clarity-api/.../executors/gmail.executor.ts`): search, list_messages,
get_message, count, add_label, modify_labels, trash, send. If a new verb is
needed, add a broker tool there — never a creds fetch here.

Contract (from `execute_tool`): NOT_CONNECTED → IntegrationNotConnected (→ 409),
any other failure → IntegrationError (→ 5xx, retryable). Requires the platform
executor (`CLARITTY_PLATFORM_URL`); with no platform to broker to, calls raise
IntegrationNotConnected — there is no local direct-to-Gmail path by design.
"""
from typing import Any, Dict, List

from backend.shared.adapters import execute_tool

SERVICE = "gmail"


def search(db, user_id: str, query: str, max_results: int = 25) -> List[Dict[str, Any]]:
    """Message stubs ({id, threadId}) matching a Gmail query string."""
    res = execute_tool(SERVICE, "search", user_id, {"query": query, "limit": max_results})
    return res.get("messages") or []


def list_page(db, user_id: str, query: str, max_results: int = 20, page_token: str = "") -> Dict[str, Any]:
    """One page of {messages, nextPageToken} for a query (infinite scroll)."""
    res = execute_tool(
        SERVICE,
        "list_messages",
        user_id,
        {"query": query, "limit": max_results, "pageToken": page_token or ""},
    )
    return {
        "messages": res.get("messages") or [],
        "nextPageToken": res.get("nextPageToken") or "",
    }


def count(db, user_id: str, query: str) -> int:
    """Estimated count of messages matching a Gmail query (for category sizes)."""
    res = execute_tool(SERVICE, "count", user_id, {"query": query})
    return int(res.get("count") or 0)


def get_meta(db, user_id: str, message_id: str) -> Dict[str, Any]:
    """Parsed metadata for one message: sender, subject, snippet, Message-ID
    header, thread id, and label ids. (Parsing happens in the broker.)"""
    res = execute_tool(SERVICE, "get_message", user_id, {"message_id": message_id})
    return {
        "id": res.get("id") or message_id,
        "thread_id": res.get("thread_id") or "",
        "snippet": res.get("snippet") or "",
        "label_ids": res.get("label_ids") or [],
        "sender": res.get("sender") or "",
        "subject": res.get("subject") or "",
        "rfc822_msgid": (res.get("rfc822_msgid") or "").strip("<>"),
    }


def apply_label(db, user_id: str, message_id: str, label_name: str, *, archive: bool = False) -> bool:
    """Add a (user) label to a message, creating it if needed. When archive=True,
    also remove it from the inbox. The broker resolves label names → ids."""
    args: Dict[str, Any] = {"message_id": message_id, "add": [label_name]}
    if archive:
        args["remove"] = ["INBOX"]
    execute_tool(SERVICE, "modify_labels", user_id, args)
    return True


def archive(db, user_id: str, message_id: str) -> bool:
    """Remove a message from the inbox (Gmail's 'archive')."""
    execute_tool(SERVICE, "modify_labels", user_id, {"message_id": message_id, "remove": ["INBOX"]})
    return True


def trash(db, user_id: str, message_id: str) -> bool:
    """Move a message to Trash."""
    execute_tool(SERVICE, "trash", user_id, {"message_id": message_id})
    return True


def batch_modify(db, user_id: str, ids, add=None, remove=None) -> int:
    """Add/remove labels across up to 1000 messages in ONE broker call (bulk
    cleanup). Bulk-trash = add ['TRASH'] + remove ['INBOX']; archive = remove
    ['INBOX']. Returns how many messages were modified."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return 0
    args = {"ids": ids}
    if add:
        args["add"] = add
    if remove:
        args["remove"] = remove
    res = execute_tool(SERVICE, "batch_modify", user_id, args)
    return int(res.get("modified") or 0)
