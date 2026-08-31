from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import email.utils
import re
from typing import Any

from app.watchers.binance_card import extract_sender_address
from app.watchers.email_decoder import parse_date_header
from app.watchers.models import WatcherRawMessage


BCP_SENDER_PATTERNS = [
    re.compile(r"notificaciones(?:bcp)?@bcp\.com\.bo", re.IGNORECASE),
    re.compile(r"@bcp\.com\.bo", re.IGNORECASE),
]

BCP_SUBJECT_PATTERNS = [
    re.compile(r"transferencia.*qr", re.IGNORECASE),
    re.compile(r"comprobante.*qr", re.IGNORECASE),
    re.compile(r"pago.*qr", re.IGNORECASE),
    re.compile(r"cobro.*qr", re.IGNORECASE),
    re.compile(r"bcp.*qr", re.IGNORECASE),
    re.compile(r"comprobante.*transferencia", re.IGNORECASE),
]

TRANSACTION_ID_PATTERNS = [
    re.compile(r"(?:Nro\.?\s*Operaci[oó]n|Operaci[oó]n|Nro\.?\s*Transacci[oó]n|Transacci[oó]n):\s*([0-9a-zA-Z\-]+)", re.IGNORECASE),
    re.compile(r"(?:Operaci[oó]n|Transacci[oó]n)[\s\S]*?<td[^>]*>([0-9a-zA-Z\-]+)</td>", re.IGNORECASE),
]

RECEIPT_ID_PATTERNS = [
    re.compile(r"(?:Nro\.?\s*Comprobante|Comprobante|Nro\.?\s*Recibo|Recibo):\s*([0-9a-zA-Z\-]+)", re.IGNORECASE),
    re.compile(r"(?:Comprobante|Recibo)[\s\S]*?<td[^>]*>([0-9a-zA-Z\-]+)</td>", re.IGNORECASE),
]

AMOUNT_PATTERNS = [
    re.compile(r"(?:Monto|Importe|Total):\s*(?:Bs\.?|BOB)?\s*(?P<amount>\d+(?:[.,]\d+)?)", re.IGNORECASE),
    re.compile(r"(?:Bs\.?|BOB)\s*(?P<amount>\d+(?:[.,]\d+)?)", re.IGNORECASE),
    re.compile(r"(?:Monto|Importe)[\s\S]*?<td[^>]*>(?:Bs\.?|BOB)?\s*([0-9.,]+)</td>", re.IGNORECASE),
]

FECHA_PATTERNS = [
    # 24/08/2026 14:30:00 or 24/08/2026 14:30
    re.compile(r"(?:Fecha|Fecha\s+y\s+hora):\s*(?P<date>\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)", re.IGNORECASE),
    # 2026-08-24 14:30:00
    re.compile(r"(?:Fecha|Fecha\s+y\s+hora):\s*(?P<date>\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)", re.IGNORECASE),
    re.compile(r"(?:Fecha|Fecha\s+y\s+hora)[\s\S]*?<td[^>]*>([^<]+)</td>", re.IGNORECASE),
]

GLOSA_PATTERNS = [
    re.compile(r"\b(BM\s+BM\s+QR\s+PAGO\s+DE\s+PRODUCTOS)\b", re.IGNORECASE),
    re.compile(r"\b(BM\s+BM\s+QR\s+INTERBANCARIA)\b", re.IGNORECASE),
    re.compile(r"(?:Glosa|Motivo|Detalle|Descripci[oó]n):\s*([^\n\r<]+?)(?=\s+(?:Beneficiario|Destinatario|Para|Banco|Monto|Fecha|Operaci|Comprobante)|$)", re.IGNORECASE),
    re.compile(r"(?:Glosa|Motivo|Detalle)[\s\S]*?<td[^>]*>([^<]+)</td>", re.IGNORECASE),
]

BENEFICIARY_PATTERNS = [
    re.compile(r"(?:Beneficiario|Destinatario|Para|A\s+favor\s+de):\s*([^\n\r<]+?)(?=\s+(?:Glosa|Motivo|Detalle|Banco|Monto|Fecha|Operaci|Comprobante)|$)", re.IGNORECASE),
    re.compile(r"(?:Beneficiario|Destinatario)[\s\S]*?<td[^>]*>([^<]+)</td>", re.IGNORECASE),
]

DESTINATION_BANK_PATTERNS = [
    re.compile(r"(?:Banco\s+Destino|Banco|Entidad\s+Destino):\s*([^\n\r<]+)", re.IGNORECASE),
    re.compile(r"(?:Banco\s+Destino|Entidad\s+Destino)[\s\S]*?<td[^>]*>([^<]+)</td>", re.IGNORECASE),
]


BOLIVIA_TZ = timezone(timedelta(hours=-4))


@dataclass(frozen=True)
class BcpQrParseResult:
    is_bcp_qr: bool
    reported_amount: Decimal | None = None
    reported_currency: str = "BOB"
    event_at: datetime | None = None
    notification_at: datetime | None = None
    transaction_id: str | None = None
    receipt_id: str | None = None
    glosa: str | None = None
    raw_glosa: str | None = None
    beneficiary: str | None = None
    destination_bank: str | None = None
    parties: dict[str, Any] | None = None
    message_id_header: str | None = None
    timezone_provenance: str | None = None
    error: str | None = None


