from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GmailSource(Base):
    __tablename__ = "gmail_sources"
    __table_args__ = (
        UniqueConstraint("plan_id", "email", name="uq_gmail_source_mailbox"),
        CheckConstraint(
            "status IN ('connecting', 'active', 'needs_authorization', 'disconnected')",
            name="ck_gmail_source_status",
        ),
        CheckConstraint(
            "sync_mode IN ('full', 'history')", name="ck_gmail_source_mode"
        ),
        Index("ix_gmail_source_poll", "status", "next_poll_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="connecting"
    )
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    allowed_senders: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    history_id: Mapped[str | None] = mapped_column(String(128))
    full_sync_history_id: Mapped[str | None] = mapped_column(String(128))
    page_token: Mapped[str | None] = mapped_column(Text)
    sync_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="full")
    pending_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )


class GmailOAuthState(Base):
    __tablename__ = "gmail_oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("gmail_sources.id", ondelete="RESTRICT"), nullable=False
    )
    browser_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GmailMessage(Base):
    __tablename__ = "gmail_messages"
    __table_args__ = (
        UniqueConstraint("source_id", "gmail_id", name="uq_gmail_message_identity"),
        CheckConstraint(
            "status IN ('decoded', 'review', 'unavailable')",
            name="ck_gmail_message_status",
        ),
        Index("ix_gmail_message_source_order", "source_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("gmail_sources.id", ondelete="RESTRICT"), nullable=False
    )
    gmail_id: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_mime: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Includes the original Gmail raw envelope, even when its base64 is malformed.
    provider_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decoded: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
