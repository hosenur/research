"""Keep human citation-review feedback for ranking evaluation."""
from alembic import op
import sqlalchemy as sa

revision = "20260814_10"
down_revision = "20260814_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "citation_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.String(36), sa.ForeignKey("citation_audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("citation_source_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feedback", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False, server_default="anonymous"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_citation_feedback_paper_created", "citation_feedback", ["paper_id", "created_at"])
    op.create_index("ix_citation_feedback_finding", "citation_feedback", ["finding_id"])


def downgrade() -> None:
    op.drop_index("ix_citation_feedback_finding", table_name="citation_feedback")
    op.drop_index("ix_citation_feedback_paper_created", table_name="citation_feedback")
    op.drop_table("citation_feedback")
