from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


StatementUUID = PostgreSQLUUID(as_uuid=True)
StatementJSON = JSONB
StatementMoney = Numeric(38, 18)


class StatementImport(Base):
    __tablename__ = "statement_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('preview', 'committed')",
            name="ck_statement_imports_status",
        ),
        CheckConstraint(
            "source_format IN ('banco_ganadero_csv')",
            name="ck_statement_imports_source_format",
        ),
        CheckConstraint(
            "debit_count >= 0 AND credit_count >= 0",
            name="ck_statement_imports_counts_nonnegative",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_statement_imports_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_statement_imports_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_statement_imports_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("plan_id", "id", name="uq_statement_imports_plan_id_id"),
        Index("ix_statement_imports_plan_account", "plan_id", "account_id", "created_at"),
        Index("ix_statement_imports_plan_status", "plan_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(StatementUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(StatementUUID, nullable=False)
    account_id: Mapped[UUID] = mapped_column(StatementUUID, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_format: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'banco_ganadero_csv'")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'preview'")
    )
    opening_balance: Mapped[Decimal | None] = mapped_column(StatementMoney, nullable=True)
    closing_balance: Mapped[Decimal | None] = mapped_column(StatementMoney, nullable=True)
    current_balance: Mapped[Decimal | None] = mapped_column(StatementMoney, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    debit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    credit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    debit_sum: Mapped[Decimal] = mapped_column(
        StatementMoney, nullable=False, default=Decimal("0"), server_default=text("0")
    )
    credit_sum: Mapped[Decimal] = mapped_column(
        StatementMoney, nullable=False, default=Decimal("0"), server_default=text("0")
    )
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "currencies.code",
            name="fk_statement_imports_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    warnings: Mapped[list[str]] = mapped_column(
        StatementJSON, nullable=False, server_default=text("'[]'::jsonb")
    )
    import_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", StatementJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    rows: Mapped[list[StatementRow]] = relationship(
        "StatementRow",
        back_populates="statement_import",
        cascade="all, delete-orphan",
        order_by="StatementRow.source_row_index",
    )


class StatementRow(Base):
    __tablename__ = "statement_rows"
    __table_args__ = (
        CheckConstraint(
            "type IN ('debit', 'credit')",
            name="ck_statement_rows_type",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_statement_rows_amount_positive",
        ),
        CheckConstraint(
            "source_row_index >= 0",
            name="ck_statement_rows_source_row_index_nonnegative",
        ),
        CheckConstraint(
            "match_status IN ('unmatched', 'matched', 'created', 'duplicate')",
            name="ck_statement_rows_match_status",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_statement_rows_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "import_id"],
            ["statement_imports.plan_id", "statement_imports.id"],
            name="fk_statement_rows_plan_import_same_plan",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_statement_rows_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_statement_rows_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        UniqueConstraint(
            "import_id", "source_row_index", name="uq_statement_rows_import_row_index"
        ),
        UniqueConstraint("plan_id", "id", name="uq_statement_rows_plan_id_id"),
        Index("ix_statement_rows_plan_import", "plan_id", "import_id", "source_row_index"),
        Index("ix_statement_rows_plan_compound", "plan_id", "account_id", "compound_identity"),
    )

    id: Mapped[UUID] = mapped_column(StatementUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(StatementUUID, nullable=False)
    import_id: Mapped[UUID] = mapped_column(StatementUUID, nullable=False)
    account_id: Mapped[UUID] = mapped_column(StatementUUID, nullable=False)
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_number: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(StatementMoney, nullable=False)
    signed_amount: Mapped[Decimal] = mapped_column(StatementMoney, nullable=False)
    running_balance: Mapped[Decimal] = mapped_column(StatementMoney, nullable=False)
    compound_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_id: Mapped[UUID | None] = mapped_column(StatementUUID, nullable=True)
    match_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'unmatched'")
    )
    card_suffix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    row_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", StatementJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    statement_import: Mapped[StatementImport] = relationship(
        "StatementImport", back_populates="rows"
    )
