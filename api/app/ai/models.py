from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


AIUUID = PostgreSQLUUID(as_uuid=True)
AIJSON = JSONB
AIScore = Numeric(5, 4)


class AIConfiguration(Base):
    __tablename__ = "ai_configurations"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('openrouter', 'groq', 'custom')",
            name="ck_ai_configurations_provider",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_ai_configurations_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("plan_id", "id", name="uq_ai_configurations_plan_id_id"),
        UniqueConstraint("plan_id", name="uq_ai_configurations_plan_id"),
        Index("ix_ai_configurations_plan_id", "plan_id"),
    )

    id: Mapped[UUID] = mapped_column(AIUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(AIUUID, nullable=False)
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'openrouter'")
    )
    model: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=text("'openai/gpt-4o-mini'")
    )
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(
        AIJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"
    __table_args__ = (
        CheckConstraint(
            "suggestion_type IN ('categorization', 'merchant_normalization', 'glosa_interpretation', 'automation')",
            name="ck_ai_suggestions_type",
        ),
        CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'quarantined')",
            name="ck_ai_suggestions_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_ai_suggestions_confidence",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_ai_suggestions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "candidate_id"],
            ["watcher_candidates.plan_id", "watcher_candidates.id"],
            name="fk_ai_suggestions_plan_candidate",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_ai_suggestions_plan_transaction",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["plan_id", "suggested_category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_ai_suggestions_plan_category",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        UniqueConstraint("plan_id", "id", name="uq_ai_suggestions_plan_id_id"),
        Index("ix_ai_suggestions_plan_status", "plan_id", "status"),
        Index("ix_ai_suggestions_plan_candidate", "plan_id", "candidate_id"),
        Index("ix_ai_suggestions_plan_transaction", "plan_id", "transaction_id"),
    )

    id: Mapped[UUID] = mapped_column(AIUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(AIUUID, nullable=False)
    candidate_id: Mapped[UUID | None] = mapped_column(AIUUID, nullable=True)
    transaction_id: Mapped[UUID | None] = mapped_column(AIUUID, nullable=True)
    suggestion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'suggested'")
    )
    suggested_category_id: Mapped[UUID | None] = mapped_column(AIUUID, nullable=True)
    suggested_merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_glosa: Mapped[str | None] = mapped_column(String(512), nullable=True)
    suggested_tags: Mapped[list[str]] = mapped_column(
        AIJSON, nullable=False, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[Decimal | None] = mapped_column(AIScore, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(AIJSON, nullable=True)
    validation_errors: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        AIJSON, nullable=True
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        AIJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
