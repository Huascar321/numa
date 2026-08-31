from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExchangeRateQuote(Base):
    __tablename__ = "exchange_rate_quotes"
    __table_args__ = (
        CheckConstraint(
            "side IN ('BUY_USDT', 'SELL_USDT')",
            name="ck_exchange_rate_quotes_side",
        ),
        CheckConstraint(
            "bob_amount > 0",
            name="ck_exchange_rate_quotes_bob_positive",
        ),
        CheckConstraint(
            "usdt_amount > 0",
            name="ck_exchange_rate_quotes_usdt_positive",
        ),
        CheckConstraint(
            "rate > 0",
            name="ck_exchange_rate_quotes_rate_positive",
        ),
        CheckConstraint(
            "btrim(base_currency) <> ''",
            name="ck_exchange_rate_quotes_base_currency_nonempty",
        ),
        CheckConstraint(
            "btrim(quote_currency) <> ''",
            name="ck_exchange_rate_quotes_quote_currency_nonempty",
        ),
        CheckConstraint(
            "btrim(source) <> ''",
            name="ck_exchange_rate_quotes_source_nonempty",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_exchange_rate_quotes_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["base_currency"],
            ["currencies.code"],
            name="fk_exchange_rate_quotes_base_currency_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["quote_currency"],
            ["currencies.code"],
            name="fk_exchange_rate_quotes_quote_currency_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "plan_id", "id", name="uq_exchange_rate_quotes_plan_id_id"
        ),
        Index("ix_exchange_rate_quotes_plan_observed", "plan_id", "observed_at"),
        Index("ix_exchange_rate_quotes_plan_side", "plan_id", "side"),
        Index("ix_exchange_rate_quotes_plan_source", "plan_id", "source"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(32), nullable=False)
    bob_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    usdt_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fee_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), server_default=text("0"), nullable=True
    )
    min_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    max_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    source: Mapped[str] = mapped_column(
        String(64), server_default=text("'manual'"), nullable=False
    )
    offer_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
