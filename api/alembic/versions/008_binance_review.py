"""Add immutable review-only Binance Card parsing records; no financial changes."""

from alembic import op
import sqlalchemy as sa

revision = "008_binance_review"
down_revision = "007a_gmail_filter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "binance_card_reviews",
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("gmail_messages.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("reported_amount", sa.Text()),
        sa.Column("reported_currency", sa.String(3)),
        sa.Column("merchant", sa.Text()),
        sa.Column("event_at", sa.DateTime(timezone=True)),
        sa.Column("notification_at", sa.DateTime(timezone=True)),
        sa.Column("header_message_id", sa.Text()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("disposition IN ('candidate', 'needs_review', 'ignored')", name="ck_binance_review_disposition"),
        sa.CheckConstraint(r"""
            (disposition = 'candidate' AND reported_amount IS NOT NULL
             AND reported_amount ~ '^[0-9]{1,38}\.[0-9]{1,2}$'
             AND reported_amount::numeric > 0 AND reported_currency IS NOT NULL AND reported_currency = 'USD'
             AND merchant IS NOT NULL AND length(merchant) BETWEEN 1 AND 512
             AND event_at IS NOT NULL AND notification_at IS NOT NULL AND notification_at >= event_at)
            OR (disposition != 'candidate' AND reported_amount IS NULL
             AND reported_currency IS NULL AND merchant IS NULL
             AND event_at IS NULL AND notification_at IS NULL)
        """, name="ck_binance_review_facts"),
    )
    op.execute("""
        CREATE FUNCTION binance_review_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Binance review evidence is immutable'; END $$;
        CREATE TRIGGER binance_review_immutable BEFORE UPDATE OR DELETE ON binance_card_reviews
        FOR EACH ROW EXECUTE FUNCTION binance_review_immutable();
    """)


def downgrade() -> None:
    op.drop_table("binance_card_reviews")
    op.execute("DROP FUNCTION binance_review_immutable()")
