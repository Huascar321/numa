from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


RuleUUID = PostgreSQLUUID(as_uuid=True)
RuleJSON = JSONB


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_rules_name_nonempty"),
        CheckConstraint(
            "stage IN ('watcher_candidate', 'transaction_normalize')",
            name="ck_rules_stage",
        ),
        CheckConstraint("priority >= 0", name="ck_rules_priority_nonnegative"),
        ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_rules_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("plan_id", "id", name="uq_rules_plan_id_id"),
        Index("ix_rules_plan_stage_priority", "plan_id", "stage", "priority"),
    )

    id: Mapped[UUID] = mapped_column(RuleUUID, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(RuleUUID, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'watcher_candidate'")
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("100")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    predicate: Mapped[dict[str, Any]] = mapped_column(
        RuleJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    action: Mapped[dict[str, Any]] = mapped_column(
        RuleJSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    creation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
