"""reply lifecycle on alerts + auto_draft on sentry_config

Adds the draft→approve→send reply lifecycle columns to `alerts` (the app now
actually sends replies through the broker, not just opens Gmail compose) and an
`auto_draft` toggle on `sentry_config` (pre-draft replies during the scan so the
notification can carry them). Column-existence guarded so a re-run is safe.

Revision ID: 0003_reply_lifecycle
Revises: 0002_multi_channel_notify
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_reply_lifecycle"
down_revision: Union[str, None] = "0002_multi_channel_notify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALERT_COLUMNS = [
    ("reply_draft", sa.Text()),
    ("reply_status", sa.String()),
    ("reply_sent_at", sa.DateTime()),
    ("reply_external_id", sa.String()),
    ("reply_error", sa.Text()),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    alert_cols = {c["name"] for c in inspector.get_columns("alerts")}
    for name, coltype in _ALERT_COLUMNS:
        if name not in alert_cols:
            op.add_column("alerts", sa.Column(name, coltype, nullable=True))
    # Backfill the status default for existing rows, then it's app-managed.
    op.execute("UPDATE alerts SET reply_status = 'none' WHERE reply_status IS NULL")

    cfg_cols = {c["name"] for c in inspector.get_columns("sentry_config")}
    if "auto_draft" not in cfg_cols:
        op.add_column(
            "sentry_config",
            sa.Column("auto_draft", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    op.drop_column("sentry_config", "auto_draft")
    for name, _ in _ALERT_COLUMNS:
        op.drop_column("alerts", name)
