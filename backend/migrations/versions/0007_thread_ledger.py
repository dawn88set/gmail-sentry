"""thread ledger — thread_messages + thread_sync_state

The app had memory of *alerts* but not of *mail*, which cost three things:

  1. Cost. A message classified `fyi` produced no row, so every 5-minute scan
     re-fetched and re-classified it for two days — thousands of LLM calls a day
     on an inbox where nothing happened. `thread_messages.triage_tier` is the
     permanent receipt; a message is judged exactly once, ever.
  2. Incremental sync. The scan re-queried a fixed `newer_than:2d` window every
     run. `thread_sync_state` holds a watermark instead.
  3. Thread state. Grouping by thread_id reveals who owes whom a reply — and
     indexing `in:sent` finally lets the app notice a reply the user sent from
     their phone.

Backfill: existing `alerts` rows are seeded into the ledger as inbound, already
hydrated and already triaged, so day one has memory and no alerted message is
ever re-classified.

Unique INDEX (not a named constraint) so it works on SQLite and Postgres alike.
Idempotent — every DDL is guarded, safe to re-run.

Revision ID: 0007_thread_ledger
Revises: 0006_alert_dedup_unique
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_thread_ledger"
down_revision: Union[str, None] = "0006_alert_dedup_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MSG = "thread_messages"
_SYNC = "thread_sync_state"


def _index(table: str, name: str, cols, *, unique: bool = False) -> None:
    insp = sa.inspect(op.get_bind())
    if name in {ix["name"] for ix in insp.get_indexes(table)}:
        return
    op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if _MSG not in tables:
        op.create_table(
            _MSG,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("gmail_message_id", sa.String(), nullable=False),
            sa.Column("thread_id", sa.String(), nullable=False),
            sa.Column("direction", sa.String(), nullable=False),
            # The query WINDOW the message was found in — the broker gives no date.
            sa.Column("ts_lo", sa.DateTime(), nullable=False),
            sa.Column("ts_hi", sa.DateTime(), nullable=False),
            sa.Column("ts_exact", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("hydrated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sender", sa.String()),
            sa.Column("counterparty_email", sa.String()),
            sa.Column("subject", sa.String()),
            sa.Column("snippet", sa.Text()),
            sa.Column("rfc822_msgid", sa.String()),
            sa.Column("label_ids", sa.JSON()),
            sa.Column("triage_tier", sa.String()),
            sa.Column("triage_source", sa.String()),
            sa.Column("triaged_at", sa.DateTime()),
            sa.Column("first_seen_at", sa.DateTime()),
        )

    _index(_MSG, "uq_tmsg_user_msg", ["user_id", "gmail_message_id"], unique=True)
    _index(_MSG, "ix_tmsg_user", ["user_id"])
    _index(_MSG, "ix_tmsg_thread", ["user_id", "thread_id", "ts_hi"])
    _index(_MSG, "ix_tmsg_direction", ["user_id", "direction", "ts_hi"])
    # The scan's candidate query: untriaged inbound, newest first.
    _index(_MSG, "ix_tmsg_untriaged", ["user_id", "triaged_at", "ts_hi"])
    _index(_MSG, "ix_tmsg_hydration", ["user_id", "hydrated", "ts_hi"])

    if _SYNC not in tables:
        op.create_table(
            _SYNC,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("inbox_watermark", sa.DateTime()),
            sa.Column("sent_watermark", sa.DateTime()),
            sa.Column("backfill_cursor", sa.DateTime()),
            sa.Column("backfill_done", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("backfill_done_at", sa.DateTime()),
            sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="45"),
            sa.Column("self_address", sa.String()),
            sa.Column("self_domain", sa.String()),
            sa.Column("alias_addresses", sa.JSON()),
            sa.Column("hydration_budget", sa.Integer(), nullable=False, server_default="25"),
            sa.Column("messages_indexed", sa.Integer(), server_default="0"),
            sa.Column("last_sweep_at", sa.DateTime()),
            sa.Column("last_error", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    _index(_SYNC, "uq_tsync_user", ["user_id"], unique=True)

    # Seed the ledger from alerts we've already seen and already classified, so
    # an existing install starts with memory instead of re-judging its backlog.
    # INSERT ... SELECT with a NOT EXISTS guard keeps this re-runnable.
    op.execute(
        f"""
        INSERT INTO {_MSG} (
            id, user_id, gmail_message_id, thread_id, direction,
            ts_lo, ts_hi, ts_exact, hydrated,
            sender, subject, snippet, rfc822_msgid,
            triage_tier, triage_source, triaged_at, first_seen_at
        )
        SELECT
            a.id, a.user_id, a.gmail_message_id,
            COALESCE(NULLIF(a.thread_id, ''), a.gmail_message_id),
            'in',
            -- FALSE/TRUE, not 0/1: SQLite accepts the integers but Postgres
            -- rejects them ("column is of type boolean but expression is of
            -- type integer"), which would fail this migration in production
            -- while passing every local test.
            a.created_at, a.created_at, FALSE, TRUE,
            a.sender, a.subject, a.snippet, a.rfc822_msgid,
            a.tier, 'backfill', a.created_at, a.created_at
        FROM alerts a
        WHERE a.gmail_message_id IS NOT NULL
          AND a.created_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM {_MSG} m
              WHERE m.user_id = a.user_id
                AND m.gmail_message_id = a.gmail_message_id
          )
        """
    )


def downgrade() -> None:
    op.drop_table(_SYNC)
    op.drop_table(_MSG)
