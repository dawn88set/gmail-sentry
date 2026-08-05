"""thread_reads — what a thread actually SAYS

Every other table here records who and when. None of them knows what was asked
or promised, because until this one the app had never read an email: triage
classified from a ~100-character snippet, "the ask" was a regex over that
snippet, and every surface above them was counting and sorting metadata.

Each row carries the quote its claim came from, and `comprehension._verify`
discards any field whose quote isn't present verbatim in the fetched messages —
so a row here cannot contain something the mail doesn't support.

`read_through_message_id` is the staleness marker rather than a timestamp: a
thread is re-read only when its newest message id changes, which is what makes
this affordable. Indexed on (user_id, thread_id) as a unique pair because a
second row for one thread would mean two answers to the same question.

`commitment_due` is indexed on its own — "what am I late on?" sorts by it, and
that is the query this whole table exists to make possible.

Revision ID: 0013_thread_reads
Revises: 0012_scan_interval
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_thread_reads"
down_revision = "0012_scan_interval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thread_reads",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("their_ask", sa.String(length=280), server_default=""),
        sa.Column("their_ask_quote", sa.Text(), server_default=""),
        sa.Column("their_ask_at", sa.DateTime()),
        sa.Column("your_commitment", sa.String(length=280), server_default=""),
        sa.Column("commitment_quote", sa.Text(), server_default=""),
        sa.Column("commitment_at", sa.DateTime()),
        sa.Column("commitment_due", sa.DateTime()),
        sa.Column("commitment_met_at", sa.DateTime()),
        sa.Column("blocked_on", sa.String(), server_default=""),
        sa.Column("amounts", sa.JSON()),
        sa.Column("summary", sa.String(length=280), server_default=""),
        sa.Column("confidence", sa.Integer(), server_default="0"),
        sa.Column("read_through_message_id", sa.String(), server_default=""),
        sa.Column("messages_read", sa.Integer(), server_default="0"),
        sa.Column("model", sa.String(), server_default=""),
        sa.Column("error", sa.Text(), server_default=""),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("user_id", "thread_id", name="uq_thread_reads_user_thread"),
    )
    op.create_index("ix_thread_reads_user", "thread_reads", ["user_id"])
    op.create_index("ix_thread_reads_thread", "thread_reads", ["thread_id"])
    op.create_index("ix_thread_reads_read_at", "thread_reads", ["read_at"])
    # "What am I late on?" — the query this table exists for.
    op.create_index("ix_thread_reads_due", "thread_reads", ["user_id", "commitment_due"])


def downgrade() -> None:
    op.drop_index("ix_thread_reads_due", table_name="thread_reads")
    op.drop_index("ix_thread_reads_read_at", table_name="thread_reads")
    op.drop_index("ix_thread_reads_thread", table_name="thread_reads")
    op.drop_index("ix_thread_reads_user", table_name="thread_reads")
    op.drop_table("thread_reads")
