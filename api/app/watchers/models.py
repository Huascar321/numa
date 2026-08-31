from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


WatcherUUID = PostgreSQLUUID(as_uuid=True)
WatcherJSON = JSONB
WatcherMoney = Numeric(38, 18)


class WatcherSource(Base):
    __tablename__ = "watcher_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('gmail')",
            name="ck_watcher_sources_source_type",
        ),
        CheckConstraint(
            "status IN ('active', 'error', 'disconnected')",
            name="ck_watcher_sources_status",
        ),
        CheckConstraint(
            "btrim(email_address) <> ''",
            name="ck_watcher_sources_email_address_nonempty",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_sources_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("plan_id", "id", name="uq_watcher_sources_plan_id_id"),
        UniqueConstraint(
            "plan_id",
            "source_type",
            "email_address",
            name="uq_watcher_sources_plan_type_email",
        ),
        Index("ix_watcher_sources_plan_status", "plan_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(WatcherUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class WatcherRawMessage(Base):
    __tablename__ = "watcher_raw_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'parsed', 'quarantined', 'ignored', 'error')",
            name="ck_watcher_raw_messages_status",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_raw_messages_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_id"],
            ["watcher_sources.id"],
            name="fk_watcher_raw_messages_source_id_watcher_sources",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "source_id"],
            ["watcher_sources.plan_id", "watcher_sources.id"],
            name="fk_watcher_raw_messages_plan_source_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_id",
            "external_message_id",
            name="uq_watcher_raw_messages_source_external_id",
        ),
        UniqueConstraint(
            "plan_id",
            "id",
            name="uq_watcher_raw_messages_plan_id_id",
        ),
        Index("ix_watcher_raw_messages_plan_source", "plan_id", "source_id", "created_at"),
        Index("ix_watcher_raw_messages_plan_status", "plan_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(WatcherUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    source_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    internal_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_headers: Mapped[dict[str, Any]] = mapped_column(
        WatcherJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    body_plain: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_metadata: Mapped[dict[str, Any]] = mapped_column(
        WatcherJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        WatcherJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class WatcherAccountMapping(Base):
    __tablename__ = "watcher_account_mappings"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('binance_card', 'banco_ganadero', 'bcp_qr')",
            name="ck_watcher_account_mappings_source_type",
        ),
        CheckConstraint(
            "btrim(pattern) <> ''",
            name="ck_watcher_account_mappings_pattern_nonempty",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_account_mappings_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_watcher_account_mappings_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "default_category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_watcher_account_mappings_plan_category_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("plan_id", "id", name="uq_watcher_account_mappings_plan_id_id"),
        UniqueConstraint(
            "plan_id",
            "source_type",
            "pattern",
            name="uq_watcher_account_mappings_plan_source_pattern",
        ),
        Index("ix_watcher_account_mappings_plan_source", "plan_id", "source_type"),
    )

    id: Mapped[UUID] = mapped_column(WatcherUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    default_category_id: Mapped[UUID | None] = mapped_column(WatcherUUID, nullable=True)
    auto_resolve: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class WatcherCandidate(Base):
    __tablename__ = "watcher_candidates"
    __table_args__ = (
        CheckConstraint(
            "candidate_type IN ('binance_card', 'banco_ganadero', 'bcp_qr')",
            name="ck_watcher_candidates_candidate_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'resolved', 'quarantined', 'ignored', 'rejected')",
            name="ck_watcher_candidates_status",
        ),
        CheckConstraint(
            "reported_amount > 0",
            name="ck_watcher_candidates_reported_amount_positive",
        ),
        CheckConstraint(
            "settlement_amount IS NULL OR settlement_amount > 0",
            name="ck_watcher_candidates_settlement_amount_positive",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_watcher_candidates_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_id"],
            ["watcher_sources.id"],
            name="fk_watcher_candidates_source_id_watcher_sources",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "source_id"],
            ["watcher_sources.plan_id", "watcher_sources.id"],
            name="fk_watcher_candidates_plan_source_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["raw_message_id"],
            ["watcher_raw_messages.id"],
            name="fk_watcher_candidates_raw_message_id_watcher_raw_messages",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "raw_message_id"],
            ["watcher_raw_messages.plan_id", "watcher_raw_messages.id"],
            name="fk_watcher_candidates_plan_raw_message_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_watcher_candidates_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        UniqueConstraint("plan_id", "id", name="uq_watcher_candidates_plan_id_id"),
        UniqueConstraint("raw_message_id", name="uq_watcher_candidates_raw_message_id"),
        Index("ix_watcher_candidates_plan_status", "plan_id", "status"),
        Index("ix_watcher_candidates_plan_type", "plan_id", "candidate_type"),
        Index("ix_watcher_candidates_plan_event_at", "plan_id", "event_at"),
    )

    id: Mapped[UUID] = mapped_column(WatcherUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    raw_message_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    source_id: Mapped[UUID] = mapped_column(WatcherUUID, nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'")
    )
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reported_amount: Mapped[Decimal] = mapped_column(WatcherMoney, nullable=False)
    reported_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    settlement_amount: Mapped[Decimal | None] = mapped_column(
        WatcherMoney, nullable=True
    )
    settlement_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    provider_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_id_header: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        WatcherJSON, nullable=False, server_default=text("'[]'::jsonb")
    )
    glosa: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_glosa: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_suffix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        WatcherJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        WatcherJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    transaction_id: Mapped[UUID | None] = mapped_column(WatcherUUID, nullable=True)
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
