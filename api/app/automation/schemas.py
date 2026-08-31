from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AutomationSuggestionStatus = Literal["suggested", "accepted", "rejected", "dismissed"]


class AutomationSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    suggestion_type: str
    status: str
    title: str
    description: str | None = None
    rule_stage: str
    suggested_priority: int
    predicate: dict[str, Any]
    action: dict[str, Any]
    evidence: dict[str, Any]
    confidence: Decimal | None = None
    source: str
    created_rule_id: UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DiscoverAutomationSuggestionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    discovered_count: int
    created_count: int
    suggestions: list[AutomationSuggestionResponse]


class AutomationSuggestionAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    priority: int | None = None
    predicate: dict[str, Any] | None = None
    action: dict[str, Any] | None = None


class AutomationSuggestionRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
