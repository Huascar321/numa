from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import email.utils
import re
from typing import Any

from app.watchers.email_decoder import parse_date_header
from app.watchers.models import WatcherRawMessage


BINANCE_CARD_SENDER = "do-not-reply@ses.binance.com"

# Subject pattern: "Binance Card - You have spent 15.50 USD on 2026-08-24 14:30:00 (UTC)"
SUBJECT_REGEX = re.compile(
    r"^Binance Card - You have spent\s+(?P<amount>\d+(?:\.\d+)?)\s+(?P<currency>[A-Z]{3})\s+on\s+(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\(UTC\)$",
    re.IGNORECASE,
)

UUID_REGEX = re.compile(
    r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)

MERCHANT_PATTERNS = [
    re.compile(
        r"You have spent\s+\d+(?:\.\d+)?\s+[A-Z]{3}\s+at\s+([^\n\r<.]+?)(?:\s+with your Binance Card|\.|\n|<|$)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:Merchant|At merchant|Comercio):\s*([^\n\r<]+)", re.IGNORECASE),
    re.compile(
        r"(?:Merchant|Comercio)[\s\S]*?<td[^>]*>([^<]+)</td>",
        re.IGNORECASE,
    ),
    re.compile(
        r"<div[^>]*class=[\"'][^\"']*merchant[^\"']*[\"'][^>]*>([^<]+)</div>",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class BinanceCardParseResult:
    is_binance_card: bool
    reported_amount: Decimal | None = None
    reported_currency: str | None = None
    event_at: datetime | None = None
    notification_at: datetime | None = None
    merchant: str | None = None
    provider_uuid: str | None = None
    message_id_header: str | None = None
    error: str | None = None


def extract_sender_address(sender: str) -> str:
    """Extract clean email address from a RFC 2822 sender string."""
    name, addr = email.utils.parseaddr(sender)
    return addr.strip().lower() if addr else sender.strip().lower()


def extract_merchant(body_plain: str | None, body_html: str | None) -> str | None:
    """Extract merchant name from email body text or HTML."""
    content_sources = [body_plain or "", body_html or ""]
    for text in content_sources:
        if not text:
            continue
        for pattern in MERCHANT_PATTERNS:
            match = pattern.search(text)
            if match:
                candidate = match.group(1).strip()
                # Clean up html tags or extra quotes
                cleaned = re.sub(r"<[^>]+>", "", candidate).strip(" \"'.,;")
                if cleaned and len(cleaned) <= 255:
                    return cleaned
    return None


def extract_provider_uuid(
    body_plain: str | None,
    body_html: str | None,
    raw_headers: dict[str, Any],
) -> str | None:
    """Extract optional unverified provider UUID from body or headers."""
    # Check headers first
    for k, v in raw_headers.items():
        if "uuid" in k.lower() or "order" in k.lower():
            val_str = str(v)
            match = UUID_REGEX.search(val_str)
            if match:
                return match.group(1)

    # Check body
    for text in [body_html or "", body_plain or ""]:
        if not text:
            continue
        match = UUID_REGEX.search(text)
        if match:
            return match.group(1)
    return None


def parse_binance_card_message(raw_message: WatcherRawMessage) -> BinanceCardParseResult:
    """Parse a WatcherRawMessage according to the Binance Card contract.

    Invariants:
    1. Match observed sender `do-not-reply@ses.binance.com`.
    2. Match exact success subject pattern with UTC timestamp.
    3. Subject timestamp is event time (`event_at` with UTC tz); `Date` header is `notification_at`.
    4. Reported currency (e.g. `USD`) and amount must remain separate from settlement currency/amount.
    5. The parser MUST NOT assume reported USD is USDT, nor convert USD to USDT.
    6. Message-ID is preserved for deduplication.
    7. Hidden provider UUID remains unverified candidate metadata.
    """
    sender_addr = extract_sender_address(raw_message.sender)
    if sender_addr != BINANCE_CARD_SENDER:
        return BinanceCardParseResult(
            is_binance_card=False,
            error=f"Sender '{sender_addr}' does not match Binance Card sender '{BINANCE_CARD_SENDER}'.",
        )

    clean_subject = raw_message.subject.strip()
    match = SUBJECT_REGEX.match(clean_subject)
    if not match:
        return BinanceCardParseResult(
            is_binance_card=False,
            error="Subject does not match Binance Card success pattern.",
        )

    amount_str = match.group("amount")
    currency_str = match.group("currency").upper()
    timestamp_str = match.group("timestamp")

    try:
        reported_amount = Decimal(amount_str)
        if reported_amount <= 0:
            return BinanceCardParseResult(
                is_binance_card=False,
                error=f"Reported amount must be positive, got {reported_amount}.",
            )
    except (InvalidOperation, ValueError):
        return BinanceCardParseResult(
            is_binance_card=False,
            error=f"Invalid reported amount format: {amount_str}.",
        )

    try:
        event_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        return BinanceCardParseResult(
            is_binance_card=False,
            error=f"Failed to parse UTC timestamp '{timestamp_str}': {exc}",
        )

    # Notification time: parse from Date header, fallback to internal_date
    raw_headers = raw_message.raw_headers or {}
    date_header = raw_headers.get("date")
    notification_at = (
        parse_date_header(date_header if isinstance(date_header, str) else None)
        or raw_message.internal_date
    )

    merchant = extract_merchant(raw_message.body_plain, raw_message.body_html)
    provider_uuid = extract_provider_uuid(
        raw_message.body_plain,
        raw_message.body_html,
        raw_headers,
    )
    message_id_header = raw_headers.get("message-id") or raw_message.provenance.get("message_id")
    if isinstance(message_id_header, list):
        message_id_header = message_id_header[0] if message_id_header else None
    if message_id_header:
        message_id_header = str(message_id_header).strip()

    return BinanceCardParseResult(
        is_binance_card=True,
        reported_amount=reported_amount,
        reported_currency=currency_str,
        event_at=event_dt,
        notification_at=notification_at,
        merchant=merchant,
        provider_uuid=provider_uuid,
        message_id_header=message_id_header,
    )
