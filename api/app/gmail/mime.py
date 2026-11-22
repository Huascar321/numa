"""Decode evidence without interpreting a notice as financial facts."""

from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser


def decode_message(raw: bytes) -> dict:
    issues: list[str] = []
    message = BytesParser(policy=policy.default).parsebytes(raw)
    headers = []
    for name, value in message.raw_items():
        try:
            decoded = str(make_header(decode_header(value)))
            if "\x00" in decoded:
                issues.append("nul_in_header")
            # JSONB cannot represent NUL or unpaired surrogate escapes.
            decoded = (
                decoded.encode("utf-8", errors="strict").decode().replace("\x00", "�")
            )
        except (LookupError, UnicodeError, ValueError):
            decoded = (
                value.encode("utf-8", errors="replace").decode().replace("\x00", "�")
            )
            issues.append("header_decode_failed")
        headers.append({"name": name, "value": decoded})

    parts = []
    for index, part in enumerate(message.walk()):
        if part.is_multipart():
            issues.extend(type(defect).__name__ for defect in part.defects)
            continue
        content = part.get_payload(decode=True) or b""
        charset = part.get_content_charset()
        used_charset = charset or "utf-8"
        if str(part.get("Content-Transfer-Encoding", "7bit")).lower() not in {
            "7bit",
            "8bit",
            "binary",
            "base64",
            "quoted-printable",
        }:
            issues.append("unknown_transfer_encoding")
        decoded_text = None
        if part.get_content_maintype() == "text":
            try:
                decoded_text = content.decode(used_charset, errors="strict")
            except (LookupError, UnicodeError):
                used_charset = "utf-8"
                decoded_text = content.decode(used_charset, errors="replace")
                issues.append("body_decode_failed")
            if "\x00" in decoded_text:
                issues.append("nul_in_body")
                decoded_text = decoded_text.replace("\x00", "�")
        parts.append(
            {
                "index": index,
                "content_type": part.get_content_type(),
                "mime_charset": charset,
                "used_charset": used_charset if decoded_text is not None else None,
                "transfer_encoding": part.get("Content-Transfer-Encoding", "7bit"),
                "text": decoded_text,
            }
        )
        issues.extend(type(defect).__name__ for defect in part.defects)

    if not any(part["text"] for part in parts):
        issues.append("no_decodable_text")
    return {
        "headers": headers,
        "parts": parts,
        "issues": sorted(set(issues)),
        "authentication_independently_verified": False,
    }
