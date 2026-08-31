"""Add reconciliation sessions and reconciliation adjustment transaction type.

Revision ID: 006_reconciliation
Revises: 005_budget_engine
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "006_reconciliation"
down_revision: str | None = "005_budget_engine"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    op.drop_constraint("ck_transactions_type", "transactions", type_="check")
    op.drop_constraint("ck_transactions_category_by_type", "transactions", type_="check")
    op.drop_constraint("ck_posted_movements_transaction_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_category_by_type", "posted_account_movements", type_="check")

    op.create_check_constraint(
        "ck_transactions_type",
        "transactions",
        "type IN ('income', 'expense', 'transfer', 'reconciliation_adjustment')",
    )
    op.create_check_constraint(
        "ck_transactions_category_by_type",
        "transactions",
        "(type = 'transfer' AND category_id IS NULL) OR "
        "(type IN ('income', 'expense', 'reconciliation_adjustment') AND category_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_posted_movements_transaction_type",
        "posted_account_movements",
        "transaction_type IN ('income', 'expense', 'transfer', 'reconciliation_adjustment')",
    )
    op.create_check_constraint(
        "ck_posted_movements_category_by_type",
        "posted_account_movements",
        "(transaction_type = 'transfer' AND category_id IS NULL) OR "
        "(transaction_type IN ('income', 'expense', 'reconciliation_adjustment') AND category_id IS NOT NULL)",
    )

    op.create_table(
        "reconciliation_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("statement_balance", MONEY, nullable=False),
        sa.Column("statement_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derived_balance", MONEY, nullable=False),
        sa.Column("discrepancy", MONEY, nullable=False),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("adjustment_transaction_id", UUID, nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('balanced', 'adjusted')",
            name="ck_reconciliation_sessions_status",
        ),
        sa.CheckConstraint(
            "(status = 'balanced' AND adjustment_transaction_id IS NULL AND discrepancy = 0) OR "
            "(status = 'adjusted' AND adjustment_transaction_id IS NOT NULL AND discrepancy <> 0)",
            name="ck_reconciliation_sessions_adjustment",
        ),
        sa.CheckConstraint(
            "statement_balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND "
            "derived_balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND "
            "discrepancy NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_reconciliation_sessions_balances_finite",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_reconciliation_sessions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_reconciliation_sessions_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_reconciliation_sessions_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "adjustment_transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_reconciliation_sessions_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_reconciliation_sessions_plan_id_id"),
    )
    op.create_index(
        "ix_reconciliation_sessions_plan_account",
        "reconciliation_sessions",
        ["plan_id", "account_id", "statement_date"],
    )

    op.execute(
        sa.text(
            """
            CREATE TRIGGER reconciliation_sessions_append_only
              BEFORE UPDATE OR DELETE ON reconciliation_sessions FOR EACH ROW
              EXECUTE FUNCTION numa_reject_append_only_mutation();
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS reconciliation_sessions_append_only ON reconciliation_sessions;
            """
        )
    )
    op.drop_index("ix_reconciliation_sessions_plan_account", table_name="reconciliation_sessions")
    op.drop_table("reconciliation_sessions")

    op.drop_constraint("ck_posted_movements_category_by_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_transaction_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_transactions_category_by_type", "transactions", type_="check")
    op.drop_constraint("ck_transactions_type", "transactions", type_="check")

    op.create_check_constraint(
        "ck_transactions_type",
        "transactions",
        "type IN ('income', 'expense', 'transfer')",
    )
    op.create_check_constraint(
        "ck_transactions_category_by_type",
        "transactions",
        "(type = 'transfer' AND category_id IS NULL) OR (type IN ('income', 'expense') AND category_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_posted_movements_transaction_type",
        "posted_account_movements",
        "transaction_type IN ('income', 'expense', 'transfer')",
    )
    op.create_check_constraint(
        "ck_posted_movements_category_by_type",
        "posted_account_movements",
        "(transaction_type = 'transfer' AND category_id IS NULL) OR (transaction_type IN ('income', 'expense') AND category_id IS NOT NULL)",
    )
