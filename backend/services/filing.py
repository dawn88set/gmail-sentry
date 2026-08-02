"""
Smart filing — put whole conversations where they belong.

`LabelRule` files individual INBOUND messages against rules the user wrote by
hand. Useful, but it leaves two gaps: the user's own replies stay orphaned in
Sent, so a conversation is split across two places; and nothing organises itself
without the user first predicting what to write a rule for.

This files by **who the thread is with**, using the counterparty ranking, and
labels **every message in the conversation** — inbound, the replies sent through
this app, and the ones sent from a phone that only the ledger knows about.

## Naming

The relationship class becomes the parent, the company or person the child:

    Clients/Northwind          Prospects/Meridian Supply
    Internal/Priya Shah        Vendors/Acme Hosting

Deterministic, so it costs nothing. A thread that clearly belongs to an existing
topical folder the user already uses (Invoices, Legal…) goes there instead —
keyword match first, so the common case is still free.

## Two gates that matter more than the feature

**Approval before creation.** A folder is `proposed` until the user says yes.
Nothing is ever labelled with an unapproved folder. Creating labels
automatically in someone's real mailbox is hard to undo and is exactly the kind
of surprise that gets an app uninstalled.

**Forward-only from activation.** `filing_started_at` is stamped when the user
switches filing on, and threads whose last activity predates it are never
auto-filed. The ledger backfills ~45 days of history; without this the first
sweep would relabel thousands of old threads at once. Organising the backlog is
offered as an explicit, previewable action instead.

## What it never does

It never removes `INBOX`. Labelling is not hiding — a thread that's been filed
is still in the inbox until the user archives it, or until one of their own
`LabelRule`s says otherwise. And an explicit LabelRule always wins: someone who
already configured filing gets no surprises from this layer.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models
from backend.integrations import gmail_ops as gmail_adapter
from backend.services import activity
from backend.services import counterparty as cp_service
from backend.services import ledger
from backend.shared.adapters import IntegrationNotConnected, IntegrationError

logger = logging.getLogger(__name__)

#: Relationship class → the parent folder it files under. `unknown` is
#: deliberately absent: we don't invent a home for someone we can't classify,
#: because a wrong folder is worse than no folder.
PARENT_FOR = {
    cp_service.CUSTOMER: "Clients",
    cp_service.PROSPECT: "Prospects",
    cp_service.INTERNAL: "Internal",
    cp_service.VENDOR: "Vendors",
}

#: Topical folders we'll match a thread into when the subject is unambiguous.
#: Keyword-first so the common case never costs a model call.
TOPIC_HINTS: List[Tuple[str, tuple]] = [
    ("Invoices", ("invoice", "receipt", "billing", "payment due", "statement")),
    ("Legal", ("nda", "contract", "agreement", "terms of service", "dpa", "msa")),
    ("Hiring", ("resume", "cv", "candidate", "interview", "application for")),
    ("Scheduling", ("calendar invite", "reschedule", "availability", "meeting request")),
]

#: How many folders may be proposed per sweep. A user who wakes up to sixty
#: pending folders will reject the feature, not review them.
MAX_PROPOSALS_PER_SWEEP = 5

#: Gmail nests labels with "/". Strip it (and control chars) from a derived
#: segment so "Acme / Co" can't silently create a nested folder.
_UNSAFE = re.compile(r"[/\\\n\r\t]+")


def _segment(text: str) -> str:
    """One safe path segment for a folder name."""
    cleaned = _UNSAFE.sub(" ", (text or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:60]


def _company_of(cp: models.Counterparty) -> str:
    """The best available name for a counterparty's organisation.

    CRM company name if we have one, else a readable form of their domain, else
    their display name. Personal-mail domains fall back to the person, since
    "Clients/Gmail.Com" would be worse than useless.
    """
    if (cp.crm_status or "") == "ok" and (cp.crm_company or "").strip():
        return _segment(cp.crm_company)

    domain = (cp.domain or "").lower()
    generic = {
        "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
        "yahoo.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "aol.com",
    }
    if domain and domain not in generic:
        root = domain.split(".")[0]
        return _segment(root.replace("-", " ").title())

    if (cp.display_name or "").strip():
        return _segment(cp.display_name)
    return _segment((cp.email or "").split("@")[0].replace(".", " ").title())


def topical_folder_for(subject: str, known: Optional[Dict[str, models.MailFolder]] = None) -> str:
    """An existing/obvious topical folder for this subject, or "".

    Prefers a folder the user already uses — matching their structure beats
    inventing a parallel one beside it.
    """
    text = (subject or "").lower()
    if not text:
        return ""

    if known:
        for name, folder in known.items():
            if folder.kind != "topical":
                continue
            leaf = name.split("/")[-1].lower()
            if len(leaf) >= 4 and leaf in text:
                return name

    for name, hints in TOPIC_HINTS:
        if any(h in text for h in hints):
            return name
    return ""


def folder_for_thread(
    cp: Optional[models.Counterparty],
    subject: str,
    known: Optional[Dict[str, models.MailFolder]] = None,
) -> Tuple[str, str, int]:
    """(folder_name, kind, confidence) for a thread. ("", "", 0) to skip.

    Counterparty-first: who a conversation is with is a far more stable fact
    than what a single subject line says.
    """
    if cp is not None and not cp_service.is_bulk_sender(cp.email or ""):
        parent = PARENT_FOR.get(cp.relationship or "")
        if parent:
            company = _company_of(cp)
            if company:
                # A stated relationship is a fact; an inferred one is a guess.
                confidence = 90 if (cp.relationship_source or "") in ("user", "crm") else 70
                return f"{parent}/{company}", "counterparty", confidence

    topical = topical_folder_for(subject, known)
    if topical:
        return topical, "topical", 60

    # Unknown relationship and no obvious topic — decline. A wrong folder is
    # worse than none, because the user then can't find the mail.
    return "", "", 0


def _known_folders(db: Session, user_id: str) -> Dict[str, models.MailFolder]:
    return {
        f.name: f
        for f in db.query(models.MailFolder)
        .filter(models.MailFolder.user_id == user_id)
        .all()
    }


def propose_folder(
    db: Session,
    user_id: str,
    name: str,
    *,
    kind: str = "counterparty",
    source: str = "derived",
    counterparty_email: str = "",
) -> Optional[models.MailFolder]:
    """Register a folder as awaiting approval. Returns None if it's rejected.

    Idempotent — proposing an existing folder just returns it, so repeated
    sweeps don't pile up duplicates.
    """
    existing = (
        db.query(models.MailFolder)
        .filter(models.MailFolder.user_id == user_id, models.MailFolder.name == name)
        .first()
    )
    if existing is not None:
        # "Rejected" means the user said no. Never offer it again.
        return None if existing.status == "rejected" else existing

    folder = models.MailFolder(
        user_id=user_id, name=name, kind=kind, source=source,
        counterparty_email=counterparty_email or "", status="proposed",
    )
    try:
        with db.begin_nested():
            db.add(folder)
            db.flush()
        return folder
    except IntegrityError:
        db.rollback()
        return (
            db.query(models.MailFolder)
            .filter(models.MailFolder.user_id == user_id, models.MailFolder.name == name)
            .first()
        )


def approve_folder(db: Session, folder: models.MailFolder) -> models.MailFolder:
    folder.status = "active"
    folder.approved_at = ledger.utcnow()
    activity.record(
        db, folder.user_id, "folder_approved",
        f"You approved the folder {folder.name}",
        detail="Conversations with this contact will be filed here from now on.",
        subject_type="folder", subject_id=folder.id, folder_name=folder.name,
        counterparty_email=folder.counterparty_email or "",
    )
    db.commit()
    return folder


def reject_folder(db: Session, folder: models.MailFolder) -> models.MailFolder:
    """Never propose this one again, and drop any threads waiting on it."""
    folder.status = "rejected"
    db.query(models.ThreadFolder).filter(
        models.ThreadFolder.user_id == folder.user_id,
        models.ThreadFolder.folder_name == folder.name,
        models.ThreadFolder.status == "pending",
    ).delete(synchronize_session=False)
    # Worth recording: a rejection is the user teaching the app something, and
    # without it the folder simply disappears with no evidence they were asked.
    activity.record(
        db, folder.user_id, "folder_rejected",
        f"You turned down the folder {folder.name}",
        detail="It won’t be suggested again.",
        subject_type="folder", subject_id=folder.id, folder_name=folder.name,
    )
    db.commit()
    return folder


def rename_folder(db: Session, folder: models.MailFolder, new_name: str) -> models.MailFolder:
    """Rename before approving. The user's wording wins over ours."""
    clean = "/".join(_segment(part) for part in (new_name or "").split("/") if _segment(part))
    if not clean:
        raise ValueError("Folder name can't be empty")
    old = folder.name
    folder.name = clean
    folder.source = "user"
    db.query(models.ThreadFolder).filter(
        models.ThreadFolder.user_id == folder.user_id,
        models.ThreadFolder.folder_name == old,
    ).update({"folder_name": clean}, synchronize_session=False)
    db.commit()
    return folder


