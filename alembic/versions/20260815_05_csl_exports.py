"""Add confirmed CSL styles and durable exports.

Revision ID: 20260815_05
Revises: 20260815_04
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260815_05"
down_revision = "20260815_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_csl_styles",
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("style_id", sa.String(length=255), nullable=False),
        sa.Column("confirmed", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("detected_family", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id"),
    )
    op.create_table(
        "paper_exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_revision", sa.Integer(), nullable=False),
        sa.Column("style_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("latex_object_key", sa.Text(), nullable=True),
        sa.Column("pdf_object_key", sa.Text(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("compiler_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_paper_export_status"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_exports_paper_created", "paper_exports", ["paper_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_paper_exports_paper_created", table_name="paper_exports")
    op.drop_table("paper_exports")
    op.drop_table("paper_csl_styles")
