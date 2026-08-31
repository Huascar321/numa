from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AIProvider = Literal["openrouter", "groq", "custom"]
AISuggestionType = Literal[
    "categorization",
    "merchant_normalization",
    "glosa_interpretation",
    "automation",
]
AISuggestionStatus = Literal["suggested", "accepted", "rejected", "quarantined"]


class AIConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AIProvider | None = None
    model: str | None = None
    api_key: str | None = None
    clear_api_key: bool | None = None
    is_enabled: bool | None = None
    base_url: str | None = None
    settings: dict[str, Any] | None = None


class AIConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    provider: str
    model: str
    has_api_key: bool
    masked_api_key: str | None = None
    is_enabled: bool
    base_url: str | None = None
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AIModelOption(BaseModel):
    id: str
    name: str
    provider: str
    recommended: bool = False
    description: str | None = None


class AISuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    candidate_id: UUID | None = None
    transaction_id: UUID | None = None
    suggestion_type: str
    status: str
    suggested_category_id: UUID | None = None
    suggested_merchant: str | None = None
    suggested_glosa: str | None = None
    suggested_tags: list[str] = Field(default_factory=list)
    confidence: Decimal | None = None
    reasoning: str | None = None
    validation_errors: dict[str, Any] | list[Any] | None = None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class StructuredLLMSuggestion(BaseModel):
    category_id: str | None = None
    merchant: str | None = None
    glosa: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    reasoning: str = ""


class AISuggestionActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