def parse_bcp_event_date(date_str: str) -> datetime | None:
    """Parse BCP body date into timezone-aware datetime (-04:00)."""
    cleaned = date_str.strip()
    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            # Apply Bolivia timezone (-04:00)
            return dt.replace(tzinfo=BOLIVIA_TZ)
        except ValueError:
            continue
    return None


def parse_bcp_qr_message(raw_message: WatcherRawMessage) -> BcpQrParseResult:
    """Parse a WatcherRawMessage according to the BCP QR notice contract.

    Invariants:
    1. Matches BCP sender and QR subject contract.
    2. Body Fecha is event time with -04:00 timezone and timezone provenance.
    3. Transaction ID, receipt ID, BOB amount, parties/accounts are extracted.
    4. Raw glosa is preserved if present; NEVER synthesized if absent.
    5. Deduplication prioritizes transaction ID > receipt ID > Message-ID.
    """
    sender_addr = extract_sender_address(raw_message.sender)
    is_bcp_sender = any(p.search(sender_addr) for p in BCP_SENDER_PATTERNS)

    subject_matches = any(p.search(raw_message.subject) for p in BCP_SUBJECT_PATTERNS)
    body_plain = raw_message.body_plain or ""
    body_html = raw_message.body_html or ""
    all_content = f"{raw_message.subject}\n{body_plain}\n{body_html}"

    has_qr_keywords = (
        "qr" in raw_message.subject.lower()
        or "qr" in body_plain.lower()
        or "qr" in body_html.lower()
        or "interbancaria" in body_plain.lower()
        or "pago de productos" in body_plain.lower()
    )

    if not (is_bcp_sender and (subject_matches or has_qr_keywords)):
        return BcpQrParseResult(
            is_bcp_qr=False,
            error="Message does not match BCP QR sender or subject patterns.",
        )

    # 1. Transaction ID
    transaction_id: str | None = None
    for pattern in TRANSACTION_ID_PATTERNS:
        match = pattern.search(all_content)
        if match:
            transaction_id = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if transaction_id:
                break

    # 2. Receipt ID
    receipt_id: str | None = None
    for pattern in RECEIPT_ID_PATTERNS:
        match = pattern.search(all_content)
        if match:
            receipt_id = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if receipt_id:
                break

    # 3. Amount
    amount: Decimal | None = None
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(all_content)
        if match:
            amt_str = match.group("amount").replace(",", ".")
            try:
                amt = Decimal(amt_str)
                if amt > 0:
                    amount = amt
                    break
            except (InvalidOperation, ValueError):
                continue

    if amount is None:
        return BcpQrParseResult(
            is_bcp_qr=False,
            error="Could not extract positive BOB amount from BCP QR notice.",
        )

    # 4. Event Date (Fecha)
    event_at: datetime | None = None
    tz_provenance: str | None = None
    for pattern in FECHA_PATTERNS:
        match = pattern.search(all_content)
        if match:
            raw_date_str = match.group(1) if match.lastindex == 1 else match.group("date")
            cleaned_date = re.sub(r"<[^>]+>", "", raw_date_str).strip()
            event_at = parse_bcp_event_date(cleaned_date)
            if event_at:
                tz_provenance = "Bolivia local time (-04:00) parsed from body Fecha"
                break

    # Fallback event date to internal date if body date parsing failed
    if event_at is None:
        event_at = raw_message.internal_date

    # 5. Glosa (Explicit extraction: NEVER synthesize if absent)
    raw_glosa: str | None = None
    for pattern in GLOSA_PATTERNS:
        match = pattern.search(all_content)
        if match:
            candidate_glosa = re.sub(r"<[^>]+>", "", match.group(1)).strip(" \"'.,;")
            if candidate_glosa and len(candidate_glosa) <= 255:
                raw_glosa = candidate_glosa
                break

    # 6. Beneficiary and Bank
    beneficiary: str | None = None
    for pattern in BENEFICIARY_PATTERNS:
        match = pattern.search(all_content)
        if match:
            b = re.sub(r"<[^>]+>", "", match.group(1)).strip(" \"'.,;")
            if b:
                beneficiary = b
                break

    destination_bank: str | None = None
    for pattern in DESTINATION_BANK_PATTERNS:
        match = pattern.search(all_content)
        if match:
            db = re.sub(r"<[^>]+>", "", match.group(1)).strip(" \"'.,;")
            if db:
                destination_bank = db
                break

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

    parties = {}
    if beneficiary:
        parties["beneficiary"] = beneficiary
    if destination_bank:
        parties["destination_bank"] = destination_bank

    return BcpQrParseResult(
        is_bcp_qr=True,
        reported_amount=amount,
        reported_currency="BOB",
        event_at=event_at,
        notification_at=notification_at,
        transaction_id=transaction_id,
        receipt_id=receipt_id,
        glosa=raw_glosa,
        raw_glosa=raw_glosa,
        beneficiary=beneficiary,
        destination_bank=destination_bank,
        parties=parties,
        message_id_header=message_id_header,
        timezone_provenance=tz_provenance,
    )
