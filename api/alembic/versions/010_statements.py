"""Add statement imports and statement rows for bank statement ingestion.

Revision ID: 010_statements
Revises: 009_watchers_rules
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010_statements"
down_revision: str | None = "009_watchers_rules"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "statement_imports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column(
            "source_format",
            sa.String(length=32),
            server_default=sa.text("'banco_ganadero_csv'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'preview'"),
            nullable=False,
        ),
        sa.Column("opening_balance", MONEY, nullable=True),
        sa.Column("closing_balance", MONEY, nullable=True),
        sa.Column("current_balance", MONEY, nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("debit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("credit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("debit_sum", MONEY, server_default=sa.text("0"), nullable=False),
        sa.Column("credit_sum", MONEY, server_default=sa.text("0"), nullable=False),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column("warnings", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('preview', 'committed')",
            name="ck_statement_imports_status",
        ),
        sa.CheckConstraint(
            "source_format IN ('banco_ganadero_csv')",
            name="ck_statement_imports_source_format",
        ),
        sa.CheckConstraint(
            "debit_count >= 0 AND credit_count >= 0",
            name="ck_statement_imports_counts_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_statement_imports_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_statement_imports_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_statement_imports_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_statement_imports_plan_id_id"),
    )
    op.create_index(
        "ix_statement_imports_plan_account",
        "statement_imports",
        ["plan_id", "account_id", "created_at"],
    )
    op.create_index(
        "ix_statement_imports_plan_status",
        "statement_imports",
        ["plan_id", "status"],
    )

    op.create_table(
        "statement_rows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("import_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("source_row_index", sa.Integer(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_number", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("signed_amount", MONEY, nullable=False),
        sa.Column("running_balance", MONEY, nullable=False),
        sa.Column("compound_identity", sa.String(length=128), nullable=False),
        sa.Column("transaction_id", UUID, nullable=True),
        sa.Column(
            "match_status",
            sa.String(length=32),
            server_default=sa.text("'unmatched'"),
            nullable=False,
        ),
        sa.Column("card_suffix", sa.String(length=16), nullable=True),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('debit', 'credit')",
            name="ck_statement_rows_type",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_statement_rows_amount_positive",
        ),
        sa.CheckConstraint(
            "source_row_index >= 0",
            name="ck_statement_rows_source_row_index_nonnegative",
        ),
        sa.CheckConstraint(
            "match_status IN ('unmatched', 'matched', 'created', 'duplicate')",
            name="ck_statement_rows_match_status",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_statement_rows_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "import_id"],
            ["statement_imports.plan_id", "statement_imports.id"],
            name="fk_statement_rows_plan_import_same_plan",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_statement_rows_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_statement_rows_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("import_id", "source_row_index", name="uq_statement_rows_import_row_index"),
        sa.UniqueConstraint("plan_id", "id", name="uq_statement_rows_plan_id_id"),
    )
    op.create_index(
        "ix_statement_rows_plan_import",
        "statement_rows",
        ["plan_id", "import_id", "source_row_index"],
    )
    op.create_index(
        "ix_statement_rows_plan_compound",
        "statement_rows",
        ["plan_id", "account_id", "compound_identity"],
    )


def downgrade() -> None:
    op.drop_index("ix_statement_rows_plan_compound", table_name="statement_rows")
    op.drop_index("ix_statement_rows_plan_import", table_name="statement_rows")
    op.drop_table("statement_rows")

    op.drop_index("ix_statement_imports_plan_status", table_name="statement_imports")
    op.drop_index("ix_statement_imports_plan_account", table_name="statement_imports")
    op.drop_table("statement_imports")
