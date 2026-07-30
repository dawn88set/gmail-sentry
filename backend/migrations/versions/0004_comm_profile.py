"""communication-pattern profile

Adds the `comm_profiles` table — one row per user holding what Gmail Sentry has
learned about how they actually communicate (behavioral VIPs, writing tone, a few
sent-mail exemplars). Used to boost triage for real contacts and draft replies in
the user's real voice. Guarded by a table-existence check so a re-run is safe.

Revision ID: 0004_comm_profile
Revises: 0003_reply_lifecycle
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_comm_profile"
down_revision: Union[str, None] = "0003_reply_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "comm_profiles" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "comm_profiles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("vip_senders", sa.JSON()),
        sa.Column("response_habits", sa.JSON()),
        sa.Column("tone", sa.String()),
        sa.Column("style_exemplars", sa.JSON()),
        sa.Column("signature", sa.String()),
        sa.Column("refreshed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_comm_profiles_user_id", "comm_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_comm_profiles_user_id", table_name="comm_profiles")
    op.drop_table("comm_profiles")
