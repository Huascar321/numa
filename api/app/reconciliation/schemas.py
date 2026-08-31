from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

from app.accounts.schemas import BalanceResponse


STATEMENT_BALANCE_PATTERN = r"^-?[0-9]{1,20}(?:\.[0-9]{1,18})?$"


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReconciliationPreviewRequest(StrictRequest):
    statement_balance: StrictStr = Field(
        max_length=40,
        pattern=STATEMENT_BALANCE_PATTERN,
        description=(
            "Plain decimal string in NUMERIC(38,18): optional minus sign, "
            "1-20 integer digits, and at most 18 fractional digits; exponent "
            "notation is not accepted."
        ),
    )
    currency_code: StrictStr
    statement_at: datetime

    @field_validator("statement_at", mode="before")
    @classmethod
    def require_explicit_utc_designator(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("statement_at must be a string using Z or +00:00")
        if not value.endswith(("Z", "+00:00")):
            raise ValueError("statement_at must use Z or +00:00")
        return value

    @field_validator("statement_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None:
            raise ValueError("statement_at must be a UTC timestamp")
        if offset.total_seconds() != 0:
            raise ValueError("statement_at must use the UTC offset")
        return value.astimezone(timezone.utc)


class ReconciliationConfirmRequest(ReconciliationPreviewRequest):
    warning_accepted: StrictBool = False


class ReconciliationComparisonResponse(BaseModel):
    id: UUID
    plan_id: UUID
    account_id: UUID
    statement_balance: BalanceResponse
    statement_at: datetime
    derived_balance: BalanceResponse
    discrepancy: BalanceResponse
    policy: Literal["block", "warn"]
    tolerance: BalanceResponse
    requires_warning_acceptance: bool
    blocked: bool


class ReconciliationSessionResponse(ReconciliationComparisonResponse):
    warning_accepted: bool
    confirmed_at: datetime
    adjustment_transaction_id: UUID | None
    adjustment_movement_id: UUID | None
