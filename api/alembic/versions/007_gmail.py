"""Add watcher sources and raw messages for Gmail integration.

Revision ID: 007_gmail
Revises: 006_reconciliation
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007_gmail"
down_revision: str | None = "006_reconciliation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "watcher_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("history_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
            "source_type IN ('gmail')",
            name="ck_watcher_sources_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'error', 'disconnected')",
            name="ck_watcher_sources_status",
        ),
        sa.CheckConstraint(
            "btrim(email_address) <> ''",
            name="ck_watcher_sources_email_address_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_sources_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("plan_id", "id", name="uq_watcher_sources_plan_id_id"),
        sa.UniqueConstraint(
            "plan_id",
            "source_type",
            "email_address",
            name="uq_watcher_sources_plan_type_email",
        ),
    )
    op.create_index(
        "ix_watcher_sources_plan_status",
        "watcher_sources",
        ["plan_id", "status"],
    )

    op.create_table(
        "watcher_raw_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=False),
        sa.Column("external_thread_id", sa.String(length=255), nullable=True),
        sa.Column("internal_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_id", sa.String(length=64), nullable=True),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column(
            "raw_headers",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("body_plain", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column(
            "mime_metadata",
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
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'parsed', 'quarantined', 'ignored', 'error')",
            name="ck_watcher_raw_messages_status",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_raw_messages_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["watcher_sources.id"],
            name="fk_watcher_raw_messages_source_id_watcher_sources",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "source_id"],
            ["watcher_sources.plan_id", "watcher_sources.id"],
            name="fk_watcher_raw_messages_plan_source_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_id",
            "external_message_id",
            name="uq_watcher_raw_messages_source_external_id",
        ),
        sa.UniqueConstraint(
            "plan_id",
            "id",
            name="uq_watcher_raw_messages_plan_id_id",
        ),
    )
    op.create_index(
        "ix_watcher_raw_messages_plan_source",
        "watcher_raw_messages",
        ["plan_id", "source_id", "created_at"],
    )
    op.create_index(
        "ix_watcher_raw_messages_plan_status",
        "watcher_raw_messages",
        ["plan_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_watcher_raw_messages_plan_status", table_name="watcher_raw_messages")
    op.drop_index("ix_watcher_raw_messages_plan_source", table_name="watcher_raw_messages")
    op.drop_table("watcher_raw_messages")

    op.drop_index("ix_watcher_sources_plan_status", table_name="watcher_sources")
    op.drop_table("watcher_sources")
