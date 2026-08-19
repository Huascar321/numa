from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from app.accounts.schemas import NonEmptyName


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanTimezoneRequest(StrictRequest):
    budget_timezone: str

    @field_validator("budget_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("budget_timezone must be a valid IANA timezone") from exc
        return value


class CategoryGroupCreate(StrictRequest):
    name: NonEmptyName


class CategoryGroupPatch(StrictRequest):
    name: NonEmptyName


class CategoryGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    name: str
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime


class CategoryCreate(StrictRequest):
    name: NonEmptyName
    group_id: UUID | None = None
    goal_type: Literal["target_balance", "monthly_funding", "due_date"] | None = None
    goal_target: StrictStr | None = None
    goal_due_month: str | None = None

    @model_validator(mode="after")
    def validate_goal(self) -> "CategoryCreate":
        _validate_goal_fields(self.goal_type, self.goal_target, self.goal_due_month)
        return self


class CategoryPatch(StrictRequest):
    name: NonEmptyName | None = None
    group_id: UUID | None = None
    goal_type: Literal["target_balance", "monthly_funding", "due_date"] | None = None
    goal_target: StrictStr | None = None
    goal_due_month: str | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> "CategoryPatch":
        if not self.model_fields_set:
            raise ValueError("category patch must change name, group_id, or goal")
        goal_fields = {"goal_type", "goal_target", "goal_due_month"}
        if self.model_fields_set & goal_fields:
            _validate_goal_fields(self.goal_type, self.goal_target, self.goal_due_month)
        return self


def _validate_goal_fields(goal_type: str | None, goal_target: str | None, goal_due_month: str | None) -> None:
    if goal_type is None:
        if goal_target is not None or goal_due_month is not None:
            raise ValueError("goal_target and goal_due_month require goal_type")
        return
    if goal_target is None:
        raise ValueError("goal_target is required")
    if goal_type == "due_date":
        if goal_due_month is None or len(goal_due_month) != 7 or goal_due_month[4] != "-":
            raise ValueError("due-date goals require goal_due_month in YYYY-MM")
        try:
            year, month = int(goal_due_month[:4]), int(goal_due_month[5:])
        except ValueError as exc:
            raise ValueError("due-date goals require goal_due_month in YYYY-MM") from exc
        if year < 1 or month not in range(1, 13):
            raise ValueError("due-date goals require goal_due_month in YYYY-MM")
    elif goal_due_month is not None:
        raise ValueError("goal_due_month is only valid for due-date goals")


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    group_id: UUID | None
    name: str
    is_pending: bool
    status: Literal["active", "archived"]
    goal_type: Literal["target_balance", "monthly_funding", "due_date"] | None
    goal_target: StrictStr | None
    goal_due_month: str | None
    created_at: datetime
    updated_at: datetime


class TagCreate(StrictRequest):
    name: NonEmptyName


class TagPatch(StrictRequest):
    name: NonEmptyName


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    name: str
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime


class TransactionCreate(StrictRequest):
    type: Literal["income", "expense"]
    account_id: UUID
    amount: StrictStr
    currency_code: StrictStr
    event_at: datetime
    category_id: UUID | None = None
    merchant: StrictStr | None = None
    memo: StrictStr | None = None
    photo_reference: StrictStr | None = None
    location: dict[str, Any] | None = None
    tags: list[UUID] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_at")
    @classmethod
    def validate_event_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        return value


class TransactionCorrectionCreate(StrictRequest):
    amount: StrictStr | None = None
    account_id: UUID | None = None
    category_id: UUID | None = None
    event_at: datetime | None = None
    merchant: StrictStr | None = None
    memo: StrictStr | None = None
    photo_reference: StrictStr | None = None
    location: dict[str, Any] | None = None
    tags: list[UUID] | None = None
    source_metadata: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None

    @field_validator("event_at")
    @classmethod
    def validate_event_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("event_at must include a timezone offset")
        return value

    @model_validator(mode="after")
    def require_a_change(self) -> "TransactionCorrectionCreate":
        if not self.model_fields_set:
            raise ValueError("correction must change at least one field")
        return self


class TransactionCorrectionResponse(BaseModel):
    id: UUID
    plan_id: UUID
    transaction_id: UUID
    correction_sequence: int
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime


class TransactionResponse(BaseModel):
    id: UUID
    plan_id: UUID
    account_id: UUID
    type: Literal["income", "expense", "transfer"]
    amount: StrictStr
    currency_code: str
    event_at: datetime
    category_id: UUID | None
    merchant: str | None
    memo: str | None
    photo_reference: str | None
    location: dict[str, Any] | None
    tags: list[UUID]
    source: str
    source_metadata: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    transfer_id: UUID | None = None
    transfer_role: Literal["outbound", "inbound"] | None = None


class TransferCreate(StrictRequest):
    source_account_id: UUID
    destination_account_id: UUID
    outbound_amount: StrictStr
    inbound_amount: StrictStr
    event_at: datetime
    rate_source: StrictStr | None = None
    memo: StrictStr | None = None
    provenance: dict[str, Any]

    @field_validator("event_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        return value


class TransferReversalCreate(StrictRequest):
    event_at: datetime
    reversal_reason: StrictStr
    memo: StrictStr | None = None
    provenance: dict[str, Any]

    @field_validator("event_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        return value


class TransferLegResponse(BaseModel):
    id: UUID
    role: Literal["outbound", "inbound"]
    transaction_id: UUID
    movement_id: UUID


class TransferResponse(BaseModel):
    id: UUID
    plan_id: UUID
    source_account_id: UUID
    destination_account_id: UUID
    outbound_amount: StrictStr
    outbound_currency_code: str
    inbound_amount: StrictStr
    inbound_currency_code: str
    event_at: datetime
    rate: StrictStr
    memo: str | None
    reversal_reason: str | None
    provenance: dict[str, Any]
    reverses_transfer_id: UUID | None
    created_at: datetime
    legs: list[TransferLegResponse]
    rate_source: str | None = None


class AssignmentCreate(StrictRequest):
    category_id: UUID
    month_key: str | None = None
    month: str | None = None
    amount: StrictStr
    currency_code: StrictStr | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_month(self) -> "AssignmentCreate":
        if (self.month_key is None) == (self.month is None):
            raise ValueError("provide exactly one month_key or month")
        key = self.month_key or self.month
        assert key is not None
        if len(key) != 7 or key[4] != "-":
            raise ValueError("month must use YYYY-MM")
        try:
            year = int(key[:4])
            month = int(key[5:])
        except ValueError as exc:
            raise ValueError("month must use YYYY-MM") from exc
        if year < 1 or month not in range(1, 13):
            raise ValueError("month must use YYYY-MM")
        self.month_key = key
        self.month = None
        return self


class AssignmentResponse(BaseModel):
    id: UUID
    plan_id: UUID
    category_id: UUID
    month_key: str
    amount: StrictStr
    currency_code: str
    source: str
    provenance: dict[str, Any]
    created_at: datetime


class MoneyResponse(BaseModel):
    amount: StrictStr
    currency: StrictStr


class UnconvertedCurrencyResponse(BaseModel):
    currency: StrictStr
    income: StrictStr = "0"
    expense: StrictStr = "0"
    amount: StrictStr = "0"
    movement_ids: list[UUID] = Field(default_factory=list)
    transaction_ids: list[UUID] = Field(default_factory=list)


class CategoryEnvelopeResponse(BaseModel):
    plan_id: UUID
    category_id: UUID
    month: str
    currency: StrictStr
    assigned: StrictStr
    activity: StrictStr
    available: StrictStr
    assigned_money: MoneyResponse
    activity_money: MoneyResponse
    available_money: MoneyResponse
    rollover: StrictStr
    cash_overspending: StrictStr
    credit_card_overspending: StrictStr
    goal: "GoalResponse | None" = None
    unconverted_by_currency: list[UnconvertedCurrencyResponse]


class GoalResponse(BaseModel):
    type: Literal["target_balance", "monthly_funding", "due_date"]
    target: StrictStr
    due_month: str | None = None
    required_contribution: StrictStr
    status: Literal["completed", "funded", "on_track", "underfunded"]


class MonthlySummaryResponse(BaseModel):
    plan_id: UUID
    month: str
    currency: StrictStr
    ready_to_assign: StrictStr
    ready_to_assign_money: MoneyResponse
    assigned_total: StrictStr
    activity_total: StrictStr
    available_total: StrictStr
    unconverted_by_currency: list[UnconvertedCurrencyResponse]
    categories: list[CategoryEnvelopeResponse]
