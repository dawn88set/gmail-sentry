"""followups + nudges — open loops that outlive the alert

An Alert answers "does this message need your eyes now?" and dies when the user
handles it. A FollowUp answers "is there an unresolved loop here?" and lives
until the loop actually closes. Before this, sending a reply removed the thread
from the app entirely, so "I sent them a quote and never heard back" was
invisible — which is precisely the case that loses customers.

`alerts.followup_id` links the two. No backfill of existing alerts into
follow-ups: state is derived from the ledger on the next sweep, and inventing
loops for mail the user already dealt with would surface a wall of stale work on
first run.

FALSE/TRUE, not 0/1 — Postgres rejects integers for boolean columns (this broke
0007 in production while passing every SQLite test).

Revision ID: 0009_followups
Revises: 0008_counterparties
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_followups"
down_revision: Union[str, None] = "0008_counterparties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FU = "followups"
_NU = "nudges"


def _index(table: str, name: str, cols, *, unique: bool = False) -> None:
    insp = sa.inspect(op.get_bind())
    if name in {ix["name"] for ix in insp.get_indexes(table)}:
        return
    op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if _FU not in tables:
        op.create_table(
            _FU,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("thread_id", sa.String(), nullable=False),
            sa.Column("counterparty_email", sa.String()),
            sa.Column("counterparty_name", sa.String()),
            sa.Column("subject", sa.String()),
            sa.Column("state", sa.String(), nullable=False, server_default="awaiting_you"),
            sa.Column("ball", sa.String(), nullable=False, server_default="you"),
            sa.Column("state_changed_at", sa.DateTime()),
            sa.Column("ask_summary", sa.String(length=280)),
            sa.Column("ask_confidence", sa.Integer(), server_default="0"),
            sa.Column("due_at", sa.DateTime()),
            sa.Column("due_source", sa.String()),
            sa.Column("last_inbound_at", sa.DateTime()),
            sa.Column("last_outbound_at", sa.DateTime()),
            sa.Column("last_activity_at", sa.DateTime()),
            sa.Column("stale_after_hours", sa.Integer(), server_default="72"),
            sa.Column("importance", sa.Integer(), server_default="0"),
            sa.Column("risk", sa.Integer(), server_default="0"),
            sa.Column("nudge_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_nudge_at", sa.DateTime()),
            sa.Column("snoozed_until", sa.DateTime()),
            sa.Column("closed_reason", sa.String()),
            sa.Column("closed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    _index(_FU, "uq_followups_user_thread", ["user_id", "thread_id"], unique=True)
    _index(_FU, "ix_fu_user", ["user_id"])
    # The list query: open loops for a user, worst first.
    _index(_FU, "ix_fu_state_risk", ["user_id", "state", "risk"])
    _index(_FU, "ix_fu_due", ["user_id", "due_at"])

    if _NU not in tables:
        op.create_table(
            _NU,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("followup_id", sa.String(), nullable=False),
            sa.Column("thread_id", sa.String()),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("tone", sa.String(), server_default="gentle"),
            sa.Column("draft", sa.Text()),
            sa.Column("subject", sa.String()),
            sa.Column("to_email", sa.String()),
            sa.Column("in_reply_to", sa.String()),
            sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
            sa.Column("sent_at", sa.DateTime()),
            sa.Column("external_id", sa.String()),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
        )

    _index(_NU, "ix_nudge_user", ["user_id"])
    _index(_NU, "ix_nudge_followup", ["followup_id", "status"])

    # Link an alert to the loop it belongs to.
    alert_cols = {c["name"] for c in insp.get_columns("alerts")}
    if "followup_id" not in alert_cols:
        op.add_column("alerts", sa.Column("followup_id", sa.String()))
    _index("alerts", "ix_alerts_followup", ["followup_id"])


def downgrade() -> None:
    op.drop_column("alerts", "followup_id")
    op.drop_table(_NU)
    op.drop_table(_FU)
