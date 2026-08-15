"""Add progressive pipeline stages and versioned retrieval indexes.

Revision ID: 20260815_02
Revises: 20260815_01
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260815_02"
down_revision = "20260815_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_paper_chunk_key", "paper_chunks", type_="unique")
    op.drop_index("ix_paper_chunks_paper_order", table_name="paper_chunks")
    op.add_column(
        "paper_chunks",
        sa.Column("source_node_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "paper_chunks",
        sa.Column(
            "index_kind",
            sa.String(length=32),
            server_default="authoritative",
            nullable=False,
        ),
    )
    op.add_column(
        "paper_chunks",
        sa.Column("paper_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "paper_chunks",
        sa.Column("generation", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_paper_chunks_index_kind",
        "paper_chunks",
        "index_kind IN ('provisional', 'authoritative')",
    )
    op.create_unique_constraint(
        "uq_paper_chunk_generation_key",
        "paper_chunks",
        ["paper_id", "index_kind", "generation", "chunk_key"],
    )
    op.create_index(
        "ix_paper_chunks_paper_index_order",
        "paper_chunks",
        ["paper_id", "index_kind", "generation", "chunk_order"],
    )

    op.create_table(
        "paper_pipeline_stages",
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="not_started", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("progress", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('not_started', 'queued', 'running', 'completed', 'failed', 'skipped')",
            name="ck_paper_pipeline_stage_status",
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id", "stage"),
    )
    op.create_index(
        "ix_paper_pipeline_stages_status",
        "paper_pipeline_stages",
        ["paper_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_pipeline_stages_status", table_name="paper_pipeline_stages")
    op.drop_table("paper_pipeline_stages")
    op.drop_index("ix_paper_chunks_paper_index_order", table_name="paper_chunks")
    op.drop_constraint("uq_paper_chunk_generation_key", "paper_chunks", type_="unique")
    op.drop_constraint("ck_paper_chunks_index_kind", "paper_chunks", type_="check")
    op.drop_column("paper_chunks", "generation")
    op.drop_column("paper_chunks", "paper_revision")
    op.drop_column("paper_chunks", "index_kind")
    op.drop_column("paper_chunks", "source_node_id")
    op.create_unique_constraint(
        "uq_paper_chunk_key", "paper_chunks", ["paper_id", "chunk_key"]
    )
    op.create_index(
        "ix_paper_chunks_paper_order", "paper_chunks", ["paper_id", "chunk_order"]
    )
