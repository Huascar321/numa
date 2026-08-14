from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


LedgerUUID = PostgreSQLUUID(as_uuid=True)
LedgerJSON = JSONB
LedgerMoney = Numeric(38, 18)


class CategoryGroup(Base):
    __tablename__ = "category_groups"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_category_groups_name_nonempty"),
        CheckConstraint(
            "status IN ('active', 'archived')", name="ck_category_groups_status"
        ),
        UniqueConstraint("plan_id", "id", name="uq_category_groups_plan_id_id"),
        UniqueConstraint("plan_id", "name", name="uq_category_groups_plan_name"),
        Index("ix_category_groups_plan_id", "plan_id"),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        LedgerUUID,
        ForeignKey(
            "plans.id",
            name="fk_category_groups_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_categories_name_nonempty"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_categories_status"),
        CheckConstraint(
            "NOT is_pending OR (name = 'Pendientes' AND status = 'active')",
            name="ck_categories_pending_identity",
        ),
        ForeignKeyConstraint(
            ["plan_id", "group_id"],
            ["category_groups.plan_id", "category_groups.id"],
            name="fk_categories_plan_group_same_plan",
        ),
        UniqueConstraint("plan_id", "id", name="uq_categories_plan_id_id"),
        UniqueConstraint("plan_id", "name", name="uq_categories_plan_name"),
        Index("ix_categories_plan_status", "plan_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        LedgerUUID,
        ForeignKey(
            "plans.id",
            name="fk_categories_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    group_id: Mapped[UUID | None] = mapped_column(LedgerUUID, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_tags_name_nonempty"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_tags_status"),
        UniqueConstraint("plan_id", "id", name="uq_tags_plan_id_id"),
        UniqueConstraint("plan_id", "name", name="uq_tags_plan_name"),
        Index("ix_tags_plan_status", "plan_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        LedgerUUID,
        ForeignKey(
            "plans.id",
            name="fk_tags_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "type IN ('income', 'expense', 'transfer')", name="ck_transactions_type"
        ),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        CheckConstraint(
            "btrim(source) <> ''", name="ck_transactions_source_nonempty"
        ),
        ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_transactions_plan_account_same_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id", "category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_transactions_plan_category_same_plan",
        ),
        ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_transactions_currency_code_currencies",
        ),
        UniqueConstraint("plan_id", "id", name="uq_transactions_plan_id_id"),
        Index("ix_transactions_plan_event_at", "plan_id", "event_at"),
        Index("ix_transactions_plan_category_event", "plan_id", "category_id", "event_at"),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        LedgerUUID,
        ForeignKey(
            "plans.id",
            name="fk_transactions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    type: Mapped[str] = mapped_column("type", String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(LedgerMoney, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "currencies.code",
            name="fk_transactions_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(LedgerUUID, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    location: Mapped[dict[str, Any] | None] = mapped_column(LedgerJSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "source_metadata", LedgerJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        LedgerJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class TransactionCorrection(Base):
    __tablename__ = "transaction_corrections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_transaction_corrections_plan_id_plans",
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_transaction_corrections_plan_transaction_same_plan",
        ),
        UniqueConstraint(
            "plan_id", "id", name="uq_transaction_corrections_plan_id_id"
        ),
        UniqueConstraint(
            "plan_id",
            "transaction_id",
            "correction_sequence",
            name="uq_transaction_corrections_transaction_sequence",
        ),
        UniqueConstraint(
            "plan_id",
            "id",
            "correction_sequence",
            name="uq_transaction_corrections_id_sequence",
        ),
        CheckConstraint(
            "correction_sequence > 0",
            name="ck_transaction_corrections_sequence_positive",
        ),
        Index(
            "ix_transaction_corrections_transaction",
            "plan_id",
            "transaction_id",
            "correction_sequence",
        ),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    correction_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(LedgerJSON, nullable=False)
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(LedgerJSON, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(
        LedgerJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class PostedAccountMovement(Base):
    __tablename__ = "posted_account_movements"
    __table_args__ = (
        CheckConstraint(
            "signed_amount <> 0", name="ck_posted_movements_amount_nonzero"
        ),
        CheckConstraint(
            "transaction_type IN ('income', 'expense', 'transfer')",
            name="ck_posted_movements_transaction_type",
        ),
        CheckConstraint(
            "movement_kind IN ('original', 'compensation', 'replacement')",
            name="ck_posted_movements_kind",
        ),
        CheckConstraint(
            "(movement_kind = 'original' AND correction_id IS NULL) OR "
            "(movement_kind <> 'original' AND correction_id IS NOT NULL)",
            name="ck_posted_movements_correction_link",
        ),
        CheckConstraint(
            "(movement_kind = 'original' AND correction_sequence = 0) OR "
            "(movement_kind <> 'original' AND correction_sequence > 0)",
            name="ck_posted_movements_correction_sequence",
        ),
        ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_posted_movements_plan_account_same_plan",
        ),
        UniqueConstraint(
            "plan_id",
            "correction_id",
            "movement_kind",
            name="uq_posted_movements_correction_kind",
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_posted_movements_plan_transaction_same_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id", "correction_id"],
            ["transaction_corrections.plan_id", "transaction_corrections.id"],
            name="fk_posted_movements_plan_correction_same_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id", "category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_posted_movements_plan_category_same_plan",
        ),
        ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_posted_movements_currency_code_currencies",
        ),
        Index("ix_posted_movements_account_effective", "plan_id", "account_id", "effective_at"),
        Index("ix_posted_movements_budget", "plan_id", "effective_at", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    account_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    correction_id: Mapped[UUID | None] = mapped_column(LedgerUUID, nullable=True)
    correction_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    currency_code: Mapped[str] = mapped_column(String(16), nullable=False)
    signed_amount: Mapped[Decimal] = mapped_column(LedgerMoney, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(LedgerUUID, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    location: Mapped[dict[str, Any] | None] = mapped_column(LedgerJSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        LedgerJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        LedgerJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    movement_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    source_account_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    destination_account_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    outbound_amount: Mapped[Decimal] = mapped_column(LedgerMoney, nullable=False)
    outbound_currency_code: Mapped[str] = mapped_column(String(16), nullable=False)
    inbound_amount: Mapped[Decimal] = mapped_column(LedgerMoney, nullable=False)
    inbound_currency_code: Mapped[str] = mapped_column(String(16), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(76, 38), nullable=False)
    rate_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(LedgerJSON, nullable=False)
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reverses_transfer_id: Mapped[UUID | None] = mapped_column(LedgerUUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TransferLeg(Base):
    __tablename__ = "transfer_legs"
    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    transfer_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)


class TransactionTag(Base):
    __tablename__ = "transaction_tags"
    __table_args__ = (
        CheckConstraint(
            "action IN ('attached', 'detached')", name="ck_transaction_tags_action"
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_transaction_tags_plan_transaction_same_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id", "tag_id"],
            ["tags.plan_id", "tags.id"],
            name="fk_transaction_tags_plan_tag_same_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id", "correction_id"],
            ["transaction_corrections.plan_id", "transaction_corrections.id"],
            name="fk_transaction_tags_plan_correction_same_plan",
        ),
        Index(
            "ix_transaction_tags_current_lookup",
            "plan_id",
            "transaction_id",
            "tag_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    tag_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    correction_id: Mapped[UUID | None] = mapped_column(LedgerUUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MonthlyBudgetAssignment(Base):
    __tablename__ = "monthly_budget_assignments"
    __table_args__ = (
        CheckConstraint(
            "month_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_monthly_assignments_month_key",
        ),
        CheckConstraint(
            "btrim(source) <> ''", name="ck_monthly_assignments_source_nonempty"
        ),
        ForeignKeyConstraint(
            ["plan_id", "category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_monthly_assignments_plan_category_same_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_monthly_assignments_plan_id_plans",
        ),
        ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_monthly_assignments_currency_code_currencies",
        ),
        UniqueConstraint("plan_id", "id", name="uq_monthly_assignments_plan_id_id"),
        Index("ix_monthly_assignments_plan_month", "plan_id", "month_key"),
        Index("ix_monthly_assignments_category_month", "plan_id", "category_id", "month_key"),
    )

    id: Mapped[UUID] = mapped_column(LedgerUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    category_id: Mapped[UUID] = mapped_column(LedgerUUID, nullable=False)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    amount: Mapped[Decimal] = mapped_column(LedgerMoney, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(
        LedgerJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
