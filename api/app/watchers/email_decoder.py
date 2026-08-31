from __future__ import annotations

import base64
import email
from email.header import decode_header
import email.utils
from datetime import datetime, timezone
import quopri
import re
from typing import Any


AUTH_HEADER_NAMES = {
    "authentication-results",
    "received-spf",
    "dkim-signature",
    "arc-authentication-results",
    "arc-message-signature",
    "arc-seal",
    "message-id",
    "date",
}


def decode_rfc2047(header_value: str | None) -> str:
    """Decode RFC 2047 encoded-word strings in email headers."""
    if not header_value:
        return ""

    try:
        decoded_words = decode_header(header_value)
        result_parts: list[str] = []
        for word, encoding in decoded_words:
            if isinstance(word, bytes):
                charset = encoding or "utf-8"
                try:
                    result_parts.append(word.decode(charset, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result_parts.append(word.decode("latin-1", errors="replace"))
            else:
                result_parts.append(str(word))
        return "".join(result_parts)
    except Exception:
        return str(header_value)


def extract_inner_html_charset(html_bytes: bytes) -> str | None:
    """Detect charset declared in HTML meta tags."""
    sample = html_bytes[:2048].decode("ascii", errors="ignore")
    # Match <meta charset="...">
    match = re.search(r'<meta[^>]+charset=["\']?([a-zA-Z0-9_-]+)', sample, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Match <meta http-equiv="Content-Type" content="...charset=...">
    match = re.search(
        r'<meta[^>]+content=["\'][^"\']*charset=([a-zA-Z0-9_-]+)', sample, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return None


def decode_part_bytes(
    raw_bytes: bytes,
    mime_charset: str | None,
    is_html: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Decode message payload bytes, ensuring MIME charset takes precedence over inner HTML metadata."""
    inner_charset = extract_inner_html_charset(raw_bytes) if is_html else None
    effective_charset = mime_charset or "utf-8"
    precedence_applied = False

    if inner_charset and mime_charset:
        if inner_charset.lower() != mime_charset.lower():
            # Invariant: MIME charset takes precedence over conflicting inner metadata
            effective_charset = mime_charset
            precedence_applied = True

    try:
        text = raw_bytes.decode(effective_charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        # Safe fallback
        try:
            text = raw_bytes.decode("utf-8", errors="replace")
            effective_charset = "utf-8"
        except Exception:
            text = raw_bytes.decode("latin-1", errors="replace")
            effective_charset = "latin-1"

    metadata: dict[str, Any] = {
        "mime_charset": mime_charset,
        "inner_charset": inner_charset,
        "effective_charset": effective_charset,
        "mime_charset_precedence": precedence_applied,
    }
    return text, metadata


def decode_transfer_data(data_bytes_or_str: bytes | str, encoding: str | None) -> bytes:
    """Decode content transfer encodings (base64, quoted-printable, 7bit, 8bit)."""
    if isinstance(data_bytes_or_str, str):
        raw_bytes = data_bytes_or_str.encode("ascii", errors="ignore")
    else:
        raw_bytes = data_bytes_or_str

    if not encoding:
        return raw_bytes

    normalized = encoding.strip().lower()
    if normalized == "base64":
        cleaned = re.sub(rb"[\r\n\s]", b"", raw_bytes)
        # Add padding if needed
        missing_padding = len(cleaned) % 4
        if missing_padding:
            cleaned += b"=" * (4 - missing_padding)
        try:
            return base64.urlsafe_b64decode(cleaned)
        except Exception:
            return base64.b64decode(cleaned)
    elif normalized == "quoted-printable":
        return quopri.decodestring(raw_bytes)
    return raw_bytes


def parse_date_header(date_str: str | None) -> datetime | None:
    """Parse RFC 2822 / MIME Date header string to UTC datetime."""
    if not date_str:
        return None
    try:
        parsed_tuple = email.utils.parsedate_to_datetime(date_str)
        if parsed_tuple.tzinfo is None:
            return parsed_tuple.replace(tzinfo=timezone.utc)
        return parsed_tuple.astimezone(timezone.utc)
    except Exception:
        return None


class DecodedEmail:
    def __init__(self) -> None:
        self.sender: str = ""
        self.recipient: str | None = None
        self.subject: str = ""
        self.internal_date: datetime = datetime.now(timezone.utc)
        self.snippet: str | None = None
        self.body_plain: str | None = None
        self.body_html: str | None = None
        self.raw_headers: dict[str, Any] = {}
        self.mime_metadata: dict[str, Any] = {}
        self.provenance: dict[str, Any] = {}


def _extract_header_dict(headers_list: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract raw headers map and authentication provenance from a list of header dicts."""
    raw_headers: dict[str, Any] = {}
    auth_provenance: dict[str, Any] = {
        "authentication_results": [],
        "received_spf": [],
        "dkim_signatures": [],
        "arc_results": [],
    }

    for item in headers_list:
        name = item.get("name", "")
        value = item.get("value", "")
        decoded_value = decode_rfc2047(value)
        lower_name = name.lower()

        if lower_name in raw_headers:
            existing = raw_headers[lower_name]
            if isinstance(existing, list):
                existing.append(decoded_value)
            else:
                raw_headers[lower_name] = [existing, decoded_value]
        else:
            raw_headers[lower_name] = decoded_value

        if lower_name == "authentication-results":
            auth_provenance["authentication_results"].append(decoded_value)
        elif lower_name == "received-spf":
            auth_provenance["received_spf"].append(decoded_value)
        elif lower_name == "dkim-signature":
            auth_provenance["dkim_signatures"].append(decoded_value)
        elif lower_name.startswith("arc-"):
            auth_provenance["arc_results"].append(f"{name}: {decoded_value}")

    return raw_headers, auth_provenance


def _extract_mime_charset_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = re.search(r"charset=([^\s;\"']+)", content_type, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _walk_gmail_parts(
    part: dict[str, Any],
    plain_parts: list[str],
    html_parts: list[str],
    mime_parts_meta: list[dict[str, Any]],
) -> None:
    """Recursively traverse nested Gmail API payload parts."""
    mime_type = part.get("mimeType", "").lower()
    headers = part.get("headers", [])
    content_type_header = next(
        (h.get("value") for h in headers if h.get("name", "").lower() == "content-type"),
        None,
    )
    content_transfer_encoding = next(
        (
            h.get("value")
            for h in headers
            if h.get("name", "").lower() == "content-transfer-encoding"
        ),
        None,
    )
    mime_charset = _extract_mime_charset_from_content_type(content_type_header)

    body_obj = part.get("body", {})
    body_data = body_obj.get("data")

    if body_data:
        # Gmail API uses base64url encoding for body.data
        raw_bytes = decode_transfer_data(body_data, "base64")
        if content_transfer_encoding and content_transfer_encoding.lower() != "base64":
            raw_bytes = decode_transfer_data(raw_bytes, content_transfer_encoding)

        is_html = "text/html" in mime_type
        decoded_text, part_meta = decode_part_bytes(raw_bytes, mime_charset, is_html=is_html)
        part_meta["mime_type"] = mime_type
        part_meta["transfer_encoding"] = content_transfer_encoding or "base64"
        mime_parts_meta.append(part_meta)

        if "text/html" in mime_type:
            html_parts.append(decoded_text)
        elif "text/plain" in mime_type:
            plain_parts.append(decoded_text)

    # Walk child subparts recursively
    for subpart in part.get("parts", []):
        _walk_gmail_parts(subpart, plain_parts, html_parts, mime_parts_meta)


def decode_gmail_message_payload(message_resource: dict[str, Any]) -> DecodedEmail:
    """Decode a Gmail API message resource into DecodedEmail."""
    result = DecodedEmail()
    payload = message_resource.get("payload", {})
    headers_list = payload.get("headers", [])
    raw_headers, auth_provenance = _extract_header_dict(headers_list)

    result.raw_headers = raw_headers
    result.sender = str(raw_headers.get("from", ""))
    result.recipient = str(raw_headers.get("to")) if "to" in raw_headers else None
    result.subject = str(raw_headers.get("subject", ""))
    result.snippet = message_resource.get("snippet")

    # Date handling: prefer header Date, fallback to internalDate timestamp
    date_header = raw_headers.get("date")
    parsed_date = parse_date_header(date_header if isinstance(date_header, str) else None)
    if parsed_date:
        result.internal_date = parsed_date
    elif "internalDate" in message_resource:
        try:
            ms = int(message_resource["internalDate"])
            result.internal_date = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        except Exception:
            result.internal_date = datetime.now(timezone.utc)

    # Recursive MIME traversal
    plain_parts: list[str] = []
    html_parts: list[str] = []
    mime_parts_meta: list[dict[str, Any]] = []

    _walk_gmail_parts(payload, plain_parts, html_parts, mime_parts_meta)

    result.body_plain = "\n\n".join(plain_parts) if plain_parts else None
    result.body_html = "\n\n".join(html_parts) if html_parts else None
    result.mime_metadata = {"parts": mime_parts_meta}

    auth_provenance["message_id"] = raw_headers.get("message-id")
    auth_provenance["date_header"] = raw_headers.get("date")
    result.provenance = auth_provenance

    return result


def decode_rfc822_bytes(raw_email_bytes: bytes) -> DecodedEmail:
    """Decode raw RFC 2822 / MIME email bytes into DecodedEmail."""
    msg = email.message_from_bytes(raw_email_bytes)
    result = DecodedEmail()

    headers_list = [{"name": k, "value": v} for k, v in msg.items()]
    raw_headers, auth_provenance = _extract_header_dict(headers_list)

    result.raw_headers = raw_headers
    result.sender = str(raw_headers.get("from", ""))
    result.recipient = str(raw_headers.get("to")) if "to" in raw_headers else None
    result.subject = str(raw_headers.get("subject", ""))

    date_header = raw_headers.get("date")
    parsed_date = parse_date_header(date_header if isinstance(date_header, str) else None)
    result.internal_date = parsed_date or datetime.now(timezone.utc)

    plain_parts: list[str] = []
    html_parts: list[str] = []
    mime_parts_meta: list[dict[str, Any]] = []

    for part in msg.walk():
        if part.is_multipart():
            continue

        content_type = part.get_content_type().lower()
        transfer_encoding = part.get("content-transfer-encoding", "").lower()
        mime_charset = part.get_content_charset()

        payload_bytes = part.get_payload(decode=True)
        if payload_bytes is None:
            continue

        is_html = "text/html" in content_type
        decoded_text, part_meta = decode_part_bytes(payload_bytes, mime_charset, is_html=is_html)
        part_meta["mime_type"] = content_type
        part_meta["transfer_encoding"] = transfer_encoding
        mime_parts_meta.append(part_meta)

        if "text/html" in content_type:
            html_parts.append(decoded_text)
        elif "text/plain" in content_type:
            plain_parts.append(decoded_text)

    result.body_plain = "\n\n".join(plain_parts) if plain_parts else None
    result.body_html = "\n\n".join(html_parts) if html_parts else None
    result.snippet = (
        (result.body_plain[:200] if result.body_plain else "")
        or (result.body_html[:200] if result.body_html else "")
    )
    result.mime_metadata = {"parts": mime_parts_meta}

    auth_provenance["message_id"] = raw_headers.get("message-id")
    auth_provenance["date_header"] = raw_headers.get("date")
    result.provenance = auth_provenance

    return result
