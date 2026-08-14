"""Persist reusable claim searches, source evidence, and user decisions."""

from alembic import op
import sqlalchemy as sa

revision = "20260814_07"
down_revision = "20260814_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("citation_source_candidates", sa.Column("support_status", sa.String(32), server_default="not_started", nullable=False))
    op.add_column("citation_source_candidates", sa.Column("supports_claim", sa.Boolean(), nullable=True))
    op.add_column("citation_source_candidates", sa.Column("support_confidence", sa.Float(), nullable=True))
    op.add_column("citation_source_candidates", sa.Column("support_explanation", sa.Text(), nullable=True))
    op.add_column("citation_source_candidates", sa.Column("support_evidence", sa.Text(), nullable=True))
    op.add_column("citation_source_candidates", sa.Column("decision", sa.String(16), server_default="pending", nullable=False))
    op.add_column("citation_source_candidates", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "citation_claim_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("search_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "citation_claim_search_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("search_id", sa.String(36), sa.ForeignKey("citation_claim_searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("scholarly_works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.UniqueConstraint("search_id", "work_id", name="uq_citation_claim_search_result"),
    )
    op.create_table(
        "confirmed_citations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.String(36), sa.ForeignKey("citation_audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("scholarly_works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), server_default="accepted", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("finding_id", "work_id", name="uq_confirmed_citation_finding_work"),
    )


def downgrade() -> None:
    op.drop_table("confirmed_citations")
    op.drop_table("citation_claim_search_results")
    op.drop_table("citation_claim_searches")
    for name in ("decided_at", "decision", "support_evidence", "support_explanation", "support_confidence", "supports_claim", "support_status"):
        op.drop_column("citation_source_candidates", name)
