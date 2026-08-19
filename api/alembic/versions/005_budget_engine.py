"""Add category goal inputs for budget-engine projections.

Revision ID: 005_budget_engine
Revises: 004_transfers
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "005_budget_engine"
down_revision: str | None = "004_transfers"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("goal_type", sa.String(32), nullable=True))
    op.add_column("categories", sa.Column("goal_target", sa.Numeric(38, 18), nullable=True))
    op.add_column("categories", sa.Column("goal_due_month", sa.String(7), nullable=True))
    op.create_check_constraint(
        "ck_categories_goal",
        "categories",
        "(goal_type IS NULL AND goal_target IS NULL AND goal_due_month IS NULL) OR "
        "(goal_type IN ('target_balance', 'monthly_funding') AND goal_target > 0 AND goal_due_month IS NULL) OR "
        "(goal_type = 'due_date' AND goal_target > 0 AND goal_due_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_categories_goal", "categories", type_="check")
    op.drop_column("categories", "goal_due_month")
    op.drop_column("categories", "goal_target")
    op.drop_column("categories", "goal_type")
