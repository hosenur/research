"""Persist scholarly works and grounded citation-source searches.

Revision ID: 20260814_04
Revises: 20260814_03
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260814_04"
down_revision: Union[str, Sequence[str], None] = "20260814_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "citation_audit_findings",
        sa.Column("source_search_error", sa.Text(), nullable=True),
    )

    # Keep the most precise span when older priority/discovery lanes produced
    # overlapping findings for the same sentence.
    op.execute(
        """
        DELETE FROM citation_audit_findings AS broader
        USING citation_audit_findings AS narrower
        WHERE broader.audit_id = narrower.audit_id
          AND broader.sentence_id = narrower.sentence_id
          AND broader.id <> narrower.id
          AND int4range(broader.start_offset, broader.end_offset, '[)')
              && int4range(narrower.start_offset, narrower.end_offset, '[)')
          AND (
            char_length(broader.source_text) > char_length(narrower.source_text)
            OR (
              char_length(broader.source_text) = char_length(narrower.source_text)
              AND broader.id > narrower.id
            )
          )
        """
    )

    op.create_table(
        "provider_cache",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("cache_key", sa.String(length=128), nullable=False),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_negative", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("provider", "cache_key"),
    )

    op.create_table(
        "scholarly_works",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canonical_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_normalized", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=512), nullable=True),
        sa.Column("arxiv_id", sa.String(length=255), nullable=True),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("landing_page_url", sa.Text(), nullable=True),
        sa.Column("cited_by_count", sa.Integer(), nullable=True),
        sa.Column("provider_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("provider_payloads", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_key"),
    )
    op.create_index("ix_scholarly_works_doi", "scholarly_works", ["doi"], unique=False)
    op.create_index("ix_scholarly_works_arxiv_id", "scholarly_works", ["arxiv_id"], unique=False)
    op.create_index("ix_scholarly_works_title_normalized", "scholarly_works", ["title_normalized"], unique=False)

    op.create_table(
        "citation_source_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("work_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["citation_audit_findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["scholarly_works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id", "work_id", name="uq_citation_source_candidate_work"),
    )
    op.create_index(
        "ix_citation_source_candidates_finding_rank",
        "citation_source_candidates",
        ["finding_id", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_citation_source_candidates_finding_rank", table_name="citation_source_candidates")
    op.drop_table("citation_source_candidates")
    op.drop_index("ix_scholarly_works_title_normalized", table_name="scholarly_works")
    op.drop_index("ix_scholarly_works_arxiv_id", table_name="scholarly_works")
    op.drop_index("ix_scholarly_works_doi", table_name="scholarly_works")
    op.drop_table("scholarly_works")
    op.drop_table("provider_cache")
    op.drop_column("citation_audit_findings", "source_search_error")
