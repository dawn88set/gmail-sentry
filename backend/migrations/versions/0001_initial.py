"""initial schema (tasks, user_integrations, workflow_executions)

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(), nullable=True, index=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "user_integrations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("service", sa.String(), nullable=False, index=True),
        sa.Column("auth_type", sa.String(), nullable=True),
        sa.Column("credentials", sa.JSON(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, index=True),
    )

    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workflow_id", sa.String(), nullable=False, index=True),
        sa.Column("trigger_id", sa.String(), nullable=True, index=True),
        sa.Column("user_id", sa.String(), nullable=True, index=True),
        sa.Column("status", sa.String(), nullable=True, index=True),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("workflow_executions")
    op.drop_table("user_integrations")
    op.drop_table("tasks")
