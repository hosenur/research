"""Add pgvector-backed paper chunks."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260814_08"
down_revision = "20260814_07"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_key", sa.String(255), nullable=False),
        sa.Column("chunk_type", sa.String(32), nullable=False),
        sa.Column("section_id", sa.String(255), nullable=True),
        sa.Column("section_title", sa.String(512), nullable=True),
        sa.Column("reference_id", sa.String(255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("paper_id", "chunk_key", name="uq_paper_chunk_key"),
    )
    op.create_index("ix_paper_chunks_paper_order", "paper_chunks", ["paper_id", "chunk_order"])

def downgrade() -> None:
    op.drop_index("ix_paper_chunks_paper_order", table_name="paper_chunks")
    op.drop_table("paper_chunks")
