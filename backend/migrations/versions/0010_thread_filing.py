"""mail_folders + thread_folders — file whole conversations, not messages

`LabelRule` files individual INBOUND messages against hand-written rules, so a
user's own replies stay orphaned in Sent and nothing organises itself. This adds
the automatic layer: a thread is filed by who it's with, derived from the
counterparty, and the label goes on every message in the conversation — both
directions, including replies sent from a phone.

Two gates are baked into the schema rather than left to code:

  * `mail_folders.status` — a folder is born `proposed` and only an explicit
    approval makes it `active`. Nothing is ever labelled with an unapproved
    folder. The alternative is label sprawl in a real mailbox, which is hard to
    undo and exactly the kind of surprise that gets an app uninstalled.
  * `thread_folders` — filing is decided once per thread and then reused, so
    later messages cost nothing.

FALSE/TRUE, never 0/1 — Postgres rejects integers for booleans (this broke 0007
in production while passing every SQLite test).

Revision ID: 0010_thread_filing
Revises: 0009_followups
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_thread_filing"
down_revision: Union[str, None] = "0009_followups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MF = "mail_folders"
_TF = "thread_folders"


def _index(table: str, name: str, cols, *, unique: bool = False) -> None:
    insp = sa.inspect(op.get_bind())
    if name in {ix["name"] for ix in insp.get_indexes(table)}:
        return
    op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if _MF not in tables:
        op.create_table(
            _MF,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), server_default="counterparty"),
            sa.Column("source", sa.String(), server_default="derived"),
            sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
            sa.Column("counterparty_email", sa.String()),
            sa.Column("thread_count", sa.Integer(), server_default="0"),
            sa.Column("approved_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
        )

    _index(_MF, "uq_folder_user_name", ["user_id", "name"], unique=True)
    _index(_MF, "ix_folder_user_status", ["user_id", "status"])

    if _TF not in tables:
        op.create_table(
            _TF,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("thread_id", sa.String(), nullable=False),
            sa.Column("folder_name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("confidence", sa.Integer(), server_default="0"),
            sa.Column("decided_by", sa.String(), server_default="auto"),
            sa.Column("filed_count", sa.Integer(), server_default="0"),
            sa.Column("filed_at", sa.DateTime()),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    _index(_TF, "uq_tfolder_user_thread", ["user_id", "thread_id"], unique=True)
    _index(_TF, "ix_tfolder_user_status", ["user_id", "status"])

    # Adopt the labels the user already files into by hand as approved folders,
    # so smart filing reuses their existing structure instead of inventing a
    # parallel one beside it.
    rules = bind.execute(
        sa.text(
            "SELECT DISTINCT user_id, target_label FROM label_rules "
            "WHERE target_label IS NOT NULL AND target_label <> ''"
        )
    ).fetchall()

    import uuid

    for user_id, label in rules:
        exists = bind.execute(
            sa.text(f"SELECT 1 FROM {_MF} WHERE user_id = :u AND name = :n"),
            {"u": user_id, "n": label},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                f"INSERT INTO {_MF} (id, user_id, name, kind, source, status, thread_count) "
                "VALUES (:id, :u, :n, 'topical', 'user', 'active', 0)"
            ),
            {"id": str(uuid.uuid4()), "u": user_id, "n": label},
        )

    # Filing settings live with the rest of the per-user config.
    cfg_cols = {c["name"] for c in insp.get_columns("sentry_config")}
    if "filing_enabled" not in cfg_cols:
        op.add_column(
            "sentry_config",
            sa.Column("filing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "filing_started_at" not in cfg_cols:
        # Filing is forward-only from the moment it's switched on — see the
        # service. Without this marker the first sweep would relabel every
        # thread in the backfilled history at once.
        op.add_column("sentry_config", sa.Column("filing_started_at", sa.DateTime()))


def downgrade() -> None:
    op.drop_column("sentry_config", "filing_started_at")
    op.drop_column("sentry_config", "filing_enabled")
    op.drop_table(_TF)
    op.drop_table(_MF)
