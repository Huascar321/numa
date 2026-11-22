"""Fixture/MIME checks only: no watcher, database access or financial mutation."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

from app.gmail.mime import decode_message


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "binance_card_notice_contracts.json").read_text(
        encoding="utf-8"
    )
)["samples"]


@pytest.mark.parametrize("sample", FIXTURES, ids=lambda sample: sample["name"])
def test_synthetic_notice_roundtrips_through_existing_mime_decoder(sample):
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "do-not-reply@ses.binance.com"
    message["To"] = "synthetic-recipient@example.invalid"
    message["Subject"] = sample["subject"]
    message["Date"] = sample["notification_date"]
    message["Message-ID"] = sample["message_id"]
    message.set_content(sample["html"], subtype="html", charset="utf-8", cte="base64")

    decoded = decode_message(message.as_bytes())
    headers = {header["name"].lower(): header["value"] for header in decoded["headers"]}
    assert headers["from"] == "do-not-reply@ses.binance.com"
    assert headers["subject"] == sample["subject"]
    assert headers["message-id"] == sample["message_id"]
    assert decoded["issues"] == []
    assert decoded["authentication_independently_verified"] is False
    assert len(decoded["parts"]) == 1
    part = decoded["parts"][0]
    assert part["content_type"] == "text/html"
    assert part["mime_charset"] == part["used_charset"] == "utf-8"
    assert part["transfer_encoding"] == "base64"
    assert part["text"].strip() == sample["html"]


@pytest.mark.parametrize("sample", FIXTURES, ids=lambda sample: sample["name"])
def test_synthetic_expectations_are_consistent_and_leave_settlement_unresolved(sample):
    """Verify fixture declarations, not yet-implemented parser/review behavior."""
    candidate = sample["expected_candidate"]
    if candidate is None:
        assert "Transaction Failed" in sample["subject"]
        assert sample["expected_disposition"] == "non_success_notice_no_posting"
        return

    assert "Transaction Successful" in sample["subject"]
    assert isinstance(candidate["reported_amount"], str)
    assert Decimal(candidate["reported_amount"]).is_finite()
    assert candidate["reported_currency"] == "USD"
    assert f"You’ve paid {candidate['reported_amount']} USD at {candidate['merchant']}." in sample["html"]
    event = datetime.fromisoformat(candidate["event_at"])
    subject_time = sample["subject"].removeprefix(
        "Binance Card - Transaction Successful - "
    ).removesuffix(" (UTC)")
    assert event == datetime.strptime(subject_time, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    assert parsedate_to_datetime(sample["notification_date"]) > event
    assert candidate["settlement_amount"] is None
    assert candidate["settlement_currency"] is None
    assert candidate["account_id"] is None
    assert candidate["disposition"] == "review_required_no_posting"
