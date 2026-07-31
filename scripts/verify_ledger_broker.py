#!/usr/bin/env python3
"""
Verify the broker assumptions the thread ledger rests on.

The ledger is designed against a broker surface that the public catalog manifest
only partly pins down. Three of its assumptions are load-bearing, and one is a
known-degraded path. This script checks all four against a REAL connected Gmail
account, so they're facts rather than hopes.

Run it once Gmail is connected for the user, with the platform env set:

    CLARITTY_PLATFORM_URL=... CLARITTY_AUTH_TOKEN=... \\
    DATABASE_URL=... python3 scripts/verify_ledger_broker.py [user_id]

Nothing here writes to the mailbox — it is read-only.

What it checks
--------------
1. **`after:`/`before:` with epoch seconds.** The whole time model. If this
   fails, set SENTRY_LEDGER_EPOCH_QUERIES=0 to switch the query builder to
   relative `newer_than:`/`older_than:` hour windows — coarser, but only that
   one function changes.
2. **`threadId` on search stubs.** Ball position, phone-reply detection and
   thread grouping all die without it.
3. **Pagination on `list_messages` with a query.** A window that silently
   truncated would leave a permanent hole in the ledger.
4. **`get_body`.** Expected to return only the snippet: the broker's
   `gmail.get_message` declares no body field. That doesn't break the ledger,
   but it does mean voice learning trains on ~100-character fragments, which is
   why learning from the user's approved sends matters more than from sent mail.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal  # noqa: E402
from backend.integrations import gmail_ops as gmail  # noqa: E402
from backend.shared.adapters import IntegrationNotConnected, IntegrationError  # noqa: E402

OK = "\033[32m✓\033[0m"
BAD = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"

results: list[tuple[bool, str]] = []


def record(ok: bool, blocking: bool, msg: str) -> None:
    mark = OK if ok else (BAD if blocking else WARN)
    print(f"  {mark} {msg}")
    if blocking:
        results.append((ok, msg))


def _epoch(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def main() -> int:
    user_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("VERIFY_USER_ID", "dev-user")
    db = SessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"\nverifying broker assumptions for user={user_id}\n")

    # -- 0. connected at all? ------------------------------------------------
    print("0. Gmail reachable")
    try:
        total = gmail.count(db, user_id, "in:inbox")
        record(True, True, f"in:inbox reachable ({total} messages estimated)")
    except IntegrationNotConnected:
        print(f"  {BAD} Gmail is not connected for {user_id} — connect it and re-run.")
        return 2
    except IntegrationError as e:
        print(f"  {BAD} broker error: {e}")
        return 2

    # -- 1. epoch after:/before: --------------------------------------------
    print("\n1. epoch after:/before: windows  [BLOCKING — the ledger's time model]")
    try:
        relative = gmail.count(db, user_id, "in:inbox newer_than:1d")
        epoch = gmail.count(db, user_id, f"in:inbox after:{_epoch(now - timedelta(days=1))}")
        close = abs(relative - epoch) <= max(3, int(0.15 * max(relative, 1)))
        record(
            close, True,
            f"newer_than:1d={relative} vs after:<epoch>={epoch} "
            f"({'agree' if close else 'DISAGREE — use SENTRY_LEDGER_EPOCH_QUERIES=0'})",
        )
        # A `before:` in the far past must return ~nothing; if the broker were
        # dropping the operator entirely we'd get the whole mailbox back.
        old = gmail.count(db, user_id, f"in:inbox before:{_epoch(now - timedelta(days=3650))}")
        record(old < max(5, total // 10), True,
               f"before:<10y ago> returns {old} (operator is honored, not ignored)")
    except Exception as e:  # noqa: BLE001
        record(False, True, f"epoch window probe failed: {type(e).__name__}: {e}")

    # -- 2. threadId on stubs -----------------------------------------------
    print("\n2. threadId on search stubs  [BLOCKING — thread state]")
    for box in ("in:inbox", "in:sent"):
        try:
            stubs = gmail.search(db, user_id, box, max_results=3)
            if not stubs:
                record(True, False, f"{box}: no messages to sample (inconclusive)")
                continue
            keys = set(stubs[0].keys())
            has = any(k in keys for k in ("threadId", "thread_id"))
            record(has, True, f"{box}: stub keys {sorted(keys)}")
        except Exception as e:  # noqa: BLE001
            record(False, True, f"{box}: {type(e).__name__}: {e}")

    # -- 3. pagination -------------------------------------------------------
    print("\n3. list_messages pagination with a query  [BLOCKING — no silent truncation]")
    try:
        page = gmail.list_page(db, user_id, "in:inbox", max_results=2)
        got = len(page.get("messages") or [])
        token = page.get("nextPageToken") or ""
        if total > 5:
            record(bool(token), True, f"page of {got}, nextPageToken={'present' if token else 'MISSING'}")
            if token:
                page2 = gmail.list_page(db, user_id, "in:inbox", max_results=2, page_token=token)
                ids1 = {m.get("id") for m in page["messages"]}
                ids2 = {m.get("id") for m in page2.get("messages") or []}
                record(bool(ids2) and not (ids1 & ids2), True,
                       "second page returns different messages")
        else:
            record(True, False, f"only {total} messages — pagination inconclusive")
    except Exception as e:  # noqa: BLE001
        record(False, True, f"pagination probe failed: {type(e).__name__}: {e}")

    # -- 4. get_body (expected to be snippet-only) ---------------------------
    print("\n4. get_body returns a real body?  [NOT blocking — affects voice quality]")
    try:
        sent = gmail.search(db, user_id, "in:sent", max_results=3)
        verdicts = []
        for stub in sent:
            mid = stub.get("id")
            if not mid:
                continue
            body = gmail.get_body(db, user_id, mid) or ""
            snip = (gmail.get_meta(db, user_id, mid) or {}).get("snippet") or ""
            verdicts.append(len(body) > len(snip) + 20)
        if not verdicts:
            record(True, False, "no sent mail to sample")
        elif any(verdicts):
            record(True, False, "full bodies ARE available — voice learning can use sent mail")
        else:
            record(False, False,
                   "snippet-only, as expected. Voice learning is training on ~100-char "
                   "fragments; prefer learning from the user's approved sends.")
    except Exception as e:  # noqa: BLE001
        record(False, False, f"body probe failed: {type(e).__name__}: {e}")

    # -- 5. label enumeration (needed by smart filing, B4) -------------------
    print("\n5. can we enumerate existing labels?  [NOT blocking — shapes B4 filing]")
    try:
        meta = gmail.get_meta(db, user_id, (gmail.search(db, user_id, "in:inbox", 1) or [{}])[0].get("id", ""))
        labels = meta.get("label_ids") or []
        user_labels = [l for l in labels if not str(l).isupper()]
        record(bool(user_labels), False,
               f"label_ids sample={labels[:6]} — these are IDs, not names"
               f"{'; a name lookup would still be needed' if not user_labels else ''}")
    except Exception as e:  # noqa: BLE001
        record(False, False, f"label probe skipped: {type(e).__name__}: {e}")

    db.close()

    failed = [m for ok, m in results if not ok]
    print()
    if failed:
        print(f"{BAD} {len(failed)} BLOCKING assumption(s) failed:")
        for m in failed:
            print(f"    - {m}")
        print("\n  See the module docstring for the fallback on each.")
        return 1
    print(f"{OK} all blocking assumptions hold — the ledger's design is sound against this broker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
