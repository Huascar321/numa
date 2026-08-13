from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.accounts.schemas import AccountCreate, AccountResponse, PlanCreate


@pytest.mark.parametrize(
    "account_type",
    ["Bank", "Cash", "Wallet", "Credit Card", "Crypto", "Other"],
)
def test_account_create_accepts_each_exact_account_type(account_type: str) -> None:
    contract = AccountCreate.model_validate(
        {
            "name": f"{account_type} account",
            "account_type": account_type,
            "currency_code": "BOB",
        }
    )

    assert contract.account_type == account_type


@pytest.mark.parametrize("account_type", ["bank", "CreditCard", "Investment"])
def test_account_create_rejects_unknown_or_inexact_account_type(
    account_type: str,
) -> None:
    with pytest.raises(ValidationError):
        AccountCreate.model_validate(
            {
                "name": "Invalid account",
                "account_type": account_type,
                "currency_code": "BOB",
            }
        )


@pytest.mark.parametrize(
    ("contract", "payload"),
    [
        (
            PlanCreate,
            {
                "name": "Plan",
                "reporting_currency_code": "BOB",
                "budget_timezone": "America/La_Paz",
                "balance": 1.0,
            },
        ),
        (
            AccountCreate,
            {
                "name": "Account",
                "account_type": "Bank",
                "currency_code": "BOB",
                "opening_balance": 1.0,
            },
        ),
    ],
)
def test_create_contracts_reject_additional_fields(contract, payload) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract.model_validate(payload)


@pytest.mark.parametrize("status", ["active", "archived"])
def test_account_response_accepts_only_declared_statuses(status: str) -> None:
    payload = {
        "id": "00000000-0000-0000-0000-000000000001",
        "plan_id": "00000000-0000-0000-0000-000000000002",
        "name": "Account",
        "account_type": "Bank",
        "currency_code": "BOB",
        "status": status,
        "balance": {"amount": "0.00", "currency": "BOB"},
        "created_at": "2026-08-12T00:00:00Z",
        "updated_at": "2026-08-12T00:00:00Z",
    }

    assert AccountResponse.model_validate(payload).status == status

    with pytest.raises(ValidationError):
        AccountResponse.model_validate({**payload, "status": "deleted"})
