"""Link parsed bibliography enrichments to canonical scholarly works.

Revision ID: 20260814_06
Revises: 20260814_05
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_06"
down_revision: Union[str, Sequence[str], None] = "20260814_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reference_enrichments",
        sa.Column("work_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_reference_enrichments_work_id",
        "reference_enrichments",
        "scholarly_works",
        ["work_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_reference_enrichments_work_id",
        "reference_enrichments",
        ["work_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE reference_enrichments AS enrichment
        SET work_id = work.id
        FROM scholarly_works AS work
        WHERE enrichment.work_id IS NULL
          AND enrichment.provider = 'openalex'
          AND enrichment.work_json IS NOT NULL
          AND work.provider_ids->>'openalex' = enrichment.work_json->>'id'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_reference_enrichments_work_id", table_name="reference_enrichments")
    op.drop_constraint(
        "fk_reference_enrichments_work_id",
        "reference_enrichments",
        type_="foreignkey",
    )
    op.drop_column("reference_enrichments", "work_id")
