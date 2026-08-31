from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UnconvertedAmountItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency_code: str
    amount: str
    transaction_count: int = 1


class UnconvertedCurrencySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency_code: str
    total_income: str
    total_expenses: str
    net_amount: str
    transaction_count: int


class AnalyticsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    period_start: datetime
    period_end: datetime
    total_income: str
    total_expenses: str
    net_cashflow: str
    savings_rate: str
    transaction_count: int
    transfers_count: int
    transfers_excluded_notice: str
    unconverted_totals: list[UnconvertedCurrencySummary]


class CategoryAnalyticsItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: UUID | None
    category_name: str
    group_id: UUID | None = None
    group_name: str | None = None
    amount: str
    percentage: str
    transaction_count: int
    unconverted_by_currency: list[UnconvertedAmountItem] = Field(default_factory=list)


class CategoryGroupAnalyticsItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_id: UUID | None
    group_name: str
    amount: str
    percentage: str
    transaction_count: int
    categories: list[CategoryAnalyticsItem] = Field(default_factory=list)


class CategoryBreakdownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    period_start: datetime
    period_end: datetime
    type: Literal["expense", "income", "all"]
    total_amount: str
    categories: list[CategoryAnalyticsItem]
    groups: list[CategoryGroupAnalyticsItem]
    unconverted_totals: list[UnconvertedCurrencySummary] = Field(default_factory=list)


class MerchantRankingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    merchant: str
    total_amount: str
    percentage: str
    transaction_count: int
    average_amount: str
    unconverted_by_currency: list[UnconvertedAmountItem] = Field(default_factory=list)


class MerchantRankingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    period_start: datetime
    period_end: datetime
    total_expense_amount: str
    merchants: list[MerchantRankingItem]
    unconverted_totals: list[UnconvertedCurrencySummary] = Field(default_factory=list)


class TagAnalyticsItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_id: UUID
    tag_name: str
    amount: str
    percentage: str
    transaction_count: int
    unconverted_by_currency: list[UnconvertedAmountItem] = Field(default_factory=list)


class TagBreakdownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    period_start: datetime
    period_end: datetime
    type: Literal["expense", "income", "all"]
    total_tagged_amount: str
    tags: list[TagAnalyticsItem]
    untagged_amount: str
    untagged_transaction_count: int
    unconverted_totals: list[UnconvertedCurrencySummary] = Field(default_factory=list)


class CashflowTrendPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket_key: str
    bucket_start: datetime
    bucket_end: datetime
    income: str
    expense: str
    net: str
    cumulative_net: str
    transaction_count: int
    unconverted_by_currency: list[UnconvertedCurrencySummary] = Field(default_factory=list)


class CashflowTrendsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    interval: Literal["day", "week", "month"]
    period_start: datetime
    period_end: datetime
    points: list[CashflowTrendPoint]


class HeatmapCell(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day_of_week: int  # 0 = Monday, 6 = Sunday
    day_name: str
    hour_of_day: int  # 0..23
    transaction_count: int
    total_amount: str


class DailyActivityCell(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str  # YYYY-MM-DD
    transaction_count: int
    income: str
    expense: str
    total_amount: str


class LocationAnalyticsPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    latitude: float | None = None
    longitude: float | None = None
    label: str | None = None
    merchant: str | None = None
    amount: str
    currency_code: str
    transaction_count: int = 1


class ActivityHeatmapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    period_start: datetime
    period_end: datetime
    day_hour_matrix: list[HeatmapCell]
    daily_activity: list[DailyActivityCell]
    location_clusters: list[LocationAnalyticsPoint] | None = None


class CategoryGoalAnalyticsItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: UUID
    category_name: str
    group_name: str | None = None
    goal_type: str
    goal_target: str
    goal_due_month: str | None = None
    current_progress_amount: str
    target_amount: str
    progress_percentage: str
    remaining_amount: str
    status: str  # e.g., "completed", "on_track", "underfunded", "funded"


class GoalsAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: UUID
    reporting_currency_code: str
    as_of_month: str
    goals: list[CategoryGoalAnalyticsItem]
