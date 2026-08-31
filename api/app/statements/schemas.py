from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatementDryRunRequest(StrictRequest):
    account_id: UUID
    csv_content: str
    filename: str | None = None


class StatementCommitRequest(StrictRequest):
    account_id: UUID
    csv_content: str
    filename: str | None = None


class StatementRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID | None = None
    source_row_index: int
    event_at: datetime
    transaction_number: str
    channel: str | None = None
    description: str
    type: Literal["debit", "credit"]
    amount: str
    signed_amount: str
    running_balance: str
    compound_identity: str
    transaction_id: UUID | None = None
    match_status: str = "unmatched"
    card_suffix: str | None = None
    row_metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="row_metadata", serialization_alias="metadata"
    )

    @field_validator("amount", "signed_amount", "running_balance", mode="before")
    @classmethod
    def coerce_row_money(cls, value: Any) -> str:
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)

    @field_serializer("amount", "signed_amount", "running_balance", mode="plain", when_used="always")
    def serialize_money(self, value: Any) -> str:
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)


class StatementDryRunResponse(BaseModel):
    account_id: UUID
    currency_code: str
    opening_balance: str | None = None
    closing_balance: str | None = None
    current_balance: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    exported_at: datetime | None = None
    debit_count: int
    credit_count: int
    debit_sum: str
    credit_sum: str
    warnings: list[str]
    rows: list[StatementRowResponse]

    @field_validator(
        "opening_balance",
        "closing_balance",
        "current_balance",
        "debit_sum",
        "credit_sum",
        mode="before",
    )
    @classmethod
    def coerce_summary_money(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)

    @field_serializer(
        "opening_balance",
        "closing_balance",
        "current_balance",
        "debit_sum",
        "credit_sum",
        mode="plain",
        when_used="always",
    )
    def serialize_money(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)


class StatementImportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    plan_id: UUID
    account_id: UUID
    filename: str | None = None
    source_format: str
    status: str
    opening_balance: str | None = None
    closing_balance: str | None = None
    current_balance: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    exported_at: datetime | None = None
    debit_count: int
    credit_count: int
    debit_sum: str
    credit_sum: str
    currency_code: str
    warnings: list[str]
    import_metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="import_metadata", serialization_alias="metadata"
    )
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "opening_balance",
        "closing_balance",
        "current_balance",
        "debit_sum",
        "credit_sum",
        mode="before",
    )
    @classmethod
    def coerce_import_money(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)

    @field_serializer(
        "opening_balance",
        "closing_balance",
        "current_balance",
        "debit_sum",
        "credit_sum",
        mode="plain",
        when_used="always",
    )
    def serialize_money(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)


class StatementImportDetail(StatementImportSummary):
    rows: list[StatementRowResponse]
