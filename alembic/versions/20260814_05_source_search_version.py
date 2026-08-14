"""Version source-search results so ranking changes are safely reprocessed.

Revision ID: 20260814_05
Revises: 20260814_04
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_05"
down_revision: Union[str, Sequence[str], None] = "20260814_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "citation_audit_findings",
        sa.Column(
            "source_search_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("citation_audit_findings", "source_search_version")
