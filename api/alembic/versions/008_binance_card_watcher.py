"""Add watcher candidates and account mappings for Binance Card integration.

Revision ID: 008_binance_card_watcher
Revises: 007_gmail
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008_binance_card_watcher"
down_revision: str | None = "007_gmail"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "watcher_account_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("pattern", sa.String(length=255), nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("default_category_id", UUID, nullable=True),
        sa.Column(
            "auto_resolve",
            sa.Boolean(),
            server_default=sa.text("false"),
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
            "source_type IN ('binance_card')",
            name="ck_watcher_account_mappings_source_type",
        ),
        sa.CheckConstraint(
            "btrim(pattern) <> ''",
            name="ck_watcher_account_mappings_pattern_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_account_mappings_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_watcher_account_mappings_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "default_category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_watcher_account_mappings_plan_category_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_watcher_account_mappings_plan_id_id"),
        sa.UniqueConstraint(
            "plan_id",
            "source_type",
            "pattern",
            name="uq_watcher_account_mappings_plan_source_pattern",
        ),
    )
    op.create_index(
        "ix_watcher_account_mappings_plan_source",
        "watcher_account_mappings",
        ["plan_id", "source_type"],
    )

    op.create_table(
        "watcher_candidates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("raw_message_id", UUID, nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("candidate_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_amount", MONEY, nullable=False),
        sa.Column("reported_currency", sa.String(length=16), nullable=False),
        sa.Column("settlement_amount", MONEY, nullable=True),
        sa.Column("settlement_currency", sa.String(length=16), nullable=True),
        sa.Column("merchant", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("provider_uuid", sa.String(length=255), nullable=True),
        sa.Column("message_id_header", sa.String(length=255), nullable=True),
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
        sa.Column(
            "raw_payload",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "provenance",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("transaction_id", UUID, nullable=True),
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
            "candidate_type IN ('binance_card')",
            name="ck_watcher_candidates_candidate_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'resolved', 'quarantined', 'ignored', 'rejected')",
            name="ck_watcher_candidates_status",
        ),
        sa.CheckConstraint("reported_amount > 0", name="ck_watcher_candidates_reported_amount_positive"),
        sa.CheckConstraint(
            "settlement_amount IS NULL OR settlement_amount > 0",
            name="ck_watcher_candidates_settlement_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_candidates_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["watcher_sources.id"],
            name="fk_watcher_candidates_source_id_watcher_sources",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "source_id"],
            ["watcher_sources.plan_id", "watcher_sources.id"],
            name="fk_watcher_candidates_plan_source_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_message_id"],
            ["watcher_raw_messages.id"],
            name="fk_watcher_candidates_raw_message_id_watcher_raw_messages",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "raw_message_id"],
            ["watcher_raw_messages.plan_id", "watcher_raw_messages.id"],
            name="fk_watcher_candidates_plan_raw_message_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_watcher_candidates_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_watcher_candidates_plan_id_id"),
        sa.UniqueConstraint("raw_message_id", name="uq_watcher_candidates_raw_message_id"),
    )
    op.create_index(
        "ix_watcher_candidates_plan_status",
        "watcher_candidates",
        ["plan_id", "status"],
    )
    op.create_index(
        "ix_watcher_candidates_plan_type",
        "watcher_candidates",
        ["plan_id", "candidate_type"],
    )
    op.create_index(
        "ix_watcher_candidates_plan_event_at",
        "watcher_candidates",
        ["plan_id", "event_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_watcher_candidates_plan_event_at", table_name="watcher_candidates")
    op.drop_index("ix_watcher_candidates_plan_type", table_name="watcher_candidates")
    op.drop_index("ix_watcher_candidates_plan_status", table_name="watcher_candidates")
    op.drop_table("watcher_candidates")

    op.drop_index("ix_watcher_account_mappings_plan_source", table_name="watcher_account_mappings")
    op.drop_table("watcher_account_mappings")
