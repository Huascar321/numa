from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal

from app.fx.schemas import ProviderStatus


class FXProvider(ABC):
    id: str
    name: str
    status: str
    is_primary: bool
    description: str
    notes: str | None = None

    @abstractmethod
    def get_status(self) -> ProviderStatus:
        pass


class ManualQuoteProvider(FXProvider):
    id = "manual"
    name = "Manual Entry"
    status = "available"
    is_primary = True
    description = (
        "User-entered manual market quotes with explicit BOB paid/received and USDT amounts."
    )
    notes = "Mandatory primary source for contextual market FX quotes."

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            id=self.id,
            name=self.name,
            status="available",
            is_primary=self.is_primary,
            description=self.description,
            last_checked_at=datetime.now(timezone.utc),
            notes=self.notes,
        )


class BCBOfficialProvider(FXProvider):
    id = "bcb_official"
    name = "Banco Central de Bolivia (Official Reference)"
    status = "reference_only"
    is_primary = False
    description = (
        "Official fixed reference rate of 6.96 BOB/USD. Reference only; not a market rate for USDT."
    )
    notes = (
        "The official 6.96 rate is maintained for macroeconomic reference only "
        "and is never assumed as a primary conversion rate."
    )
    official_rate = Decimal("6.96")

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            id=self.id,
            name=self.name,
            status="reference_only",
            is_primary=False,
            description=self.description,
            last_checked_at=datetime.now(timezone.utc),
            notes=self.notes,
        )


class BinanceP2POptionalAdapter(FXProvider):
    id = "binance_p2p"
    name = "Binance P2P (Optional Adapter)"
    status = "unverified_optional"
    is_primary = False
    description = (
        "Optional automated adapter for Binance P2P BOB/USDT order book quotes. "
        "Unverified external endpoint, never sole provider."
    )
    notes = (
        "Unverified endpoint status; requires external credentials and connectivity. "
        "Manual quotes remain mandatory primary fallback."
    )

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            id=self.id,
            name=self.name,
            status="unverified_optional",
            is_primary=False,
            description=self.description,
            last_checked_at=datetime.now(timezone.utc),
            notes=self.notes,
        )


def get_registered_providers() -> list[FXProvider]:
    return [
        ManualQuoteProvider(),
        BCBOfficialProvider(),
        BinanceP2POptionalAdapter(),
    ]
