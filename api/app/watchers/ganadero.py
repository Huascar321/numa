from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import email.header
import email.utils
import re
from typing import Any

from app.watchers.binance_card import extract_sender_address
from app.watchers.email_decoder import parse_date_header
from app.watchers.models import WatcherRawMessage


BANCO_GANADERO_SENDER = "notificaciones@bg.com.bo"

# Pattern for credit notice: "Recibiste Bs 100.00 en tu cuenta *1234"
CREDIT_PATTERN = re.compile(
    r"(?:Recibiste|Abono|Credito|Depósito|Transferencia recibida)\s*(?:de)?\s*Bs\.?\s*(?P<amount>\d+(?:[.,]\d+)?)(?:[^*]*\*(?P<suffix>\d+))?",
    re.IGNORECASE,
)

# Pattern for debit notice: "Enviaste Bs 25.50 de tu cuenta *5678"
DEBIT_PATTERN = re.compile(
    r"(?:Enviaste|Debito|Cargo|Retiro|Transferencia enviada)\s*(?:de)?\s*Bs\.?\s*(?P<amount>\d+(?:[.,]\d+)?)(?:[^*]*\*(?P<suffix>\d+))?",
    re.IGNORECASE,
)

SUFFIX_PATTERN = re.compile(r"\*(?P<suffix>\d{3,6})")


@dataclass(frozen=True)
class BancoGanaderoParseResult:
    is_banco_ganadero: bool
    reported_amount: Decimal | None = None
    reported_currency: str | None = None
    raw_currency_token: str | None = None
    direction: str | None = None  # "credit" | "debit"
    account_suffix: str | None = None
    notification_at: datetime | None = None
    event_at: datetime | None = None  # Always None for Ganadero notices (pending statement enrichment)
    message_id_header: str | None = None
    error: str | None = None


def decode_rfc2047(header_str: str | None) -> str:
    """Decode an RFC2047 encoded header string safely."""
    if not header_str:
        return ""
    try:
        decoded_parts = email.header.decode_header(header_str)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                enc = encoding or "utf-8"
                try:
                    result.append(part.decode(enc, errors="replace"))
                except Exception:
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(str(part))
        return "".join(result).strip()
    except Exception:
        return str(header_str).strip()


def parse_banco_ganadero_message(raw_message: WatcherRawMessage) -> BancoGanaderoParseResult:
    """Parse a WatcherRawMessage according to the Banco Ganadero notice contract.

    Invariants:
    1. Matches sender `notificaciones@bg.com.bo`.
    2. Decodes RFC2047 subjects.
    3. Identifies credit ('Recibiste') or debit ('Enviaste') notices.
    4. Maps raw 'Bs' token to 'BOB' while preserving raw token in provenance.
    5. Captures masked suffix (e.g. *1234).
    6. Retains Date header ONLY as notification_at; leaves event_at as None (pending statement enrichment).
    7. Retains Message-ID for fallback deduplication.
    8. Preserves trusted receiver authentication metadata as provenance.
    """
    sender_addr = extract_sender_address(raw_message.sender)
    if sender_addr != BANCO_GANADERO_SENDER:
        return BancoGanaderoParseResult(
            is_banco_ganadero=False,
            error=f"Sender '{sender_addr}' does not match Banco Ganadero sender '{BANCO_GANADERO_SENDER}'.",
        )

    decoded_subject = decode_rfc2047(raw_message.subject)
    content_sources = [
        decoded_subject,
        raw_message.body_plain or "",
        raw_message.body_html or "",
        raw_message.snippet or "",
    ]

    direction: str | None = None
    amount_str: str | None = None
    suffix: str | None = None

    # Check credit pattern
    for text in content_sources:
        if not text:
            continue
        credit_match = CREDIT_PATTERN.search(text)
        if credit_match:
            direction = "credit"
            amount_str = credit_match.group("amount")
            suffix = credit_match.group("suffix")
            break

    # If not credit, check debit pattern
    if direction is None:
        for text in content_sources:
            if not text:
                continue
            debit_match = DEBIT_PATTERN.search(text)
            if debit_match:
                direction = "debit"
                amount_str = debit_match.group("amount")
                suffix = debit_match.group("suffix")
                break

    # If suffix not found from pattern, search general suffix pattern in content
    if suffix is None:
        for text in content_sources:
            if not text:
                continue
            suffix_match = SUFFIX_PATTERN.search(text)
            if suffix_match:
                suffix = suffix_match.group("suffix")
                break

    if direction is None or amount_str is None:
        return BancoGanaderoParseResult(
            is_banco_ganadero=False,
            error="Could not determine credit/debit direction or Bs amount from Banco Ganadero notice.",
        )

    # Normalize decimal separator
    normalized_amount_str = amount_str.replace(",", ".")
    try:
        reported_amount = Decimal(normalized_amount_str)
        if reported_amount <= 0:
            return BancoGanaderoParseResult(
                is_banco_ganadero=False,
                error=f"Reported amount must be positive, got {reported_amount}.",
            )
    except (InvalidOperation, ValueError):
        return BancoGanaderoParseResult(
            is_banco_ganadero=False,
            error=f"Invalid reported amount format: {amount_str}.",
        )

    raw_headers = raw_message.raw_headers or {}
    date_header = raw_headers.get("date")
    notification_at = (
        parse_date_header(date_header if isinstance(date_header, str) else None)
        or raw_message.internal_date
    )

    message_id_header = raw_headers.get("message-id") or raw_message.provenance.get("message_id")
    if isinstance(message_id_header, list):
        message_id_header = message_id_header[0] if message_id_header else None
    if message_id_header:
        message_id_header = str(message_id_header).strip()

    account_suffix = f"*{suffix}" if suffix and not suffix.startswith("*") else suffix

    return BancoGanaderoParseResult(
        is_banco_ganadero=True,
        reported_amount=reported_amount,
        reported_currency="BOB",
        raw_currency_token="Bs",
        direction=direction,
        account_suffix=account_suffix,
        notification_at=notification_at,
        event_at=None,  # Explicitly null per specification
        message_id_header=message_id_header,
    )
