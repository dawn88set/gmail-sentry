"""thread_reads.dropped — what the verifier refused, and why that matters

Every judgement this app makes must carry a quote that appears verbatim in the
mail it came from; anything else is dropped before it reaches a screen. That is
the honesty mechanism, and it is also a silent one: a dropped field and a field
the model never produced look exactly the same afterwards — empty.

That was tolerable while the only trace was a log line. It stopped being
tolerable once two things became true at once: production is the FIRST place a
real model's output meets this verifier (the LLM proxy needs a per-app token the
platform injects, so it cannot be exercised locally), and `GET /api/apps/:id/logs`
returns four placeholder lines rather than container logs.

So if some unanticipated formatting difference caused the verifier to reject
everything — as curly apostrophes very nearly did — the app would appear to have
nothing to say, and there would be no way to find out why from outside. This
column is the difference between diagnosing that in a minute and never.

Revision ID: 0014_thread_read_dropped
Revises: 0013_thread_reads
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_thread_read_dropped"
down_revision = "0013_thread_reads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default is required: the column is added to a table that already
    # has rows, and reads written before this migration genuinely dropped
    # nothing we can now know about — "" is the honest value for them.
    op.add_column(
        "thread_reads",
        sa.Column("dropped", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("thread_reads", "dropped")
