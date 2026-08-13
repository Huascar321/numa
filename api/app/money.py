from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    """Exact monetary amount represented by Decimal or integer atomic units."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("Money does not accept float values.")
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money amount must be a Decimal.")
        if not self.currency:
            raise ValueError("Money currency is required.")

    @classmethod
    def from_decimal(cls, amount: Decimal, currency: str) -> "Money":
        if isinstance(amount, float):
            raise TypeError("Money does not accept float values.")
        if not isinstance(amount, Decimal):
            raise TypeError("Money amount must be a Decimal.")
        return cls(amount=amount, currency=currency)

    @classmethod
    def from_atomic_units(
        cls,
        atomic_units: int,
        currency: str,
        exponent: int,
    ) -> "Money":
        if isinstance(atomic_units, bool) or not isinstance(atomic_units, int):
            raise TypeError("Money atomic units must be an integer.")
        if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 0:
            raise ValueError("Money exponent must be a non-negative integer.")
        return cls(amount=Decimal(atomic_units).scaleb(-exponent), currency=currency)
