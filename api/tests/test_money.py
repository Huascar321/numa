from decimal import Decimal

import pytest

from app.money import Money


def test_money_accepts_decimal() -> None:
    money = Money.from_decimal(Decimal("12.34"), "BOB")

    assert money.amount == Decimal("12.34")
    assert money.currency == "BOB"


def test_money_accepts_integer_atomic_units() -> None:
    money = Money.from_atomic_units(1234, "BOB", 2)

    assert money.amount == Decimal("12.34")


def test_money_rejects_float_values() -> None:
    with pytest.raises(TypeError, match="float"):
        Money.from_decimal(12.34, "BOB")  # type: ignore[arg-type]


def test_money_rejects_non_integer_atomic_units() -> None:
    with pytest.raises(TypeError, match="integer"):
        Money.from_atomic_units("1234", "BOB", 2)  # type: ignore[arg-type]
