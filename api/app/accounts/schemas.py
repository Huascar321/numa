from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints
from typing_extensions import Annotated


AccountType = Literal[
    "Bank",
    "Cash",
    "Wallet",
    "Credit Card",
    "Crypto",
    "Other",
]
AccountStatus = Literal["active", "archived"]
NonEmptyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
CurrencyCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=16),
]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CurrencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    decimal_places: int = Field(ge=0)


class PlanCreate(StrictRequest):
    name: NonEmptyName
    reporting_currency_code: CurrencyCode


class PlanRename(StrictRequest):
    name: NonEmptyName


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    reporting_currency_code: str
    created_at: datetime
    updated_at: datetime


class AccountCreate(StrictRequest):
    name: NonEmptyName
    account_type: AccountType
    currency_code: CurrencyCode


class AccountRename(StrictRequest):
    name: NonEmptyName


class BalanceResponse(BaseModel):
    amount: StrictStr
    currency: StrictStr


class AccountResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    name: str
    account_type: AccountType
    currency_code: str
    balance: BalanceResponse
    created_at: datetime
    updated_at: datetime


class AccountResponse(AccountResponseBase):
    status: AccountStatus


class AccountArchiveResponse(AccountResponseBase):
    status: Literal["archived"]
