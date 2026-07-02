"""initial schema for Gmail Sentry

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-30
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
        "triage_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )

    op.create_table(
        "label_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("match_type", sa.String(), nullable=False),
        sa.Column("match_value", sa.Text(), nullable=False),
        sa.Column("target_label", sa.String(), nullable=False),
        sa.Column("archive_after", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("gmail_message_id", sa.String(), nullable=False, index=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("rfc822_msgid", sa.String(), nullable=True),
        sa.Column("sender", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("tier", sa.String(), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("deep_link", sa.Text(), nullable=True),
        sa.Column("slack_sent", sa.Boolean(), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )

    op.create_table(
        "scan_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("scanned", sa.Integer(), nullable=True),
        sa.Column("flagged", sa.Integer(), nullable=True),
        sa.Column("labeled", sa.Integer(), nullable=True),
        sa.Column("notified", sa.Integer(), nullable=True),
        sa.Column("promo_count", sa.Integer(), nullable=True),
        sa.Column("social_count", sa.Integer(), nullable=True),
        sa.Column("spam_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True, index=True),
    )

    op.create_table(
        "sentry_config",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("slack_channel", sa.String(), nullable=True),
        sa.Column("notify_tier", sa.String(), nullable=True),
        sa.Column("onboarded", sa.Boolean(), nullable=True),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("muted_senders", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
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
    op.drop_table("sentry_config")
    op.drop_table("scan_runs")
    op.drop_table("alerts")
    op.drop_table("label_rules")
    op.drop_table("triage_rules")
