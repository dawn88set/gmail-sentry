"""unique (user_id, gmail_message_id) on alerts — kill duplicate alerts

Overlapping scan runs (a slow scan while the platform fires the next interval, or a
manual scan concurrent with a scheduled one) could both pass the racy pre-insert
dedup SELECT and insert an alert + fire a notification for the SAME message. This
adds a unique index so the DB rejects the second insert (run_scan catches the
IntegrityError and skips). Existing duplicate rows are collapsed first.

A unique INDEX (not a named constraint) is used so it works on both SQLite (local
dev) and Postgres (prod). Idempotent — safe to re-run.

Revision ID: 0006_alert_dedup_unique
Revises: 0005_channel_tiers
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_alert_dedup_unique"
down_revision: Union[str, None] = "0005_channel_tiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_alerts_user_msg"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "alerts" not in insp.get_table_names():
        return

    # 1) Collapse existing duplicates — keep one row per (user_id, gmail_message_id).
    #    Nested subquery so the DELETE doesn't read the same table it modifies.
    op.execute(
        """
        DELETE FROM alerts
        WHERE id NOT IN (
            SELECT keep_id FROM (
                SELECT MIN(id) AS keep_id
                FROM alerts
                GROUP BY user_id, gmail_message_id
            ) AS keep
        )
        """
    )

    # 2) Enforce uniqueness going forward.
    existing = {ix["name"] for ix in insp.get_indexes("alerts")}
    if _INDEX not in existing:
        op.create_index(
            _INDEX, "alerts", ["user_id", "gmail_message_id"], unique=True
        )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="alerts")
