"""Create incremental citation audit records.

Revision ID: 20260814_02
Revises: 20260814_01
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260814_02"
down_revision: Union[str, Sequence[str], None] = "20260814_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "citation_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("total_sentences", sa.Integer(), server_default="0", nullable=False),
        sa.Column("heuristic_candidates", sa.Integer(), server_default="0", nullable=False),
        sa.Column("priority_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("priority_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("discovery_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("discovery_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id"),
    )

    op.create_table(
        "citation_audit_batches",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("lane", sa.String(length=32), nullable=False),
        sa.Column("batch_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("item_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["audit_id"], ["citation_audits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("audit_id", "lane", "batch_key"),
    )

    op.create_table(
        "citation_audit_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("sentence_id", sa.String(length=255), nullable=False),
        sa.Column("section_id", sa.String(length=255), nullable=False),
        sa.Column("section_title", sa.String(length=512), nullable=False),
        sa.Column("paragraph_id", sa.String(length=255), nullable=False),
        sa.Column("sentence_text", sa.Text(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_hash", sa.String(length=64), nullable=False),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("detected_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("heuristic_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("source_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_search_status", sa.String(length=32), server_default="not_started", nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["audit_id"], ["citation_audits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", "claim_hash", name="uq_citation_audit_finding_claim"),
    )
    op.create_index(
        "ix_citation_audit_findings_revision",
        "citation_audit_findings",
        ["audit_id", "revision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_citation_audit_findings_revision", table_name="citation_audit_findings")
    op.drop_table("citation_audit_findings")
    op.drop_table("citation_audit_batches")
    op.drop_table("citation_audits")