def _label_rule_labels(db: Session, user_id: str) -> set:
    """Labels the user's own rules already manage — this layer stays out of
    their way, because someone who configured filing wants no surprises."""
    return {
        r.target_label
        for r in db.query(models.LabelRule)
        .filter(models.LabelRule.user_id == user_id, models.LabelRule.active.is_(True))
        .all()
        if r.target_label
    }


def apply_thread_folder(db: Session, user_id: str, tf: models.ThreadFolder) -> int:
    """Label every message in the thread. Returns how many were labelled.

    ONE broker call per thread: `batch_modify` over every message id the ledger
    holds for it, which is what gets the user's own sent replies filed alongside
    the inbound ones. `INBOX` is never removed — labelling is not hiding.
    """
    ids = [
        m.gmail_message_id
        for m in db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.thread_id == tf.thread_id,
        )
        .all()
        if m.gmail_message_id
    ]
    if not ids:
        return 0

    modified = gmail_adapter.batch_modify(db, user_id, ids, add=[tf.folder_name])
    tf.status = "filed"
    tf.filed_count = len(ids)
    tf.filed_at = ledger.utcnow()
    tf.error = ""
    return modified or len(ids)


def run_filing(db: Session, user_id: str, cfg: models.SentryConfig) -> Dict[str, object]:
    """File the threads that can be filed; propose folders for the rest.

    Returns a summary the scan turns into one notification line. Never raises
    for a filing problem — organising mail must not be able to fail a scan.
    """
    out: Dict[str, object] = {"filed": 0, "threads": 0, "proposed": [], "by_folder": {}}
    if not cfg.filing_enabled:
        return out

    started = cfg.filing_started_at
    if started is None:
        # Belt and braces: if the flag is on but the marker is missing, stamp it
        # now rather than treating all of history as fair game.
        cfg.filing_started_at = started = ledger.utcnow()
        db.commit()

    known = _known_folders(db, user_id)
    active = {name for name, f in known.items() if f.status == "active"}
    reserved = _label_rule_labels(db, user_id)
    counterparties = {
        c.email: c
        for c in db.query(models.Counterparty)
        .filter(models.Counterparty.user_id == user_id)
        .all()
    }

    already = {
        tf.thread_id: tf
        for tf in db.query(models.ThreadFolder)
        .filter(models.ThreadFolder.user_id == user_id)
        .all()
    }

    # Candidate threads: active since filing was switched on. Forward-only — the
    # backfilled history is not touched unless the user explicitly asks.
    rows = (
        db.query(models.ThreadMessage)
        .filter(
            models.ThreadMessage.user_id == user_id,
            models.ThreadMessage.ts_hi >= started,
        )
        .order_by(models.ThreadMessage.ts_hi.desc())
        .limit(2000)
        .all()
    )
    by_thread: Dict[str, List[models.ThreadMessage]] = {}
    for m in rows:
        by_thread.setdefault(m.thread_id, []).append(m)

    proposals_left = MAX_PROPOSALS_PER_SWEEP
    by_folder: Dict[str, int] = {}
    # Conversations, not messages. The notification counts labels applied, but
    # "6 conversations filed" is what a person recognises as work done — a
    # 12-message thread is one thing they no longer have to sort.
    threads_by_folder: Dict[str, int] = {}

    for thread_id, msgs in by_thread.items():
        tf = already.get(thread_id)

        if tf is None:
            inbound = [m for m in msgs if m.direction == "in" and m.counterparty_email]
            email = inbound[0].counterparty_email if inbound else ""
            subject = next((m.subject for m in msgs if m.subject), "")
            cp = counterparties.get(email or "")

            if cp is not None and cp.muted:
                continue
            if email and cp_service.is_bulk_sender(email):
                continue

            name, kind, confidence = folder_for_thread(cp, subject, known)
            if not name or name in reserved:
                continue  # nothing confident to say, or the user's own rule owns it

            folder = known.get(name)
            if folder is not None and folder.status == "rejected":
                # The user said no to this folder. Don't queue threads against
                # it either — otherwise rejected folders quietly accumulate
                # pending rows that would all file at once if it were ever
                # re-approved.
                continue
            if folder is None:
                if proposals_left <= 0:
                    continue
                folder = propose_folder(
                    db, user_id, name, kind=kind, source="derived", counterparty_email=email,
                )
                if folder is None:
                    continue  # previously rejected
                known[name] = folder
                proposals_left -= 1
                activity.record(
                    db, user_id, "folder_proposed",
                    f"Suggested a folder: {name}",
                    detail="Waiting for your OK — nothing is filed there until you approve it.",
                    subject_type="folder", subject_id=folder.id,
                    folder_name=name, counterparty_email=email or "",
                )

            tf = models.ThreadFolder(
                user_id=user_id, thread_id=thread_id, folder_name=name,
                confidence=confidence, status="pending",
            )
            db.add(tf)
            already[thread_id] = tf

        # Only file into folders the user has actually approved.
        if tf.folder_name not in active:
            continue
        # Already fully filed and no new messages since — nothing to do.
        if tf.status == "filed" and int(tf.filed_count or 0) >= len(msgs):
            continue

        try:
            n = apply_thread_folder(db, user_id, tf)
            if n:
                out["filed"] = int(out["filed"]) + n
                out["threads"] = int(out["threads"]) + 1
                by_folder[tf.folder_name] = by_folder.get(tf.folder_name, 0) + n
                threads_by_folder[tf.folder_name] = threads_by_folder.get(tf.folder_name, 0) + 1
        except IntegrationNotConnected:
            raise
        except IntegrationError as e:
            tf.status = "failed"
            tf.error = str(e)[:500]
            logger.info("filing failed for thread %s: %s", thread_id, e)
            # Previously this was invisible everywhere: the thread simply never
            # appeared in its folder and nothing said why.
            activity.record(
                db, user_id, "filing_failed",
                f"Couldn’t file a conversation into {tf.folder_name}",
                detail=str(e)[:500],
                subject_type="thread", subject_id=thread_id,
                folder_name=tf.folder_name,
            )

    # One event per folder per sweep, not one per thread. Filing runs every five
    # minutes; per-thread rows would turn the feed into the log it exists to
    # replace.
    for name, threads in threads_by_folder.items():
        activity.record(
            db, user_id, "thread_filed",
            f"Filed {threads} conversation{'s' if threads != 1 else ''} into {name}",
            detail=f"{by_folder.get(name, 0)} messages labelled, including your own replies.",
            subject_type="folder", subject_id=(known.get(name).id if known.get(name) else ""),
            folder_name=name, count=threads,
        )

    db.commit()

    pending = [
        f.name
        for f in db.query(models.MailFolder)
        .filter(models.MailFolder.user_id == user_id, models.MailFolder.status == "proposed")
        .order_by(models.MailFolder.created_at.desc())
        .limit(20)
        .all()
    ]
    out["proposed"] = pending
    out["by_folder"] = by_folder
    return out


