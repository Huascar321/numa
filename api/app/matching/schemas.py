from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SignalDetail(BaseModel):
    score: float
    matched: bool
    details: dict[str, Any] = Field(default_factory=dict)


class CandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_type: str
    reported_amount: str
    reported_currency: str
    settlement_amount: str | None = None
    settlement_currency: str | None = None
    merchant: str | None = None
    subject: str
    glosa: str | None = None
    account_suffix: str | None = None
    direction: str | None = None
    event_at: datetime | None = None
    notification_at: datetime | None = None
    status: str


class StatementRowSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    import_id: UUID
    account_id: UUID
    source_row_index: int
    event_at: datetime
    transaction_number: str
    channel: str | None = None
    description: str
    type: str
    amount: str
    signed_amount: str
    match_status: str
    card_suffix: str | None = None


class TransactionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    type: str
    amount: str
    currency_code: str
    event_at: datetime
    category_id: UUID | None = None
    merchant: str | None = None
    memo: str | None = None
    source: str


class TransactionMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    candidate_id: UUID | None = None
    statement_row_id: UUID | None = None
    transaction_id: UUID | None = None
    classification: str
    status: str
    confidence_score: str
    signals: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    candidate: CandidateSummary | None = None
    statement_row: StatementRowSummary | None = None
    transaction: TransactionSummary | None = None


class MatchEvaluationRequest(BaseModel):
    candidate_id: UUID | None = None
    statement_row_id: UUID | None = None
    auto_link_exact: bool = False


class MatchEvaluationResponse(BaseModel):
    evaluations: list[TransactionMatchResponse]
    evaluated_candidates_count: int
    evaluated_statement_rows_count: int
    matches_created_count: int


class MatchAcceptRequest(BaseModel):
    pass


class MatchRejectRequest(BaseModel):
    reason: str | None = None


class MatchUnlinkRequest(BaseModel):
    reason: str | None = None
