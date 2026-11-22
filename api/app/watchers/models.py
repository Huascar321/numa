from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WatcherRun(Base):
    __tablename__ = "watcher_runs"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_watcher_run_revision"),
        CheckConstraint("status IN ('review_only', 'quarantined')", name="ck_watcher_run_status"),
        CheckConstraint("replayed_from IS NULL OR replayed_from < revision", name="ck_watcher_run_replay_order"),
        ForeignKeyConstraint(["message_id", "replayed_from"], ["watcher_runs.message_id", "watcher_runs.revision"], ondelete="RESTRICT"),
        Index("uq_watcher_run_initial_contract", "message_id", "engine_version", "parser_version", "ruleset_hash", unique=True, postgresql_where=text("replayed_from IS NULL")),
    )

    message_id: Mapped[int] = mapped_column(ForeignKey("gmail_messages.id", ondelete="RESTRICT"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    replayed_from: Mapped[int | None] = mapped_column(Integer)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
