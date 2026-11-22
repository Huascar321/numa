"""Add optional Gmail OAuth, synchronization checkpoints and raw evidence."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "007_gmail"
down_revision = "006_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_sources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.Text()),
        sa.Column("history_id", sa.String(128)),
        sa.Column("full_sync_history_id", sa.String(128)),
        sa.Column("page_token", sa.Text()),
        sa.Column("sync_mode", sa.String(16), nullable=False),
        sa.Column("pending_job_id", pg.UUID(as_uuid=True)),
        sa.Column("next_poll_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("plan_id", "email", name="uq_gmail_source_mailbox"),
        sa.CheckConstraint(
            "status IN ('connecting', 'active', 'needs_authorization', 'disconnected')",
            name="ck_gmail_source_status",
        ),
        sa.CheckConstraint(
            "sync_mode IN ('full', 'history')", name="ck_gmail_source_mode"
        ),
    )
    op.create_index("ix_gmail_source_poll", "gmail_sources", ["status", "next_poll_at"])
    op.create_table(
        "gmail_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column(
            "source_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("gmail_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "gmail_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("gmail_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("gmail_id", sa.String(128), nullable=False),
        sa.Column("raw_mime", sa.LargeBinary()),
        sa.Column("provider_metadata", pg.JSONB(), nullable=False),
        sa.Column("decoded", pg.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("source_id", "gmail_id", name="uq_gmail_message_identity"),
        sa.CheckConstraint(
            "status IN ('decoded', 'review', 'unavailable')",
            name="ck_gmail_message_status",
        ),
    )
    op.create_index(
        "ix_gmail_message_source_order", "gmail_messages", ["source_id", "id"]
    )
    op.execute("""
        CREATE FUNCTION gmail_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Gmail source evidence is immutable'; END $$;
        CREATE TRIGGER gmail_message_immutable BEFORE UPDATE OR DELETE ON gmail_messages
        FOR EACH ROW EXECUTE FUNCTION gmail_evidence_immutable();
    """)


def downgrade() -> None:
    op.drop_table("gmail_messages")
    op.execute("DROP FUNCTION gmail_evidence_immutable()")
    op.drop_table("gmail_oauth_states")
    op.drop_table("gmail_sources")
