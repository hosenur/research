"""Create persisted papers and provider enrichment results.

Revision ID: 20260814_01
Revises:
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260814_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("paper_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_papers_content_sha256", "papers", ["content_sha256"], unique=False)

    op.create_table(
        "reference_enrichments",
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("work_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("match_method", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id", "reference_id", "provider"),
    )
    op.create_index(
        "ix_reference_enrichments_paper_revision",
        "reference_enrichments",
        ["paper_id", "revision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reference_enrichments_paper_revision", table_name="reference_enrichments")
    op.drop_table("reference_enrichments")
    op.drop_index("ix_papers_content_sha256", table_name="papers")
    op.drop_table("papers")
