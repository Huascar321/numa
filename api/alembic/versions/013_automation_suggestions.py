"""Add automation_rule_suggestions table for discoverable reviewable automation rules.

Revision ID: 013_automation_suggestions
Revises: 012_ai
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "013_automation_suggestions"
down_revision: str | None = "012_ai"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "automation_rule_suggestions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("suggestion_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'suggested'"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "rule_stage",
            sa.String(length=32),
            server_default=sa.text("'watcher_candidate'"),
            nullable=False,
        ),
        sa.Column(
            "suggested_priority",
            sa.Integer(),
            server_default=sa.text("100"),
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
            "evidence",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'pattern_detector'"),
            nullable=False,
        ),
        sa.Column("created_rule_id", UUID, nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            "btrim(title) <> ''",
            name="ck_automation_rule_suggestions_title_nonempty",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'dismissed')",
            name="ck_automation_rule_suggestions_status",
        ),
        sa.CheckConstraint(
            "rule_stage IN ('watcher_candidate', 'transaction_normalize')",
            name="ck_automation_rule_suggestions_stage",
        ),
        sa.CheckConstraint(
            "suggested_priority >= 0",
            name="ck_automation_rule_suggestions_priority_nonnegative",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_automation_rule_suggestions_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_automation_rule_suggestions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "created_rule_id"],
            ["rules.plan_id", "rules.id"],
            name="fk_automation_rule_suggestions_plan_rule",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "plan_id", "id", name="uq_automation_rule_suggestions_plan_id_id"
        ),
    )
    op.create_index(
        "ix_automation_rule_suggestions_plan_status",
        "automation_rule_suggestions",
        ["plan_id", "status"],
    )
    op.create_index(
        "ix_automation_rule_suggestions_plan_source",
        "automation_rule_suggestions",
        ["plan_id", "source"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_rule_suggestions_plan_source",
        table_name="automation_rule_suggestions",
    )
    op.drop_index(
        "ix_automation_rule_suggestions_plan_status",
        table_name="automation_rule_suggestions",
    )
    op.drop_table("automation_rule_suggestions")
