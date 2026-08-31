"""Add deterministic rules engine and support for Banco Ganadero and BCP QR notice candidates.

Revision ID: 009_watchers_rules
Revises: 008_binance_card_watcher
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "009_watchers_rules"
down_revision: str | None = "008_binance_card_watcher"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "stage",
            sa.String(length=32),
            server_default=sa.text("'watcher_candidate'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("100"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "predicate",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "action",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
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
        sa.CheckConstraint("btrim(name) <> ''", name="ck_rules_name_nonempty"),
        sa.CheckConstraint(
            "stage IN ('watcher_candidate', 'transaction_normalize')",
            name="ck_rules_stage",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_rules_priority_nonnegative"),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_rules_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_rules_plan_id_id"),
    )
    op.create_index(
        "ix_rules_plan_stage_priority",
        "rules",
        ["plan_id", "stage", "priority"],
    )

    op.add_column(
        "watcher_candidates",
        sa.Column(
            "rule_evidence",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "watcher_candidates",
        sa.Column("glosa", sa.Text(), nullable=True),
    )
    op.add_column(
        "watcher_candidates",
        sa.Column("raw_glosa", sa.Text(), nullable=True),
    )
    op.add_column(
        "watcher_candidates",
        sa.Column("qr_subtype", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "watcher_candidates",
        sa.Column("account_suffix", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "watcher_candidates",
        sa.Column("direction", sa.String(length=16), nullable=True),
    )

    op.alter_column(
        "watcher_candidates",
        "event_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )

    op.drop_constraint(
        "ck_watcher_candidates_candidate_type",
        "watcher_candidates",
        type_="check",
    )
    op.create_check_constraint(
        "ck_watcher_candidates_candidate_type",
        "watcher_candidates",
        "candidate_type IN ('binance_card', 'banco_ganadero', 'bcp_qr')",
    )

    op.drop_constraint(
        "ck_watcher_account_mappings_source_type",
        "watcher_account_mappings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_watcher_account_mappings_source_type",
        "watcher_account_mappings",
        "source_type IN ('binance_card', 'banco_ganadero', 'bcp_qr')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_watcher_account_mappings_source_type",
        "watcher_account_mappings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_watcher_account_mappings_source_type",
        "watcher_account_mappings",
        "source_type IN ('binance_card')",
    )

    op.drop_constraint(
        "ck_watcher_candidates_candidate_type",
        "watcher_candidates",
        type_="check",
    )
    op.create_check_constraint(
        "ck_watcher_candidates_candidate_type",
        "watcher_candidates",
        "candidate_type IN ('binance_card')",
    )

    op.alter_column(
        "watcher_candidates",
        "event_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    op.drop_column("watcher_candidates", "direction")
    op.drop_column("watcher_candidates", "account_suffix")
    op.drop_column("watcher_candidates", "qr_subtype")
    op.drop_column("watcher_candidates", "raw_glosa")
    op.drop_column("watcher_candidates", "glosa")
    op.drop_column("watcher_candidates", "rule_evidence")

    op.drop_index("ix_rules_plan_stage_priority", table_name="rules")
    op.drop_table("rules")
