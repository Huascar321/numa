from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuoteCreate(BaseModel):
    side: Literal["BUY_USDT", "SELL_USDT"]
    bob_amount: Decimal = Field(..., gt=0, description="BOB amount paid or received")
    usdt_amount: Decimal = Field(..., gt=0, description="USDT amount received or sold")
    base_currency: str = Field(default="USDT", max_length=16)
    quote_currency: str = Field(default="BOB", max_length=16)
    rate: Decimal | None = Field(default=None, gt=0, description="Calculated rate BOB per USDT")
    payment_method: str | None = Field(default=None, max_length=64)
    fee_amount: Decimal | None = Field(default=Decimal("0"), ge=0)
    min_limit: Decimal | None = Field(default=None, ge=0)
    max_limit: Decimal | None = Field(default=None, ge=0)
    source: str = Field(default="manual", max_length=64)
    offer_context: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime | None = None
    creation_fingerprint: str | None = None

    @model_validator(mode="after")
    def compute_rate_and_currencies(self) -> "QuoteCreate":
        if self.rate is None:
            # Explicit quote formulas:
            # BUY_USDT: rate = BOB paid / USDT received
            # SELL_USDT: rate = BOB received / USDT sold
            computed = (self.bob_amount / self.usdt_amount).quantize(
                Decimal("0.00000001")
            )
            self.rate = computed
        return self


class QuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    base_currency: str
    quote_currency: str
    side: str
    bob_amount: Decimal
    usdt_amount: Decimal
    rate: Decimal
    payment_method: str | None = None
    fee_amount: Decimal | None = None
    min_limit: Decimal | None = None
    max_limit: Decimal | None = None
    source: str
    offer_context: dict[str, Any]
    observed_at: datetime
    created_at: datetime
    updated_at: datetime
    is_stale: bool = False
    freshness: Literal["fresh", "stale"] = "fresh"


class LatestQuoteResponse(BaseModel):
    buy_quote: QuoteResponse | None = None
    sell_quote: QuoteResponse | None = None
    has_fresh_quote: bool = False
    has_quote: bool = False
    is_stale: bool = True
    staleness_threshold_hours: int = 24


class ConvertRequest(BaseModel):
    from_currency: str = Field(..., min_length=1, max_length=16)
    to_currency: str = Field(..., min_length=1, max_length=16)
    amount: Decimal = Field(..., gt=0)
    side: Literal["BUY_USDT", "SELL_USDT"] | None = None
    quote_id: UUID | None = None
    custom_rate: Decimal | None = Field(default=None, gt=0)


class ConvertResponse(BaseModel):
    from_currency: str
    to_currency: str
    from_amount: Decimal
    to_amount: Decimal
    rate_used: Decimal
    rate_source: str
    quote_id: UUID | None = None
    rate_observed_at: datetime | None = None
    is_stale: bool = False
    formula: str
    provenance: dict[str, Any]


class ProviderStatus(BaseModel):
    id: str
    name: str
    status: Literal["available", "reference_only", "unverified_optional", "unavailable"]
    is_primary: bool
    description: str
    last_checked_at: datetime | None = None
    notes: str | None = None


class ProviderListResponse(BaseModel):
    providers: list[ProviderStatus]
