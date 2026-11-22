"""Persist explicit Gmail sender scope and fence legacy unscoped connections."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "007a_gmail_filter"
down_revision = "007_gmail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gmail_sources",
        sa.Column("allowed_senders", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.execute("""
        UPDATE gmail_sources
        SET status = 'needs_authorization', pending_job_id = NULL,
            next_poll_at = NULL, last_error = 'ingestion_filter_required'
        WHERE status = 'active'
    """)


def downgrade() -> None:
    # Do not reactivate legacy jobs or restore unrestricted ingestion.
    op.drop_column("gmail_sources", "allowed_senders")
