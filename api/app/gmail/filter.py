"""Sender-only collection boundary, not sender authentication or financial parsing."""

from email import policy
from email.parser import HeaderParser
import re


MAILBOX = re.compile(
    r"[a-z0-9][a-z0-9._+-]{0,63}@"
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)


def normalize_senders(values: list[str]) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("Allowed senders must be a list of plain mailbox addresses.")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Allowed senders must be plain mailbox addresses.")
        if any(ord(char) < 32 for char in value):
            raise ValueError("Allowed senders must not contain control characters.")
        mailbox = value.strip().lower()
        if (
            len(mailbox) > 254
            or not MAILBOX.fullmatch(mailbox)
            or ".." in mailbox
            or mailbox.split("@", 1)[0].endswith(".")
        ):
            raise ValueError("Allowed senders must be plain ASCII mailbox addresses.")
        if mailbox not in result:
            result.append(mailbox)
    return result


def sender_query(senders: list[str]) -> str:
    normalized = normalize_senders(senders)
    if not normalized:
        raise ValueError("A nonempty sender scope is required.")
    return "{" + " ".join(f"from:{sender}" for sender in normalized) + "}"


def metadata_is_allowed(metadata: dict, gmail_id: str, senders: list[str]) -> bool:
    """Reject uncertainty before raw MIME is requested. Do not retain rejected headers."""
    try:
        approved = normalize_senders(senders)
        if not approved or metadata.get("id") != gmail_id:
            return False
        labels = metadata.get("labelIds", [])
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            return False
        if {"SPAM", "TRASH"}.intersection(labels):
            return False
        headers = metadata["payload"]["headers"]
        if not isinstance(headers, list) or not all(
            isinstance(header, dict)
            and isinstance(header.get("name"), str)
            and isinstance(header.get("value"), str)
            for header in headers
        ):
            return False
        from_headers = [header["value"] for header in headers if header["name"].lower() == "from"]
        if len(from_headers) != 1 or any(ord(char) < 32 for char in from_headers[0]):
            return False
        parsed = HeaderParser(policy=policy.default).parsestr(
            "From: " + from_headers[0] + "\n\n"
        )["From"]
        if (
            parsed.defects or len(parsed.addresses) != 1
            or any(group.display_name is not None for group in parsed.groups)
        ):
            return False
        return parsed.addresses[0].addr_spec.lower() in approved
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return False
