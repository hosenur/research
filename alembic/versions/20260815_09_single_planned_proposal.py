"""Enforce one planned edit proposal per paper revision.

Revision ID: 20260815_09
Revises: 20260815_08
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_09"
down_revision = "20260815_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY paper_id, base_revision
                    ORDER BY created_at DESC, id DESC
                ) AS position
            FROM edit_proposals
        )
        UPDATE edit_proposals
        SET status = 'conflict'
        WHERE status = 'planned'
          AND id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.create_index(
        "uq_edit_proposals_one_planned_per_revision",
        "edit_proposals",
        ["paper_id", "base_revision"],
        unique=True,
        postgresql_where=sa.text("status = 'planned'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_edit_proposals_one_planned_per_revision",
        table_name="edit_proposals",
    )
