"""Version claim-search cache identity.

Revision ID: 20260814_11
Revises: 20260814_10
Create Date: 2026-08-14
"""

from alembic import op


revision = "20260814_11"
down_revision = "20260814_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE citation_claim_searches "
        "DROP CONSTRAINT IF EXISTS citation_claim_searches_claim_hash_key"
    )
    op.execute(
        "ALTER TABLE citation_claim_searches "
        "DROP CONSTRAINT IF EXISTS uq_citation_claim_search_hash"
    )
    op.create_unique_constraint(
        "uq_citation_claim_search_identity",
        "citation_claim_searches",
        ["claim_hash", "search_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_citation_claim_search_identity",
        "citation_claim_searches",
        type_="unique",
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY claim_hash
                    ORDER BY search_version DESC, created_at DESC NULLS LAST, id DESC
                ) AS position
            FROM citation_claim_searches
        )
        DELETE FROM citation_claim_searches
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.create_unique_constraint(
        "citation_claim_searches_claim_hash_key",
        "citation_claim_searches",
        ["claim_hash"],
    )
