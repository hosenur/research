"""Add paper page counts for bounded automatic review.

Revision ID: 20260815_06
Revises: 20260815_05
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_06"
down_revision = "20260815_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("page_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("papers", "page_count")
