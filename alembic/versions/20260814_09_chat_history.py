"""Persist paper chat threads and messages."""
from alembic import op
import sqlalchemy as sa

revision = "20260814_09"
down_revision = "20260814_08"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("thread_id", sa.String(255), sa.ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_thread_sequence", "chat_messages", ["thread_id", "sequence"])

def downgrade() -> None:
    op.drop_index("ix_chat_messages_thread_sequence", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
