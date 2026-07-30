"""per-channel urgency routing on sentry_config

Adds `channel_tiers` (JSON) to sentry_config so each notification channel can have
its own minimum urgency (e.g. urgent → WhatsApp, needs_reply → Slack). A channel
absent from the map falls back to the global notify_tier. Column-guarded so a
re-run is safe.

Revision ID: 0005_channel_tiers
Revises: 0004_comm_profile
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_channel_tiers"
down_revision: Union[str, None] = "0004_comm_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("sentry_config")}
    if "channel_tiers" not in cols:
        op.add_column("sentry_config", sa.Column("channel_tiers", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sentry_config", "channel_tiers")
