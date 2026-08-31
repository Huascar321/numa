"""Add transaction_matches table for deterministic deduplication and enrichment.

Revision ID: 011_matching
Revises: 010_statements
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "011_matching"
down_revision: str | None = "010_statements"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "transaction_matches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("candidate_id", UUID, nullable=True),
        sa.Column("statement_row_id", UUID, nullable=True),
        sa.Column("transaction_id", UUID, nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'suggested'"),
            nullable=False,
        ),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("signals", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
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
            "classification IN ('EXACT_MATCH', 'HIGH_CONFIDENCE_MATCH', 'POSSIBLE_MATCH', 'NEW_TRANSACTION')",
            name="ck_transaction_matches_classification",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'unlinked')",
            name="ck_transaction_matches_status",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_transaction_matches_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_transaction_matches_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "candidate_id"],
            ["watcher_candidates.plan_id", "watcher_candidates.id"],
            name="fk_transaction_matches_plan_candidate",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "statement_row_id"],
            ["statement_rows.plan_id", "statement_rows.id"],
            name="fk_transaction_matches_plan_statement_row",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_transaction_matches_plan_transaction",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_transaction_matches_plan_id_id"),
    )
    op.create_index(
        "ix_transaction_matches_plan_status",
        "transaction_matches",
        ["plan_id", "status"],
    )
    op.create_index(
        "ix_transaction_matches_plan_classification",
        "transaction_matches",
        ["plan_id", "classification"],
    )
    op.create_index(
        "ix_transaction_matches_plan_candidate",
        "transaction_matches",
        ["plan_id", "candidate_id"],
    )
    op.create_index(
        "ix_transaction_matches_plan_statement_row",
        "transaction_matches",
        ["plan_id", "statement_row_id"],
    )
    op.create_index(
        "ix_transaction_matches_plan_transaction",
        "transaction_matches",
        ["plan_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_matches_plan_transaction", table_name="transaction_matches")
    op.drop_index("ix_transaction_matches_plan_statement_row", table_name="transaction_matches")
    op.drop_index("ix_transaction_matches_plan_candidate", table_name="transaction_matches")
    op.drop_index("ix_transaction_matches_plan_classification", table_name="transaction_matches")
    op.drop_index("ix_transaction_matches_plan_status", table_name="transaction_matches")
    op.drop_table("transaction_matches")
