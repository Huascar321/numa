from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

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


MatchingUUID = PostgreSQLUUID(as_uuid=True)
MatchingJSON = JSONB
MatchingScore = Numeric(5, 4)


class TransactionMatch(Base):
    __tablename__ = "transaction_matches"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('EXACT_MATCH', 'HIGH_CONFIDENCE_MATCH', 'POSSIBLE_MATCH', 'NEW_TRANSACTION')",
            name="ck_transaction_matches_classification",
        ),
        CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'unlinked')",
            name="ck_transaction_matches_status",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_transaction_matches_confidence",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_transaction_matches_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "candidate_id"],
            ["watcher_candidates.plan_id", "watcher_candidates.id"],
            name="fk_transaction_matches_plan_candidate",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["plan_id", "statement_row_id"],
            ["statement_rows.plan_id", "statement_rows.id"],
            name="fk_transaction_matches_plan_statement_row",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_transaction_matches_plan_transaction",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        UniqueConstraint("plan_id", "id", name="uq_transaction_matches_plan_id_id"),
        Index("ix_transaction_matches_plan_status", "plan_id", "status"),
        Index("ix_transaction_matches_plan_classification", "plan_id", "classification"),
        Index("ix_transaction_matches_plan_candidate", "plan_id", "candidate_id"),
        Index("ix_transaction_matches_plan_statement_row", "plan_id", "statement_row_id"),
        Index("ix_transaction_matches_plan_transaction", "plan_id", "transaction_id"),
    )

    id: Mapped[UUID] = mapped_column(MatchingUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(MatchingUUID, nullable=False)
    candidate_id: Mapped[UUID | None] = mapped_column(MatchingUUID, nullable=True)
    statement_row_id: Mapped[UUID | None] = mapped_column(MatchingUUID, nullable=True)
    transaction_id: Mapped[UUID | None] = mapped_column(MatchingUUID, nullable=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'suggested'")
    )
    confidence_score: Mapped[Decimal] = mapped_column(MatchingScore, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(
        MatchingJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        MatchingJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
