"""Add durable paper ingestion lifecycle.

Revision ID: 20260815_01
Revises: 20260814_11
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260815_01"
down_revision = "20260814_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "papers",
        "paper_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.add_column(
        "papers",
        sa.Column("status", sa.String(length=32), server_default="ready", nullable=False),
    )
    op.add_column("papers", sa.Column("source_object_key", sa.Text(), nullable=True))
    op.add_column("papers", sa.Column("parse_error", sa.Text(), nullable=True))
    op.add_column(
        "papers", sa.Column("parse_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "papers", sa.Column("parse_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE papers SET parse_completed_at = updated_at WHERE paper_json IS NOT NULL")
    op.alter_column("papers", "status", server_default="uploaded")
    op.create_check_constraint(
        "ck_papers_status",
        "papers",
        "status IN ('uploaded', 'parsing', 'ready', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_papers_status", "papers", type_="check")
    op.drop_column("papers", "parse_completed_at")
    op.drop_column("papers", "parse_started_at")
    op.drop_column("papers", "parse_error")
    op.drop_column("papers", "source_object_key")
    op.drop_column("papers", "status")
    op.execute("DELETE FROM papers WHERE paper_json IS NULL")
    op.alter_column(
        "papers",
        "paper_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
