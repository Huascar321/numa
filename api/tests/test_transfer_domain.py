from __future__ import annotations

from decimal import Decimal

import pytest

from app.ledger.service import LedgerValidationError, canonical_transfer_text, transfer_rate
from app.ledger.schemas import TransferCreate


def test_transfer_rate_uses_38_place_half_even_for_normative_ties_and_bounds() -> None:
    maximum = Decimal("99999999999999999999.999999999999999999")
    minimum = Decimal("0.000000000000000001")

    assert transfer_rate(minimum, Decimal("40000000000000000000.000000000000000000")) == Decimal("2e-38")
    assert transfer_rate(Decimal("0.000000000000000003"), Decimal("40000000000000000000.000000000000000000")) == Decimal("8e-38")
    assert transfer_rate(maximum, minimum) == Decimal("99999999999999999999999999999999999999")
    assert transfer_rate(minimum, maximum) == Decimal("1e-38")


def test_transfer_text_contract_preserves_non_space_edges_and_null_states() -> None:
    assert canonical_transfer_text("  cafe\u0301  ", field="memo", required=False, maximum=2000) == "café"
    assert canonical_transfer_text("\u00a0 Keep \u00a0", field="memo", required=False, maximum=2000) == "\u00a0 Keep \u00a0"
    assert canonical_transfer_text("   ", field="memo", required=False, maximum=2000) is None
    with pytest.raises(LedgerValidationError):
        canonical_transfer_text("   ", field="reversal_reason", required=True, maximum=500)


def test_transfer_schema_preserves_explicit_null_rate_source_presence() -> None:
    payload = TransferCreate.model_validate({
        "source_account_id": "00000000-0000-0000-0000-000000000001",
        "destination_account_id": "00000000-0000-0000-0000-000000000002",
        "outbound_amount": "1.00",
        "inbound_amount": "1.00",
        "event_at": "2026-01-01T00:00:00Z",
        "rate_source": None,
        "provenance": {},
    })
    assert "rate_source" in payload.model_fields_set
