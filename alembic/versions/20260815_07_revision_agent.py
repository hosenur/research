"""Allow history-aware manuscript operations.

Revision ID: 20260815_07
Revises: 20260815_06
Create Date: 2026-08-15
"""

from alembic import op


revision = "20260815_07"
down_revision = "20260815_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_edit_operation_type", "edit_operations", type_="check")
    op.create_check_constraint(
        "ck_edit_operation_type",
        "edit_operations",
        "operation_type IN ('replace_text', 'insert_citation', 'remove_citation', 'restore_revision')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_edit_operation_type", "edit_operations", type_="check")
    op.create_check_constraint(
        "ck_edit_operation_type",
        "edit_operations",
        "operation_type IN ('replace_text', 'insert_citation')",
    )
