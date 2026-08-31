"""Create exchange_rate_quotes table for explicit FX quotes and conversions.

Revision ID: 015_exchange_rates
Revises: 013_automation_suggestions
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "015_exchange_rates"
down_revision: str | None = "013_automation_suggestions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "exchange_rate_quotes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("base_currency", sa.String(length=16), nullable=False),
        sa.Column("quote_currency", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=False),
        sa.Column("bob_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("usdt_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("payment_method", sa.String(length=64), nullable=True),
        sa.Column(
            "fee_amount",
            sa.Numeric(18, 4),
            server_default=sa.text("0"),
            nullable=True,
        ),
        sa.Column("min_limit", sa.Numeric(18, 4), nullable=True),
        sa.Column("max_limit", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "source",
            sa.String(length=64),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column(
            "offer_context",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
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
        sa.CheckConstraint(
            "side IN ('BUY_USDT', 'SELL_USDT')",
            name="ck_exchange_rate_quotes_side",
        ),
        sa.CheckConstraint(
            "bob_amount > 0",
            name="ck_exchange_rate_quotes_bob_positive",
        ),
        sa.CheckConstraint(
            "usdt_amount > 0",
            name="ck_exchange_rate_quotes_usdt_positive",
        ),
        sa.CheckConstraint(
            "rate > 0",
            name="ck_exchange_rate_quotes_rate_positive",
        ),
        sa.CheckConstraint(
            "btrim(base_currency) <> ''",
            name="ck_exchange_rate_quotes_base_currency_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(quote_currency) <> ''",
            name="ck_exchange_rate_quotes_quote_currency_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(source) <> ''",
            name="ck_exchange_rate_quotes_source_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_exchange_rate_quotes_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["base_currency"],
            ["currencies.code"],
            name="fk_exchange_rate_quotes_base_currency_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["quote_currency"],
            ["currencies.code"],
            name="fk_exchange_rate_quotes_quote_currency_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "plan_id", "id", name="uq_exchange_rate_quotes_plan_id_id"
        ),
    )
    op.create_index(
        "ix_exchange_rate_quotes_plan_observed",
        "exchange_rate_quotes",
        ["plan_id", "observed_at"],
    )
    op.create_index(
        "ix_exchange_rate_quotes_plan_side",
        "exchange_rate_quotes",
        ["plan_id", "side"],
    )
    op.create_index(
        "ix_exchange_rate_quotes_plan_source",
        "exchange_rate_quotes",
        ["plan_id", "source"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_exchange_rate_quotes_plan_source",
        table_name="exchange_rate_quotes",
    )
    op.drop_index(
        "ix_exchange_rate_quotes_plan_side",
        table_name="exchange_rate_quotes",
    )
    op.drop_index(
        "ix_exchange_rate_quotes_plan_observed",
        table_name="exchange_rate_quotes",
    )
    op.drop_table("exchange_rate_quotes")
