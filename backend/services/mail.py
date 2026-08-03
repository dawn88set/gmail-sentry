"""
Reading and writing mail — the client half of the app.

The watchdog half decides what matters and hands you a short list. This is the
other half: when a row isn't enough and you need to actually read the thread,
reply in context, or write to someone the app never flagged.

Two things shape the implementation, both consequences of the broker's surface:

**There is no `get_thread` verb.** `list_messages` returns `{id, threadId}` stubs
and nothing else, so a list costs one `get_message` per row. That's the same
price `category_messages` has always paid; it is why pages are small and why the
ledger is preferred wherever it already knows the answer.

**Thread membership comes from the ledger, not from Gmail.** `ThreadMessage`
already indexes every message the app has observed, keyed by thread — so opening
a conversation costs zero extra broker calls to *find* the messages, and only
pays to fetch the bodies. A thread older than the ledger horizon degrades to the
one message we were given rather than silently showing a partial conversation as
if it were whole.

Sending goes through the same honest path as every other outbound action: a real
message id or an exception. Nothing here marks anything sent on optimism.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend import models
from backend.integrations import gmail_ops as gmail
from backend.services import activity
from backend.shared.adapters import IntegrationError

logger = logging.getLogger(__name__)

#: The mailboxes the UI offers. Kept as a closed set: a free-text Gmail query in
#: the URL is a footgun (`in:anywhere` over a big mailbox is slow and expensive),
#: and search gets its own explicit entry point.
BOXES = {
    "inbox": "in:inbox",
    "unread": "in:inbox is:unread",
    "sent": "in:sent",
    "starred": "is:starred",
    "archive": "-in:inbox -in:trash -in:spam",
}

PAGE = 20


def list_box(
    db: Session,
    user_id: str,
    *,
    box: str = "inbox",
    query: str = "",
    page_token: str = "",
) -> Dict[str, Any]:
    """One page of a mailbox, or of a search when `query` is given.

    Rows carry what a mail list needs to be scannable — who, what, a snippet,
    and whether it's unread — and the thread id so tapping opens a conversation
    rather than a message.
    """
    q = (query or "").strip() or BOXES.get(box, BOXES["inbox"])
    page = gmail.list_page(db, user_id, q, max_results=PAGE, page_token=page_token)

    rows: List[Dict[str, Any]] = []
    for stub in page.get("messages", []):
        mid = stub.get("id")
        if not mid:
            continue
        try:
            meta = gmail.get_meta(db, user_id, mid)
        except IntegrationError:
            # One unreadable message must not blank the page.
            continue
        labels = meta.get("label_ids") or []
        rows.append({
            "id": mid,
            "thread_id": meta.get("thread_id") or stub.get("threadId") or "",
            "sender": meta.get("sender") or "",
            "subject": meta.get("subject") or "(no subject)",
            "snippet": meta.get("snippet") or "",
            "unread": "UNREAD" in labels,
            "starred": "STARRED" in labels,
            "rfc822_msgid": meta.get("rfc822_msgid") or "",
        })

    return {"messages": rows, "next_page_token": page.get("nextPageToken") or "", "query": q}


def read_thread(db: Session, user_id: str, thread_id: str, *, seed_id: str = "") -> Dict[str, Any]:
    """A whole conversation, oldest first, with bodies.

    Membership comes from the ledger, which already knows every message it has
    seen in this thread and in which direction it went. `partial` is returned
    honestly when the ledger only knows the one message we were handed — showing
    a fragment as though it were the full conversation is the kind of quiet lie
    that makes someone reply to the wrong thing.
    """
    known = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.thread_id == thread_id,
        )
        .order_by(models.ThreadMessage.ts_hi.asc())
        .all()
    )
    ids = [m.gmail_message_id for m in known if m.gmail_message_id]
    direction = {m.gmail_message_id: m.direction for m in known}
    if seed_id and seed_id not in ids:
        ids.append(seed_id)

    messages: List[Dict[str, Any]] = []
    for mid in ids[:25]:
        try:
            meta = gmail.get_meta(db, user_id, mid)
            body = gmail.get_body(db, user_id, mid)
        except IntegrationError as e:
            logger.info("thread %s: message %s unreadable (%s)", thread_id, mid, e)
            continue
        messages.append({
            "id": mid,
            "sender": meta.get("sender") or "",
            "subject": meta.get("subject") or "",
            "body": body or meta.get("snippet") or "",
            "outbound": direction.get(mid) == "out",
            "rfc822_msgid": meta.get("rfc822_msgid") or "",
        })

    subject = next((m["subject"] for m in messages if m["subject"]), "")
    return {
        "thread_id": thread_id,
        "subject": subject or "(no subject)",
        "messages": messages,
        # True when the ledger didn't know this conversation, so what's shown is
        # one message rather than the exchange.
        "partial": len(ids) <= 1 and bool(seed_id),
        "deep_link": f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else "",
    }


def send_mail(
    db: Session,
    user_id: str,
    *,
    to: str,
    subject: str,
    body: str,
    thread_id: str = "",
    in_reply_to: str = "",
) -> Dict[str, Any]:
    """Send. Raises rather than reporting a success it can't prove — the id in
    the result is a real Gmail message id or there was an exception."""
    result = gmail.send(
        db, user_id, to=to, subject=subject, body=body,
        thread_id=thread_id, in_reply_to=in_reply_to,
    )
    mid = (result or {}).get("message_id") or ""
    if not mid:
        raise IntegrationError("gmail", "Gmail didn't confirm the send.")

    activity.record(
        db, user_id, "reply_sent" if thread_id else "mail_sent",
        f"You emailed {activity.short_sender(to)}",
        detail=subject or "",
        subject_type="thread", subject_id=thread_id or "",
        counterparty_email=to, meta={"message_id": mid},
    )
    db.commit()
    return {"message_id": mid}