def filing_summary_line(result: Dict[str, object]) -> str:
    """One line for the scan notification, or "" when nothing happened.

    Batched on purpose: filing runs every five minutes, so a ping per message
    would be unusable. This is quiet enough to ignore and specific enough to
    catch a wrong folder early.
    """
    filed = int(result.get("filed") or 0)
    by_folder: Dict[str, int] = result.get("by_folder") or {}  # type: ignore[assignment]
    proposed: List[str] = result.get("proposed") or []  # type: ignore[assignment]

    parts: List[str] = []
    if filed and by_folder:
        top = sorted(by_folder.items(), key=lambda kv: kv[1], reverse=True)[:3]
        detail = ", ".join(f"{n} → {name}" for name, n in top)
        more = len(by_folder) - len(top)
        if more > 0:
            detail += f", +{more} more"
        parts.append(f"📁 Filed {filed} — {detail}")
    if proposed:
        n = len(proposed)
        parts.append(f"{n} new folder{'s' if n != 1 else ''} waiting for approval")
    return "\n".join(parts)


def preview_backlog(db: Session, user_id: str, *, days: int = 30) -> List[Dict[str, object]]:
    """What organising the recent backlog WOULD do, without doing it.

    The backlog is the dangerous case — thousands of threads at once — so it's
    an explicit action with a preview rather than something that happens on its
    own the first time filing is switched on.
    """
    since = ledger.utcnow() - timedelta(days=days)
    known = _known_folders(db, user_id)
    reserved = _label_rule_labels(db, user_id)
    counterparties = {
        c.email: c
        for c in db.query(models.Counterparty)
        .filter(models.Counterparty.user_id == user_id)
        .all()
    }
    rows = (
        db.query(models.ThreadMessage)
        .filter(models.ThreadMessage.user_id == user_id, models.ThreadMessage.ts_hi >= since)
        .all()
    )
    by_thread: Dict[str, List[models.ThreadMessage]] = {}
    for m in rows:
        by_thread.setdefault(m.thread_id, []).append(m)

    tally: Dict[str, int] = {}
    for msgs in by_thread.values():
        inbound = [m for m in msgs if m.direction == "in" and m.counterparty_email]
        email = inbound[0].counterparty_email if inbound else ""
        cp = counterparties.get(email or "")
        if cp is not None and cp.muted:
            continue
        if email and cp_service.is_bulk_sender(email):
            continue
        subject = next((m.subject for m in msgs if m.subject), "")
        name, _kind, _conf = folder_for_thread(cp, subject, known)
        if not name or name in reserved:
            continue
        tally[name] = tally.get(name, 0) + 1

    return [
        {"folder": name, "threads": count, "exists": name in known}
        for name, count in sorted(tally.items(), key=lambda kv: kv[1], reverse=True)
    ]
