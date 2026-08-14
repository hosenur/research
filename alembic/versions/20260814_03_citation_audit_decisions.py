"""Record citation verification decisions and exact source spans.

Revision ID: 20260814_03
Revises: 20260814_02
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_03"
down_revision: Union[str, Sequence[str], None] = "20260814_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "citation_audit_findings",
        sa.Column("source_text", sa.Text(), nullable=True),
    )
    op.execute(
        "UPDATE citation_audit_findings SET source_text = claim_text "
        "WHERE source_text IS NULL"
    )
    op.alter_column("citation_audit_findings", "source_text", nullable=False)

    op.create_table(
        "citation_audit_decisions",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("lane", sa.String(length=32), nullable=False),
        sa.Column("batch_key", sa.String(length=64), nullable=False),
        sa.Column("sentence_id", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("is_verifiable_claim", sa.Boolean(), nullable=False),
        sa.Column("requires_citation", sa.Boolean(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["audit_id"], ["citation_audits.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "audit_id", "lane", "batch_key", "sentence_id", "model"
        ),
    )
    op.create_index(
        "ix_citation_audit_decisions_audit_sentence",
        "citation_audit_decisions",
        ["audit_id", "sentence_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_citation_audit_decisions_audit_sentence",
        table_name="citation_audit_decisions",
    )
    op.drop_table("citation_audit_decisions")
    op.drop_column("citation_audit_findings", "source_text")
