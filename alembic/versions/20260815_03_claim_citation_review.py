"""Add durable existing claim/citation support judgments.

Revision ID: 20260815_03
Revises: 20260815_02
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260815_03"
down_revision = "20260815_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claim_citation_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("paper_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sentence_id", sa.String(length=255), nullable=False),
        sa.Column("section_id", sa.String(length=255), nullable=False),
        sa.Column("section_title", sa.String(length=512), nullable=False),
        sa.Column("paragraph_id", sa.String(length=255), nullable=False),
        sa.Column("citation_id", sa.String(length=255), nullable=True),
        sa.Column("reference_id", sa.String(length=255), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("citation_text", sa.Text(), nullable=False),
        sa.Column("work_id", sa.String(length=36), nullable=True),
        sa.Column("work_title", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("provider_evidence", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("classification", sa.String(length=32), server_default="unverifiable", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("explanation", sa.Text(), server_default="", nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("classification IN ('supported', 'weak', 'contradicted', 'unverifiable')", name="ck_claim_citation_review_classification"),
        sa.CheckConstraint("status IN ('pending', 'completed', 'failed')", name="ck_claim_citation_review_status"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["scholarly_works.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "paper_revision", "sentence_id", "reference_id", name="uq_claim_citation_review_pair"),
    )
    op.create_index("ix_claim_citation_reviews_paper_classification", "claim_citation_reviews", ["paper_id", "classification"])


def downgrade() -> None:
    op.drop_index("ix_claim_citation_reviews_paper_classification", table_name="claim_citation_reviews")
    op.drop_table("claim_citation_reviews")
