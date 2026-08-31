from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ReconciliationSession(Base):
    __tablename__ = "reconciliation_sessions"
    __table_args__ = (
        CheckConstraint(
            "policy IN ('block', 'warn')", name="ck_reconciliation_sessions_policy"
        ),
        CheckConstraint(
            "tolerance >= 0", name="ck_reconciliation_sessions_tolerance_nonnegative"
        ),
        CheckConstraint(
            "statement_balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND derived_balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND discrepancy NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND tolerance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_reconciliation_sessions_amounts_finite",
        ),
        ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_reconciliation_sessions_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_reconciliation_sessions_currency",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("plan_id", "id", name="uq_reconciliation_sessions_plan_id_id"),
        Index(
            "ix_reconciliation_sessions_account_confirmed",
            "plan_id",
            "account_id",
            "confirmed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(16), nullable=False)
    statement_balance: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    statement_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    derived_balance: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    discrepancy: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    policy: Mapped[str] = mapped_column(String(16), nullable=False)
    tolerance: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    warning_accepted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
