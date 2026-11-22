"""Preserve immutable typed watcher outcomes and explicit replay lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "009_watcher_runs"
down_revision = "008_binance_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watcher_runs",
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("gmail_messages.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("replayed_from", sa.Integer()),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("ruleset_hash", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("config_snapshot", pg.JSONB(), nullable=False),
        sa.Column("result", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("revision > 0", name="ck_watcher_run_revision"),
        sa.CheckConstraint("status IN ('review_only', 'quarantined')", name="ck_watcher_run_status"),
        sa.CheckConstraint("replayed_from IS NULL OR replayed_from < revision", name="ck_watcher_run_replay_order"),
        sa.ForeignKeyConstraint(["message_id", "replayed_from"], ["watcher_runs.message_id", "watcher_runs.revision"], ondelete="RESTRICT"),
    )
    op.create_index("uq_watcher_run_initial_contract", "watcher_runs",
                    ["message_id", "engine_version", "parser_version", "ruleset_hash"],
                    unique=True, postgresql_where=sa.text("replayed_from IS NULL"))
    op.execute("""
        CREATE FUNCTION watcher_run_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Watcher run evidence is immutable'; END $$;
        CREATE TRIGGER watcher_run_immutable BEFORE UPDATE OR DELETE ON watcher_runs
        FOR EACH ROW EXECUTE FUNCTION watcher_run_immutable();
    """)


def downgrade() -> None:
    op.drop_table("watcher_runs")
    op.execute("DROP FUNCTION watcher_run_immutable()")
