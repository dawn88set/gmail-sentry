"""multi-channel notification destinations on sentry_config

Adds non-secret per-channel destinations (Telegram/Discord/Teams/WhatsApp) so
attention alerts can fan out to every connected channel. Idempotent-ish: guarded
by a column-existence check so a re-run / partial state is safe.

Revision ID: 0002_multi_channel_notify
Revises: 0001_initial
Create Date: 2026-07-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_multi_channel_notify"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    "telegram_chat_id",
    "discord_channel_id",
    "teams_chat_id",
    "whatsapp_to",
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("sentry_config")}
    for col in _COLUMNS:
        if col not in existing:
            op.add_column("sentry_config", sa.Column(col, sa.String(), nullable=True))


def downgrade() -> None:
    for col in _COLUMNS:
        op.drop_column("sentry_config", col)
