from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

SENDER = "do-not-reply@ses.binance.com"
PARSER_VERSION = "binance-card-usd-review-v1"
SUBJECT = re.compile(
    r"Binance Card - Transaction (Successful|Failed) - "
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \(UTC\)"
)
SENTENCE = re.compile(
    r"You’ve paid (?P<amount>\S+) (?P<currency>[A-Z]{3}) at "
    r"(?P<merchant>.+?)\. If this wasn’t you, please "
)
AMOUNT = re.compile(r"\d{1,38}\.\d{1,2}", re.ASCII)


@dataclass(frozen=True)
class NoticeResult:
    disposition: str
    reason: str
    reported_amount: str | None = None
    reported_currency: str | None = None
    merchant: str | None = None
    event_at: datetime | None = None
    notification_at: datetime | None = None
    message_id: str | None = None


class VisibleText(HTMLParser):
    """Extract text without executing HTML or trusting hidden provider identity."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.hidden: list[tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
        hidden = (
            any(flag for _, flag in self.hidden) or tag in {"head", "script", "style", "template"}
            or "hidden" in attributes or attributes.get("aria-hidden") == "true"
            or "display:none" in style or "visibility:hidden" in style
        )
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.hidden.append((tag, hidden))
        if tag in {"p", "div", "tr", "br", "li"}:
            self.chunks.append(" ")

    def handle_endtag(self, tag):
        for index in range(len(self.hidden) - 1, -1, -1):
            if self.hidden[index][0] == tag:
                del self.hidden[index:]
                break
        if tag in {"p", "div", "tr", "li"}:
            self.chunks.append(" ")

    def handle_data(self, data):
        if not any(flag for _, flag in self.hidden):
            self.chunks.append(data)


def parse_notice(decoded: dict) -> NoticeResult:
    """Fail closed. This function cannot resolve settlement or access the ledger."""
    headers: dict[str, list[str]] = {}
    for header in decoded.get("headers", []):
        headers.setdefault(header["name"].lower(), []).append(header["value"])
    senders = [address.lower() for _, address in getaddresses(headers.get("from", []))]
    if SENDER not in senders:
        return NoticeResult("ignored", "other_sender")
    if len(headers.get("from", [])) != 1 or senders != [SENDER]:
        return NoticeResult("needs_review", "ambiguous_sender")
    subjects = headers.get("subject", [])
    if not any(subject.startswith("Binance Card") for subject in subjects):
        return NoticeResult("ignored", "unrelated_notice")
    if len(subjects) != 1:
        return NoticeResult("needs_review", "ambiguous_subject")
    match = SUBJECT.fullmatch(subjects[0])
    if not match:
        return NoticeResult("needs_review", "unsupported_subject")
    if match[1] == "Failed":
        return NoticeResult("ignored", "failed_transaction")
    if decoded.get("issues"):
        return NoticeResult("needs_review", "mime_decode_issues")
    if len(headers.get("date", [])) != 1 or len(headers.get("message-id", [])) > 1:
        return NoticeResult("needs_review", "ambiguous_metadata")
    try:
        event = datetime.strptime(match[2], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        notification = parsedate_to_datetime(headers["date"][0])
        if notification.tzinfo is None or notification < event:
            raise ValueError("Invalid notification timestamp")
    except (TypeError, ValueError, OverflowError):
        return NoticeResult("needs_review", "invalid_timestamp")
    html = [part for part in decoded.get("parts", []) if part.get("content_type") == "text/html"]
    if len(html) != 1:
        return NoticeResult("needs_review", "ambiguous_html")
    part = html[0]
    if (
        (part.get("mime_charset") or "").lower() != "utf-8"
        or (part.get("used_charset") or "").lower() != "utf-8"
        or (part.get("transfer_encoding") or "").lower() != "base64"
        or not isinstance(part.get("text"), str)
    ):
        return NoticeResult("needs_review", "unsupported_mime")
    reader = VisibleText()
    reader.feed(part["text"])
    reader.close()
    body = re.sub(r"\s+", " ", "".join(reader.chunks)).strip()
    matches = list(SENTENCE.finditer(body))
    if len(matches) != 1 or len(re.findall(r"You[’']ve paid\b", body)) != 1:
        return NoticeResult("needs_review", "unsupported_body")
    sentence = matches[0]
    if sentence["currency"] != "USD":
        return NoticeResult("needs_review", "unsupported_currency")
    amount = sentence["amount"]
    if not AMOUNT.fullmatch(amount) or Decimal(amount) <= 0:
        return NoticeResult("needs_review", "invalid_amount")
    merchant = sentence["merchant"].strip()
    if not merchant or len(merchant) > 512 or any(ord(char) < 32 for char in merchant):
        return NoticeResult("needs_review", "invalid_merchant")
    message_id = next(iter(headers.get("message-id", [])), None)
    return NoticeResult(
        "candidate", "settlement_unresolved", amount, "USD", merchant, event,
        notification, message_id,
    )
