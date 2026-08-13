from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (
        CheckConstraint(
            "decimal_places >= 0",
            name="ck_currencies_decimal_places",
        ),
    )

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_plans_name_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reporting_currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "currencies.code",
            name="fk_plans_reporting_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    budget_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_accounts_name_nonempty"),
        CheckConstraint(
            "account_type IN "
            "('Bank', 'Cash', 'Wallet', 'Credit Card', 'Crypto', 'Other')",
            name="ck_accounts_account_type",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_accounts_status",
        ),
        Index("ix_accounts_plan_id", "plan_id"),
        Index("ix_accounts_plan_status", "plan_id", "status"),
        UniqueConstraint("plan_id", "id", name="uq_accounts_plan_id_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "plans.id",
            name="fk_accounts_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "currencies.code",
            name="fk_accounts_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
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
