"""Add constrained edit proposals and immutable manuscript revisions.

Revision ID: 20260815_04
Revises: 20260815_03
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260815_04"
down_revision = "20260815_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("manuscript_revision", sa.Integer(), server_default="1", nullable=False))
    op.create_table(
        "manuscript_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_revision", sa.Integer(), nullable=True),
        sa.Column("paper_json", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="parse", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("proposal_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "revision", name="uq_manuscript_revision_number"),
    )
    op.create_index("ix_manuscript_revisions_paper_created", "manuscript_revisions", ["paper_id", "created_at"])
    op.execute(
        """
        INSERT INTO manuscript_revisions
            (id, paper_id, revision, parent_revision, paper_json, content_hash, source)
        SELECT gen_random_uuid()::text, id, 1, NULL, paper_json, content_sha256, 'parse'
        FROM papers WHERE paper_json IS NOT NULL
        """
    )
    op.create_table(
        "edit_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="planned", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("approved_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('planned', 'approved', 'rejected', 'conflict', 'invalid')", name="ck_edit_proposal_status"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edit_proposals_paper_created", "edit_proposals", ["paper_id", "created_at"])
    op.create_table(
        "edit_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("node_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("before_text", sa.Text(), nullable=False),
        sa.Column("after_text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), server_default="", nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("operation_type IN ('replace_text', 'insert_citation')", name="ck_edit_operation_type"),
        sa.CheckConstraint("validation_status IN ('valid', 'invalid')", name="ck_edit_operation_validation"),
        sa.ForeignKeyConstraint(["proposal_id"], ["edit_proposals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "position", name="uq_edit_operation_position"),
    )


def downgrade() -> None:
    op.drop_table("edit_operations")
    op.drop_index("ix_edit_proposals_paper_created", table_name="edit_proposals")
    op.drop_table("edit_proposals")
    op.drop_index("ix_manuscript_revisions_paper_created", table_name="manuscript_revisions")
    op.drop_table("manuscript_revisions")
    op.drop_column("papers", "manuscript_revision")
