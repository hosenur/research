"""Add agent citation-improvement candidates and atomic citation changes.

Revision ID: 20260815_08
Revises: 20260815_07
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_08"
down_revision = "20260815_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "citation_improvement_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("review_finding_id", sa.String(length=36), nullable=False),
        sa.Column("work_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("support_status", sa.String(length=32), server_default="not_started", nullable=False),
        sa.Column("supports_claim", sa.Boolean(), nullable=True),
        sa.Column("support_confidence", sa.Float(), nullable=True),
        sa.Column("support_explanation", sa.Text(), nullable=True),
        sa.Column("support_evidence", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "support_status IN ('not_started', 'running', 'verified', 'rejected', 'failed')",
            name="ck_citation_improvement_candidate_support_status",
        ),
        sa.CheckConstraint(
            "decision IN ('pending', 'accepted', 'rejected')",
            name="ck_citation_improvement_candidate_decision",
        ),
        sa.ForeignKeyConstraint(
            ["review_finding_id"], ["claim_citation_reviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["work_id"], ["scholarly_works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_finding_id",
            "work_id",
            name="uq_citation_improvement_candidate_work",
        ),
    )
    op.create_index(
        "ix_citation_improvement_candidates_finding_rank",
        "citation_improvement_candidates",
        ["review_finding_id", "rank"],
    )
    op.drop_constraint("ck_edit_operation_type", "edit_operations", type_="check")
    op.create_check_constraint(
        "ck_edit_operation_type",
        "edit_operations",
        "operation_type IN ('replace_text', 'insert_citation', 'remove_citation', 'restore_revision', 'citation_change')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_edit_operation_type", "edit_operations", type_="check")
    op.create_check_constraint(
        "ck_edit_operation_type",
        "edit_operations",
        "operation_type IN ('replace_text', 'insert_citation', 'remove_citation', 'restore_revision')",
    )
    op.drop_index(
        "ix_citation_improvement_candidates_finding_rank",
        table_name="citation_improvement_candidates",
    )
    op.drop_table("citation_improvement_candidates")
