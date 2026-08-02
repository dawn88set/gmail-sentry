"""activity_events — an append-only record of what Sentry actually did

Every other table in this schema holds *state*: a thread's status now, the
folder it ended up in, how many conversations a label holds. None of it can
answer "what did you do for me this week?", which is the one question a user
asks about software that works while they aren't looking. A scan performs a
dozen side effects every five minutes and, until this table, left no trace of
any of them anywhere in the UI.

Most of these transitions are also genuinely unrecoverable after the fact, which
is why they're recorded at the moment they happen rather than derived later:

  * `followups.closed_at` is NULLed when a loop reopens, so closures undercount
  * `thread_folders.filed_at` is overwritten when a thread is re-filed
  * going cold is computed inside `sync_followups` and thrown away
  * an alert closed because the user replied from their phone leaves no mark

The backfill below seeds the feed from the timestamps that *do* survive, so an
existing install doesn't open on an empty screen and imply nothing ever
happened. Backfilled rows are marked `meta.backfilled = true` — they're honest
about being reconstructed, and their wording avoids claiming a precision the
source column doesn't have.

FALSE/TRUE, never 0/1 — Postgres rejects integers for booleans (this broke 0007
in production while passing every SQLite test).

Revision ID: 0011_activity_events
Revises: 0010_thread_filing
Create Date: 2026-08-01
"""
import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_activity_events"
down_revision: Union[str, None] = "0010_thread_filing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AE = "activity_events"


def _index(table: str, name: str, cols, *, unique: bool = False) -> None:
    insp = sa.inspect(op.get_bind())
    if name in {ix["name"] for ix in insp.get_indexes(table)}:
        return
    op.create_index(name, table, cols, unique=unique)


def _backfill(bind, rows) -> None:
    """Insert reconstructed events. Skips silently if a source table is missing
    — a fresh database has nothing to reconstruct, and that is not an error."""
    if not rows:
        return
    bind.execute(
        sa.text(
            f"INSERT INTO {_AE} "
            "(id, user_id, at, kind, title, detail, subject_type, subject_id, "
            " counterparty_email, folder_name, count, meta) "
            "VALUES (:id, :user_id, :at, :kind, :title, :detail, :subject_type, "
            "        :subject_id, :counterparty_email, :folder_name, :count, :meta)"
        ),
        rows,
    )


def _row(**kw) -> dict:
    base = {
        "id": str(uuid.uuid4()),
        "detail": "",
        "subject_type": "",
        "subject_id": "",
        "counterparty_email": "",
        "folder_name": "",
        "count": 0,
        "meta": json.dumps({"backfilled": True}),
    }
    base.update(kw)
    return base


def _fetch(bind, tables, table, sql):
    if table not in tables:
        return []
    return bind.execute(sa.text(sql)).fetchall()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if _AE not in tables:
        op.create_table(
            _AE,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("at", sa.DateTime(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False, server_default=""),
            sa.Column("detail", sa.Text()),
            sa.Column("subject_type", sa.String()),
            sa.Column("subject_id", sa.String()),
            sa.Column("counterparty_email", sa.String()),
            sa.Column("folder_name", sa.String()),
            sa.Column("count", sa.Integer(), server_default="0"),
            sa.Column("meta", sa.JSON()),
        )

    # The feed's only real query: this user's events, newest first.
    _index(_AE, "ix_activity_user_at", ["user_id", "at"])
    _index(_AE, "ix_activity_user_kind", ["user_id", "kind"])
    _index(_AE, "ix_activity_subject", ["subject_id"])

    # ---- backfill from the timestamps that survived -----------------------
    out: list[dict] = []

    # Filed conversations. `filed_at` is overwritten on a re-file, so this is
    # "most recently filed", and the copy says so rather than implying it's the
    # moment the thread first landed there.
    for user_id, thread_id, folder, at, n in _fetch(
        bind, tables, "thread_folders",
        "SELECT user_id, thread_id, folder_name, filed_at, filed_count "
        "FROM thread_folders WHERE status = 'filed' AND filed_at IS NOT NULL",
    ):
        out.append(_row(
            user_id=user_id, at=at, kind="thread_filed",
            title=f"Filed into {folder}",
            detail="Recorded from the thread's last filing.",
            subject_type="thread", subject_id=thread_id,
            folder_name=folder, count=int(n or 0),
        ))

    for user_id, name, at in _fetch(
        bind, tables, "mail_folders",
        "SELECT user_id, name, approved_at FROM mail_folders "
        "WHERE status = 'active' AND approved_at IS NOT NULL",
    ):
        out.append(_row(
            user_id=user_id, at=at, kind="folder_approved",
            title=f"You approved the folder {name}",
            folder_name=name,
        ))

    for user_id, alert_id, sender, subject, at in _fetch(
        bind, tables, "alerts",
        "SELECT user_id, id, sender, subject, reply_sent_at FROM alerts "
        "WHERE reply_sent_at IS NOT NULL",
    ):
        out.append(_row(
            user_id=user_id, at=at, kind="reply_sent",
            title=f"You sent a reply to {sender or 'a contact'}",
            detail=subject or "",
            subject_type="alert", subject_id=alert_id,
            counterparty_email=sender or "",
        ))

    for user_id, nudge_id, to_email, attempt, at in _fetch(
        bind, tables, "nudges",
        "SELECT user_id, id, to_email, attempt_no, sent_at FROM nudges "
        "WHERE status = 'sent' AND sent_at IS NOT NULL",
    ):
        out.append(_row(
            user_id=user_id, at=at, kind="nudge_sent",
            title=f"You followed up with {to_email or 'a contact'}",
            subject_type="nudge", subject_id=nudge_id,
            counterparty_email=to_email or "", count=int(attempt or 1),
        ))

    # Only currently-closed loops exist to be found: closed_at is NULLed on
    # reopen, so this is a floor, not a count of everything ever closed.
    for user_id, fu_id, email, subject, at in _fetch(
        bind, tables, "followups",
        "SELECT user_id, id, counterparty_email, subject, closed_at FROM followups "
        "WHERE closed_at IS NOT NULL",
    ):
        out.append(_row(
            user_id=user_id, at=at, kind="loop_closed",
            title=f"Loop with {email or 'a contact'} closed",
            detail=subject or "",
            subject_type="followup", subject_id=fu_id,
            counterparty_email=email or "",
        ))

    _backfill(bind, out)


def downgrade() -> None:
    op.drop_table(_AE)
