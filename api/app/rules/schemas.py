from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class RuleCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    stage: str = "watcher_candidate"
    priority: int = 100
    enabled: bool = True
    predicate: dict[str, Any]
    action: dict[str, Any]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Rule name cannot be empty.")
        return s

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in {"watcher_candidate", "transaction_normalize"}:
            raise ValueError(f"Invalid rule stage '{v}'.")
        return s

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Priority must be non-negative.")
        return v


class RuleUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    stage: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    predicate: dict[str, Any] | None = None
    action: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Rule name cannot be empty.")
            return s
        return v

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip().lower()
            if s not in {"watcher_candidate", "transaction_normalize"}:
                raise ValueError(f"Invalid rule stage '{v}'.")
            return s
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("Priority must be non-negative.")
        return v


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    name: str
    stage: str
    priority: int
    enabled: bool
    predicate: dict[str, Any]
    action: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class RuleEvidenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: UUID
    rule_name: str
    result: str  # "applied" | "skipped" | "conflict"
    reason: str | None = None
    applied_actions: dict[str, Any] | None = None
    conflicting_field: str | None = None
    existing_value: Any = None
    attempted_value: Any = None
    timestamp: str


class ReplayRulesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    replayed_count: int
    resolved_count: int
    quarantined_count: int
    pending_count: int
