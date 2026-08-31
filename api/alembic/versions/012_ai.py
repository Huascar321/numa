"""Add ai_configurations and ai_suggestions tables for optional bounded AI assistance.

Revision ID: 012_ai
Revises: 011_matching
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012_ai"
down_revision: str | None = "011_matching"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "ai_configurations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column(
            "provider",
            sa.String(length=32),
            server_default=sa.text("'openrouter'"),
            nullable=False,
        ),
        sa.Column(
            "model",
            sa.String(length=128),
            server_default=sa.text("'openai/gpt-4o-mini'"),
            nullable=False,
        ),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column(
            "settings",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
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
            "provider IN ('openrouter', 'groq', 'custom')",
            name="ck_ai_configurations_provider",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_ai_configurations_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_ai_configurations_plan_id_id"),
        sa.UniqueConstraint("plan_id", name="uq_ai_configurations_plan_id"),
    )
    op.create_index(
        "ix_ai_configurations_plan_id",
        "ai_configurations",
        ["plan_id"],
    )

    op.create_table(
        "ai_suggestions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("candidate_id", UUID, nullable=True),
        sa.Column("transaction_id", UUID, nullable=True),
        sa.Column("suggestion_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'suggested'"),
            nullable=False,
        ),
        sa.Column("suggested_category_id", UUID, nullable=True),
        sa.Column("suggested_merchant", sa.String(length=255), nullable=True),
        sa.Column("suggested_glosa", sa.String(length=512), nullable=True),
        sa.Column(
            "suggested_tags",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("raw_prompt", sa.Text(), nullable=True),
        sa.Column("raw_response", JSONB, nullable=True),
        sa.Column("validation_errors", JSONB, nullable=True),
        sa.Column(
            "provenance",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
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
            "suggestion_type IN ('categorization', 'merchant_normalization', 'glosa_interpretation', 'automation')",
            name="ck_ai_suggestions_type",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'quarantined')",
            name="ck_ai_suggestions_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_ai_suggestions_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_ai_suggestions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "candidate_id"],
            ["watcher_candidates.plan_id", "watcher_candidates.id"],
            name="fk_ai_suggestions_plan_candidate",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_ai_suggestions_plan_transaction",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "suggested_category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_ai_suggestions_plan_category",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_ai_suggestions_plan_id_id"),
    )
    op.create_index(
        "ix_ai_suggestions_plan_status",
        "ai_suggestions",
        ["plan_id", "status"],
    )
    op.create_index(
        "ix_ai_suggestions_plan_candidate",
        "ai_suggestions",
        ["plan_id", "candidate_id"],
    )
    op.create_index(
        "ix_ai_suggestions_plan_transaction",
        "ai_suggestions",
        ["plan_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_suggestions_plan_transaction", table_name="ai_suggestions")
    op.drop_index("ix_ai_suggestions_plan_candidate", table_name="ai_suggestions")
    op.drop_index("ix_ai_suggestions_plan_status", table_name="ai_suggestions")
    op.drop_table("ai_suggestions")
    op.drop_index("ix_ai_configurations_plan_id", table_name="ai_configurations")
    op.drop_table("ai_configurations")
