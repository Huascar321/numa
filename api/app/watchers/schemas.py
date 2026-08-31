from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class GmailAuthUrlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    auth_url: str


class ConnectGmailRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    redirect_uri: str
    password: str | None = None

    @field_validator("password")
    @classmethod
    def reject_passwords(cls, value: str | None) -> str | None:
        if value is not None:
            raise ValueError("Password collection is strictly prohibited.")
        return value


class WatcherSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    source_type: str
    email_address: str
    status: str
    history_id: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SyncResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    synced_count: int
    new_messages_count: int
    history_id: str | None = None


class WatcherRawMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    source_id: UUID
    external_message_id: str
    external_thread_id: str | None = None
    internal_date: datetime
    history_id: str | None = None
    sender: str
    recipient: str | None = None
    subject: str
    snippet: str | None = None
    raw_headers: dict[str, Any]
    body_plain: str | None = None
    body_html: str | None = None
    mime_metadata: dict[str, Any]
    provenance: dict[str, Any]
    status: str
    created_at: datetime


class WatcherCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    raw_message_id: UUID
    source_id: UUID
    candidate_type: str
    status: str
    event_at: datetime | None = None
    notification_at: datetime | None = None
    reported_amount: Decimal
    reported_currency: str
    settlement_amount: Decimal | None = None
    settlement_currency: str | None = None
    merchant: str | None = None
    subject: str
    sender: str
    provider_uuid: str | None = None
    message_id_header: str | None = None
    quarantine_reason: str | None = None
    rule_evidence: list[dict[str, Any]] = []
    glosa: str | None = None
    raw_glosa: str | None = None
    qr_subtype: str | None = None
    account_suffix: str | None = None
    direction: str | None = None
    raw_payload: dict[str, Any]
    provenance: dict[str, Any]
    transaction_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ResolveCandidateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    category_id: UUID | None = None
    settlement_amount: Decimal | None = None
    settlement_currency: str | None = None
    memo: str | None = None
    tags: list[str] | None = None


class IgnoreCandidateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reason: str | None = None


class WatcherAccountMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    source_type: str
    pattern: str
    account_id: UUID
    default_category_id: UUID | None = None
    auto_resolve: bool = False
    created_at: datetime
    updated_at: datetime


class CreateAccountMappingRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_type: str = "binance_card"
    pattern: str = "*"
    account_id: UUID
    default_category_id: UUID | None = None
    auto_resolve: bool = False

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Pattern cannot be empty.")
        return s

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in {"binance_card", "banco_ganadero", "bcp_qr"}:
            raise ValueError(f"Unsupported source_type '{v}'.")
        return s


class ProcessCandidatesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    processed_count: int
    candidates_created: int
    candidates_resolved: int
    candidates_quarantined: int
