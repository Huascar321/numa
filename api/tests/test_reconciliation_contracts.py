from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.accounts.models import Currency
from app.ledger.service import LedgerValidationError
from app.reconciliation import service as reconciliation_service
from app.reconciliation.schemas import ReconciliationPreviewRequest


def _payload(statement_at: object) -> dict[str, object]:
    return {
        "statement_balance": "1.00",
        "currency_code": "BOB",
        "statement_at": statement_at,
    }


def test_statement_at_rejects_negative_zero_utc_offset() -> None:
    with pytest.raises(ValidationError, match=r"must use Z or \+00:00"):
        ReconciliationPreviewRequest.model_validate(
            _payload("2026-01-01T00:00:00-00:00")
        )


@pytest.mark.parametrize(
    "statement_at",
    [
        0,
        1.5,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        b"2026-01-01T00:00:00Z",
    ],
)
def test_statement_at_rejects_non_string_values(statement_at: object) -> None:
    with pytest.raises(ValidationError, match="must be a string"):
        ReconciliationPreviewRequest.model_validate(_payload(statement_at))


@pytest.mark.parametrize(
    "statement_at",
    ["2026-01-01T00:00:00Z", "2026-01-01T00:00:00+00:00"],
)
def test_statement_at_accepts_declared_utc_designators(statement_at: str) -> None:
    request = ReconciliationPreviewRequest.model_validate(_payload(statement_at))
    offset = request.statement_at.utcoffset()

    assert offset is not None
    assert offset.total_seconds() == 0


@pytest.mark.parametrize(
    "statement_balance",
    [
        "1e999999",
        "1E-999999",
        "100000000000000000000",
        "1.0000000000000000000",
        "00000000000000000000000000000000000000000",
    ],
)
def test_statement_balance_rejects_exponents_and_out_of_domain_strings(
    statement_balance: str,
) -> None:
    with pytest.raises(ValidationError):
        ReconciliationPreviewRequest.model_validate(
            {
                **_payload("2026-01-01T00:00:00Z"),
                "statement_balance": statement_balance,
            }
        )


@pytest.mark.parametrize(
    ("statement_balance", "decimal_places"),
    [
        ("99999999999999999999.999999999999999999", 18),
        ("99999999999999999999.99", 2),
        ("-99999999999999999999.99", 2),
        ("0.00", 2),
    ],
)
def test_statement_balance_accepts_valid_numeric_domain_limits(
    statement_balance: str, decimal_places: int
) -> None:
    request = ReconciliationPreviewRequest.model_validate(
        {
            **_payload("2026-01-01T00:00:00Z"),
            "statement_balance": statement_balance,
        }
    )
    currency = Currency(code="TEST", decimal_places=decimal_places)

    assert reconciliation_service._amount_at_currency_scale(
        request.statement_balance, currency
    ) == Decimal(statement_balance)


def test_statement_balance_is_bounded_before_decimal_parsing(monkeypatch) -> None:
    def unexpected_decimal_parse(*args, **kwargs):
        raise AssertionError("out-of-domain input reached Decimal parsing")

    monkeypatch.setattr(
        reconciliation_service, "parse_exact_decimal", unexpected_decimal_parse
    )

    with pytest.raises(LedgerValidationError, match=r"NUMERIC\(38,18\)"):
        reconciliation_service._amount_at_currency_scale(
            "1e999999", Currency(code="BOB", decimal_places=2)
        )
