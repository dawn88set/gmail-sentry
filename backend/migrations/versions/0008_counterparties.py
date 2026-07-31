"""counterparties — who it would cost the user to ignore

Replaces the top-5 `comm_profiles.vip_senders` list the scan injected as
synthetic triage rules. That list ranked people by how often they appear;
this table ranks them by revealed preference — whether the user actually
replies, how fast, over how many threads — all derived from the thread ledger
by plain SQL, with no Gmail or LLM calls.

Backfill: existing `vip_senders` become pinned counterparties, so a user who
already curated that list doesn't lose it and doesn't have to wait for the
ledger to re-learn them.

Note FALSE/TRUE rather than 0/1 in the seeding INSERT — SQLite accepts the
integers, Postgres rejects them for boolean columns (this exact mistake broke
0007 in production and passed every local test).

Revision ID: 0008_counterparties
Revises: 0007_thread_ledger
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_counterparties"
down_revision: Union[str, None] = "0007_thread_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CP = "counterparties"


def _index(table: str, name: str, cols, *, unique: bool = False) -> None:
    insp = sa.inspect(op.get_bind())
    if name in {ix["name"] for ix in insp.get_indexes(table)}:
        return
    op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _CP not in set(insp.get_table_names()):
        op.create_table(
            _CP,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("domain", sa.String()),
            sa.Column("display_name", sa.String()),
            sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("msg_in_count", sa.Integer(), server_default="0"),
            sa.Column("msg_out_count", sa.Integer(), server_default="0"),
            sa.Column("thread_count", sa.Integer(), server_default="0"),
            sa.Column("threads_you_replied", sa.Integer(), server_default="0"),
            sa.Column("your_reply_rate", sa.Integer(), server_default="0"),
            sa.Column("their_reply_rate", sa.Integer(), server_default="0"),
            sa.Column("your_median_reply_h", sa.Integer()),
            sa.Column("their_median_reply_h", sa.Integer()),
            sa.Column("first_seen_at", sa.DateTime()),
            sa.Column("last_seen_at", sa.DateTime()),
            sa.Column("relationship", sa.String(), server_default="unknown"),
            sa.Column("relationship_source", sa.String(), server_default="inferred"),
            sa.Column("importance", sa.Integer(), server_default="0"),
            sa.Column("crm_source", sa.String()),
            sa.Column("crm_id", sa.String()),
            sa.Column("crm_company", sa.String()),
            sa.Column("crm_stage", sa.String()),
            sa.Column("crm_owner", sa.String()),
            sa.Column("crm_checked_at", sa.DateTime()),
            sa.Column("crm_status", sa.String()),
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    _index(_CP, "uq_cp_user_email", ["user_id", "email"], unique=True)
    _index(_CP, "ix_cp_user", ["user_id"])
    _index(_CP, "ix_cp_importance", ["user_id", "importance"])
    _index(_CP, "ix_cp_last_seen", ["user_id", "last_seen_at"])

    # Seed from the VIP list the user (or the profile learner) already curated.
    # Pinned, because an explicit VIP is a stated preference and shouldn't have
    # to be re-earned from behaviour. Done in Python rather than SQL because
    # vip_senders is a JSON array and JSON handling differs across backends.
    profiles = bind.execute(
        sa.text("SELECT user_id, vip_senders FROM comm_profiles WHERE vip_senders IS NOT NULL")
    ).fetchall()

    import json
    import uuid

    for user_id, vips in profiles:
        if isinstance(vips, str):
            try:
                vips = json.loads(vips)
            except (TypeError, ValueError):
                continue
        for v in (vips or [])[:20]:
            if not isinstance(v, dict):
                continue
            email = (v.get("email") or "").strip().lower()
            if not email or "@" not in email:
                continue
            exists = bind.execute(
                sa.text(f"SELECT 1 FROM {_CP} WHERE user_id = :u AND email = :e"),
                {"u": user_id, "e": email},
            ).first()
            if exists:
                continue
            bind.execute(
                sa.text(
                    f"INSERT INTO {_CP} "
                    "(id, user_id, email, domain, display_name, is_internal, pinned, muted, "
                    " relationship, relationship_source, importance) "
                    "VALUES (:id, :u, :e, :d, :n, FALSE, TRUE, FALSE, "
                    " 'unknown', 'inferred', 100)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "u": user_id,
                    "e": email,
                    "d": email.split("@")[-1],
                    "n": (v.get("name") or "")[:200],
                },
            )


def downgrade() -> None:
    op.drop_table(_CP)
