"""
Accounts — the mailbox grouped the way a business is actually run.

Every other surface in this app is organised the way mail arrives: a message, a
thread, a person. None of those is how an owner thinks about their work. They
think "where does Northwind stand?" — and the answer is spread across four
people, six threads and two months of silence.

Nothing new is collected here. `Counterparty` already stores the domain, the CRM
company, the inferred relationship, reply rates and last-seen; `FollowUp` already
knows which loops are open and which have gone cold. This module only groups what
exists and ranks it by what should worry someone first.

The honesty rule that governs the rest of the app governs this too: every field
below is a counted row or a real timestamp. No deal values, no pipeline, no
"revenue at risk" — this app cannot see money, and inventing a number the user can
disprove would make the true ones worthless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend import models
from backend.services import counterparty as cp_service
# The naming rule lives on counterparty because it is a property of one, and
# because `worklist` needs it too — importing accounts there would be a cycle,
# since accounts is built FROM the worklist.
from backend.services.counterparty import GENERIC_DOMAINS, _clean, company_of
from backend.services import followups as followups_service
from backend.services import worklist as worklist_service

# Strongest wins when one account holds several relationships: a company with a
# client contact and a prospect contact is a client. Most→least committed.
_REL_RANK = [
    cp_service.CUSTOMER,
    "client",
    cp_service.PROSPECT,
    cp_service.VENDOR,
    cp_service.INTERNAL,
    cp_service.UNKNOWN,
]

#: How a relationship is said on screen. Matches the People screen's wording so
#: a contact is never a "Client" there and a "customer" here.
REL_LABEL = {
    "customer": "Client",
    "client": "Client",
    "prospect": "Prospect",
    "vendor": "Supplier",
    "internal": "Colleague",
    "bulk": "Automated",
    "unknown": "Unclassified",
}


def account_key(cp: models.Counterparty) -> str:
    """Stable identifier for the account a counterparty belongs to.

    URL-safe and derived only from stored fields, so it survives a recompute —
    an account whose key changed on every scan could not be linked to or
    bookmarked.
    """
    if (cp.crm_status or "") == "ok" and _clean(cp.crm_company or ""):
        return "crm:" + _clean(cp.crm_company).lower()
    domain = (cp.domain or "").lower()
    if domain and domain not in GENERIC_DOMAINS:
        return "d:" + domain
    return "p:" + (cp.email or "").lower()


@dataclass
class Account:
    key: str
    name: str
    relationship: str
    people: List[models.Counterparty] = field(default_factory=list)
    #: Everything on this account that needs the user — the same rows the Today
    #: worklist shows, grouped. `needs_you` must always equal
    #: `you_owe + chasing`, and the sum across accounts must equal the
    #: worklist's own total; a company card saying 3 above a list of 5 teaches
    #: people to trust neither.
    needs_you: int = 0
    you_owe: int = 0
    chasing: int = 0
    open_threads: int = 0
    #: The single most pressing thing on this account, in the user's own words —
    #: "PO 4471 needs your signature", not "you owe 1". A count tells an owner an
    #: account needs work; the ask tells them whether it needs work NOW, which is
    #: the decision they are actually making while scanning the list.
    headline: str = ""
    last_contact_at: Optional[datetime] = None
    silent_days: Optional[int] = None
    your_median_reply_h: Optional[int] = None
    importance: int = 0


def _rel_of(members: List[models.Counterparty]) -> str:
    present = {(m.relationship or "unknown") for m in members}
    for rel in _REL_RANK:
        if rel in present:
            return rel
    return "unknown"


def _member_rows(db: Session, user_id: str) -> List[models.Counterparty]:
    """Counterparties worth showing as business relationships.

    Colleagues and bulk senders are excluded: an account list led by newsletters
    and your own teammates buries the customers it exists to surface.
    """
    return (
        db.query(models.Counterparty)
        .filter(
            models.Counterparty.user_id == user_id,
            models.Counterparty.muted.is_(False),
            models.Counterparty.is_internal.is_(False),
            models.Counterparty.relationship != cp_service.BULK,
        )
        .all()
    )


def _risk(a: Account) -> tuple:
    """Ranking key. Going-quiet first, then what you owe, then importance.

    Deliberately not alphabetical: a list sorted by name makes the user do the
    triage the app is supposed to have already done.
    """
    return (
        -a.chasing,
        -a.you_owe,
        -(a.silent_days or 0) if a.chasing else 0,
        -a.importance,
        -a.open_threads,
    )


def build(db: Session, user_id: str, *, now: Optional[datetime] = None) -> List[Account]:
    """Group this user's counterparties into ranked accounts."""
    now = now or datetime.utcnow()
    members = _member_rows(db, user_id)
    if not members:
        return []

    by_key: Dict[str, Account] = {}
    for cp in members:
        key = account_key(cp)
        acc = by_key.get(key)
        if acc is None:
            acc = Account(key=key, name=company_of(cp), relationship="unknown")
            by_key[key] = acc
        acc.people.append(cp)

    # Bucket by member email in one pass rather than a query per account — an
    # owner with 200 contacts should not cost 200 round trips.
    emails: Dict[str, str] = {}
    for acc in by_key.values():
        for cp in acc.people:
            if cp.email:
                emails[cp.email.lower()] = acc.key

    # The SAME rows Today shows, grouped. Deriving "you owe 2" independently
    # from FollowUp would drift from the worklist the moment either changed —
    # and the Alert/FollowUp boundary means a naive follow-up query silently
    # omits threads that are currently live alerts. A high limit because this is
    # a rollup, not a page: truncation here would undercount an account.
    work = worklist_service.build(db, user_id, limit=1000)
    for item in work.get("items", []):
        key = emails.get((item.get("email") or "").lower())
        if not key:
            continue
        acc = by_key[key]
        acc.needs_you += 1
        # Items arrive already ranked, so the first one seen for an account is
        # its most pressing — no second sort, and it is the same row the user
        # would find at the top of Today.
        if not acc.headline:
            acc.headline = (item.get("headline") or "").strip()
        if item.get("kind") == worklist_service.CHASE:
            acc.chasing += 1
        else:
            acc.you_owe += 1

    # Open threads is context, not a call to action, so it stays sourced from
    # the loops themselves. `state="open"` already includes going_cold — asking
    # for "cold" as well would count those threads twice.
    for fu in followups_service.list_followups(db, user_id, state="open", limit=1000):
        key = emails.get((fu.counterparty_email or "").lower())
        if key:
            by_key[key].open_threads += 1

    for acc in by_key.values():
        acc.relationship = _rel_of(acc.people)
        acc.importance = max((int(c.importance or 0) for c in acc.people), default=0)
        seen = [c.last_seen_at for c in acc.people if c.last_seen_at]
        acc.last_contact_at = max(seen) if seen else None
        if acc.last_contact_at:
            acc.silent_days = max(0, int((now - acc.last_contact_at).total_seconds() // 86400))
        medians = [int(c.your_median_reply_h) for c in acc.people if c.your_median_reply_h]
        acc.your_median_reply_h = min(medians) if medians else None

    return sorted(by_key.values(), key=_risk)


def _person_dict(cp: models.Counterparty) -> Dict[str, Any]:
    return {
        "email": cp.email,
        "display_name": cp.display_name or "",
        "relationship": cp.relationship or "unknown",
        "relationship_label": REL_LABEL.get(cp.relationship or "", "Unclassified"),
        "your_reply_rate": int(cp.your_reply_rate or 0),
        "thread_count": int(cp.thread_count or 0),
        "last_seen_at": cp.last_seen_at.isoformat() if cp.last_seen_at else None,
    }


def to_dict(a: Account) -> Dict[str, Any]:
    return {
        "key": a.key,
        "name": a.name,
        "relationship": a.relationship,
        "relationship_label": REL_LABEL.get(a.relationship, "Unclassified"),
        "people_count": len(a.people),
        "open_threads": a.open_threads,
        "headline": a.headline,
        "needs_you": a.needs_you,
        "you_owe": a.you_owe,
        "chasing": a.chasing,
        "at_risk": a.chasing > 0,
        "silent_days": a.silent_days,
        "last_contact_at": a.last_contact_at.isoformat() if a.last_contact_at else None,
        "your_median_reply_h": a.your_median_reply_h,
        "importance": a.importance,
    }


def list_accounts(db: Session, user_id: str, *, limit: int = 100) -> Dict[str, Any]:
    accounts = build(db, user_id)
    return {
        "accounts": [to_dict(a) for a in accounts[: max(1, limit)]],
        "total": len(accounts),
        "at_risk": sum(1 for a in accounts if a.chasing > 0),
        "needs_you": sum(a.needs_you for a in accounts),
        "you_owe": sum(a.you_owe for a in accounts),
    }


def get_account(db: Session, user_id: str, key: str) -> Optional[Dict[str, Any]]:
    """One account with its people and open threads, or None if the key is gone.

    Returning None rather than an empty account matters: a key can disappear
    when a CRM lookup lands and a domain-keyed account becomes a CRM-keyed one,
    and a bookmarked link should 404 honestly instead of showing a blank company.
    """
    for a in build(db, user_id):
        if a.key != key:
            continue
        emails = {(c.email or "").lower() for c in a.people}
        threads = [
            {
                "id": f.id,
                "thread_id": f.thread_id,
                "subject": f.subject or "(no subject)",
                "who": f.counterparty_name or f.counterparty_email or "someone",
                "email": f.counterparty_email or "",
                "ball": getattr(f, "ball", "") or "",
                "state": getattr(f, "state", "") or "",
                "risk": int(getattr(f, "risk", 0) or 0),
                "last_activity_at": (
                    f.last_activity_at.isoformat() if getattr(f, "last_activity_at", None) else None
                ),
            }
            for f in followups_service.list_followups(db, user_id, state="all", limit=200)
            if (f.counterparty_email or "").lower() in emails
        ]
        return {
            **to_dict(a),
            "people": [_person_dict(c) for c in sorted(
                a.people, key=lambda c: (-(int(c.importance or 0)), c.email or "")
            )],
            "threads": threads,
        }
    return None
