"""scan_interval_minutes — let the owner choose how often their mail is checked

The platform owns the schedule: the `sentry-scan` trigger fires on ITS interval
and calls the app. That interval lives in Claritty's trigger settings, which is
the wrong place for a preference about how noisy someone's own inbox assistant
should be — most people will never find it, and it isn't part of this app's UI.

So the cadence becomes app state, and the scheduled path checks it before doing
any work. It can only make scanning less frequent than the trigger, never more,
which is why the UI offers the trigger's own cadence as the fastest choice and
says as much rather than implying a control it doesn't have.

Defaults to 5 to match the shipped trigger, so existing installs behave exactly
as they did before this ran.

NOT NULL with a server_default: existing rows need a value, and without the
server default the ALTER fails on Postgres the moment the table isn't empty.

Revision ID: 0012_scan_interval
Revises: 0011_activity_events
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_scan_interval"
down_revision = "0011_activity_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sentry_config",
        sa.Column(
            "scan_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("sentry_config", "scan_interval_minutes")
