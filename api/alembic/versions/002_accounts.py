"""Create currencies, plans, and accounts.

Revision ID: 002_accounts
Revises: 001_foundation
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "002_accounts"
down_revision: str | None = "001_foundation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "decimal_places >= 0",
            name="ck_currencies_decimal_places",
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.bulk_insert(
        sa.table(
            "currencies",
            sa.column("code", sa.String(length=16)),
            sa.column("decimal_places", sa.Integer()),
        ),
        [
            {"code": "BOB", "decimal_places": 2},
            {"code": "USDT", "decimal_places": 6},
        ],
    )

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "reporting_currency_code",
            sa.String(length=16),
            nullable=False,
        ),
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
        sa.CheckConstraint("btrim(name) <> ''", name="ck_plans_name_nonempty"),
        sa.ForeignKeyConstraint(
            ["reporting_currency_code"],
            ["currencies.code"],
            name="fk_plans_reporting_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
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
        sa.CheckConstraint("btrim(name) <> ''", name="ck_accounts_name_nonempty"),
        sa.CheckConstraint(
            "account_type IN "
            "('Bank', 'Cash', 'Wallet', 'Credit Card', 'Crypto', 'Other')",
            name="ck_accounts_account_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_accounts_status",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_accounts_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_accounts_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_plan_id", "accounts", ["plan_id"])
    op.create_index(
        "ix_accounts_plan_status",
        "accounts",
        ["plan_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_accounts_plan_status", table_name="accounts")
    op.drop_index("ix_accounts_plan_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("plans")
    op.drop_table("currencies")
