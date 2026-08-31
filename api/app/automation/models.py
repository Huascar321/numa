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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


SuggestionUUID = PostgreSQLUUID(as_uuid=True)
SuggestionJSON = JSONB
SuggestionScore = Numeric(5, 4)


class AutomationRuleSuggestion(Base):
    __tablename__ = "automation_rule_suggestions"
    __table_args__ = (
        CheckConstraint(
            "btrim(title) <> ''",
            name="ck_automation_rule_suggestions_title_nonempty",
        ),
        CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'dismissed')",
            name="ck_automation_rule_suggestions_status",
        ),
        CheckConstraint(
            "rule_stage IN ('watcher_candidate', 'transaction_normalize')",
            name="ck_automation_rule_suggestions_stage",
        ),
        CheckConstraint(
            "suggested_priority >= 0",
            name="ck_automation_rule_suggestions_priority_nonnegative",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_automation_rule_suggestions_confidence",
        ),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_automation_rule_suggestions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "created_rule_id"],
            ["rules.plan_id", "rules.id"],
            name="fk_automation_rule_suggestions_plan_rule",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        UniqueConstraint(
            "plan_id", "id", name="uq_automation_rule_suggestions_plan_id_id"
        ),
        Index("ix_automation_rule_suggestions_plan_status", "plan_id", "status"),
        Index("ix_automation_rule_suggestions_plan_source", "plan_id", "source"),
    )

    id: Mapped[UUID] = mapped_column(SuggestionUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(SuggestionUUID, nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'suggested'")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'watcher_candidate'")
    )
    suggested_priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("100")
    )
    predicate: Mapped[dict[str, Any]] = mapped_column(
        SuggestionJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    action: Mapped[dict[str, Any]] = mapped_column(
        SuggestionJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        SuggestionJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    confidence: Mapped[Decimal | None] = mapped_column(SuggestionScore, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pattern_detector'")
    )
    created_rule_id: Mapped[UUID | None] = mapped_column(SuggestionUUID, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
