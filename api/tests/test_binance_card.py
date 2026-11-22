from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import base64
from copy import deepcopy
from dataclasses import asdict
from email import policy
from email.message import EmailMessage
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.binance_card.models import BinanceCardReview
from app.binance_card.parser import parse_notice
from app.binance_card.service import process_pending, record_message
from app.db import session_factory_for
from app.gmail.mime import decode_message
from app.gmail.models import GmailMessage, GmailSource
from app.gmail.service import _store_message
from app.main import create_app
from app.settings import Settings

SAMPLES = json.loads((Path(__file__).parent / "fixtures/binance_card_notice_contracts.json").read_text())["samples"]


def raw_notice(sample=None):
    sample = sample or SAMPLES[0]
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "do-not-reply@ses.binance.com"
    message["Subject"] = sample["subject"]
    message["Date"] = sample["notification_date"]
    message["Message-ID"] = sample["message_id"]
    message.set_content(sample["html"], subtype="html", charset="utf-8", cte="base64")
    return message.as_bytes()


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: sample["name"])
def test_observed_contract_parser(sample):
    result = parse_notice(decode_message(raw_notice(sample)))
    expected = sample["expected_candidate"]
    if expected is None:
        assert result.disposition == "ignored"
        assert result.reason == "failed_transaction"
        assert result.reported_amount is None
        return
    assert result.disposition == "candidate"
    assert result.reason == "settlement_unresolved"
    assert result.reported_amount == expected["reported_amount"]
    assert result.reported_currency == "USD"
    assert result.merchant == expected["merchant"]
    assert result.event_at.isoformat() == expected["event_at"]
    assert result.notification_at > result.event_at
    assert result.message_id == sample["message_id"]
    assert "settlement_amount" not in asdict(result)


@pytest.mark.parametrize("kind,reason", [
    ("wrong_sender", "other_sender"), ("other_notice", "unrelated_notice"),
    ("duplicate_from", "ambiguous_sender"), ("duplicate_subject", "ambiguous_subject"),
    ("duplicate_date", "ambiguous_metadata"), ("missing_date", "ambiguous_metadata"),
    ("duplicate_message_id", "ambiguous_metadata"), ("date_without_zone", "invalid_timestamp"),
    ("early_date", "invalid_timestamp"), ("invalid_event", "invalid_timestamp"),
    ("refund_subject", "unsupported_subject"), ("currency", "unsupported_currency"),
    ("zero", "invalid_amount"), ("float_notation", "invalid_amount"),
    ("precision", "invalid_amount"), ("huge_amount", "invalid_amount"),
    ("duplicate_sentence", "unsupported_body"), ("missing_disclaimer", "unsupported_body"),
    ("ascii_variant", "unsupported_body"), ("charset", "unsupported_mime"),
    ("encoding", "unsupported_mime"), ("decode_issues", "mime_decode_issues"),
    ("second_html", "ambiguous_html"), ("hidden_sentence", "unsupported_body"),
])
def test_negative_contracts_never_invent_financial_facts(kind, reason):
    decoded = decode_message(raw_notice())
    headers = decoded["headers"]
    def header(name):
        return next(h for h in headers if h["name"].lower() == name)
    part = decoded["parts"][0]
    if kind == "wrong_sender": header("from")["value"] = "fake@example.invalid"
    elif kind == "other_notice": header("subject")["value"] = "Binance Pay notification"
    elif kind.startswith("duplicate_") and kind != "duplicate_sentence":
        name = kind.removeprefix("duplicate_").replace("_", "-")
        headers.append(deepcopy(header(name)))
    elif kind == "missing_date": headers.remove(header("date"))
    elif kind == "date_without_zone": header("date")["value"] = "Thu, 01 Jan 2026 10:00:15"
    elif kind == "early_date": header("date")["value"] = "Thu, 01 Jan 2026 09:59:59 +0000"
    elif kind == "invalid_event": header("subject")["value"] = SAMPLES[0]["subject"].replace("2026-01-01", "2026-02-31")
    elif kind == "refund_subject": header("subject")["value"] = "Binance Card - Refund"
    elif kind == "currency": part["text"] = part["text"].replace(" USD ", " EUR ")
    elif kind in {"zero", "float_notation", "precision", "huge_amount"}:
        part["text"] = part["text"].replace("12.5", {"zero": "0.00", "float_notation": "1e2", "precision": "12.555", "huge_amount": "9"*39+".00"}[kind])
    elif kind == "duplicate_sentence": part["text"] += part["text"]
    elif kind == "missing_disclaimer": part["text"] = part["text"].replace(". If this wasn’t you, please", ". Different disclaimer")
    elif kind == "ascii_variant": part["text"] = part["text"].replace("’", "'")
    elif kind == "charset": part["mime_charset"] = "latin-1"
    elif kind == "encoding": part["transfer_encoding"] = "quoted-printable"
    elif kind == "decode_issues": decoded["issues"] = ["body_decode_failed"]
    elif kind == "second_html": decoded["parts"].append(deepcopy(part))
    elif kind == "hidden_sentence": part["text"] = '<div style="display:none">'+part["text"]+'</div>'
    result = parse_notice(decoded)
    assert result.reason == reason
    assert result.disposition in {"ignored", "needs_review"}
    assert result.reported_amount is result.reported_currency is result.merchant is None
    assert result.event_at is result.notification_at is None


def test_nested_mime_merchant_punctuation_and_html_entities():
    sample = deepcopy(SAMPLES[1])
    sample["html"] = sample["html"].replace("SYNTHETIC MERCHANT BETA", "SYNTHETIC.MERCHANT &amp; BETA")
    inner = EmailMessage(policy=policy.SMTP)
    inner.set_content("Plain-text alternative is not financial evidence.")
    inner.add_alternative(sample["html"], subtype="html", charset="utf-8", cte="base64")
    outer = EmailMessage(policy=policy.SMTP)
    outer["From"] = "do-not-reply@ses.binance.com"
    outer["Subject"] = sample["subject"]
    outer["Date"] = sample["notification_date"]
    outer.make_mixed()
    outer.attach(inner)
    result = parse_notice(decode_message(outer.as_bytes()))
    assert result.disposition == "candidate"
    assert result.reported_amount == "28.40"
    assert result.merchant == "SYNTHETIC.MERCHANT & BETA"


def test_hidden_or_head_sentences_do_not_become_visible_financial_evidence():
    decoded = decode_message(raw_notice())
    part = decoded["parts"][0]
    sentence = SAMPLES[0]["html"]
    part["text"] = '<div hidden><br/>'+sentence+'</div><p>No visible payment.</p>'
    assert parse_notice(decoded).reason == "unsupported_body"
    part["text"] = '<html><head><title>'+sentence+'</title></head><body>No visible payment.</body></html>'
    assert parse_notice(decoded).reason == "unsupported_body"
    part["text"] = '<script>'+sentence+'</script>'+sentence
    assert parse_notice(decoded).disposition == "candidate"


@pytest.fixture
def review_db(migrated_postgres_url):
    sessions = session_factory_for(migrated_postgres_url)
    with sessions.begin() as session:
        session.execute(text("TRUNCATE plans, jobs CASCADE"))
    api = TestClient(create_app(Settings(database_url=migrated_postgres_url)))
    plan, source = uuid4(), uuid4()
    assert api.put(f"/plans/{plan}", json={"name": "Review test", "reporting_currency_code": "BOB", "budget_timezone": "America/La_Paz"}).status_code == 201
    assert api.put(f"/plans/{plan}/accounts/{uuid4()}", json={"name": "Unmapped USDT", "account_type": "Crypto", "currency_code": "USDT"}).status_code == 201
    with sessions.begin() as session:
        session.add(GmailSource(id=source, plan_id=plan, status="disconnected", email="synthetic@example.invalid", allowed_senders=["do-not-reply@ses.binance.com"]))
    yield api, sessions, plan, source


def add_message(sessions, source, *, sample=None, gmail_id=None):
    raw = raw_notice(sample)
    with sessions.begin() as session:
        message = GmailMessage(source_id=source, gmail_id=gmail_id or uuid4().hex, raw_mime=raw, decoded=decode_message(raw), provider_metadata={"id": "synthetic"}, status="decoded")
        session.add(message)
        session.flush()
        return message.id


def financial_counts(sessions):
    with sessions() as session:
        return session.execute(text("SELECT (SELECT count(*) FROM transactions), (SELECT count(*) FROM posted_account_movements), (SELECT count(*) FROM monthly_budget_assignments)")).one()


def test_backfill_idempotency_pagination_plan_isolation_and_no_financial_mutation(review_db):
    api, sessions, plan, source = review_db
    ids = [add_message(sessions, source, sample=sample) for sample in SAMPLES]
    before = financial_counts(sessions)
    assert process_pending(sessions, limit=2) == 2
    assert process_pending(sessions, limit=2) == 2
    assert process_pending(sessions) == 0
    with sessions.begin() as session:
        record_message(session, session.get(GmailMessage, ids[0]))
    endpoint = f"/plans/{plan}/gmail/binance-card-reviews"
    response = api.get(endpoint, params={"limit": 2})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    first = response.json()
    assert first["candidate_count"] == 3 and first["needs_review_count"] == 0
    assert len(first["items"]) == 2
    second = api.get(endpoint, params={"after": first["next_after"], "limit": 2}).json()
    assert [row["id"] for row in first["items"] + second["items"]] == ids[:3]
    assert second["next_after"] is None
    for row in first["items"] + second["items"]:
        assert isinstance(row["reported_amount"], str)
        assert row["reported_currency"] == "USD"
        assert row["settlement_amount"] is row["settlement_currency"] is row["account_id"] is None
        assert row["provenance"]["source_id"] == str(source)
        assert "raw_mime" not in row and "decoded" not in row
    other = uuid4()
    assert api.put(f"/plans/{other}", json={"name": "Other", "reporting_currency_code": "BOB", "budget_timezone": "America/La_Paz"}).status_code == 201
    assert api.get(f"/plans/{other}/gmail/binance-card-reviews").json()["items"] == []
    assert api.get(f"/plans/{uuid4()}/gmail/binance-card-reviews").status_code == 404
    assert api.get(endpoint, params={"limit": 101}).status_code == 422
    assert api.post(endpoint, json={}).status_code == 405
    assert financial_counts(sessions) == before


def test_concurrent_processing_and_separate_gmail_messages_are_not_destructively_merged(review_db):
    _, sessions, _, source = review_db
    ids = [add_message(sessions, source) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: process_pending(sessions), range(2))) == 8
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(BinanceCardReview)) == 8
        assert [message.raw_mime for message in session.scalars(select(GmailMessage).order_by(GmailMessage.id))] == [raw_notice()] * 8
        assert {r.message_id for r in session.scalars(select(BinanceCardReview))} == set(ids)
    assert process_pending(sessions) == 0
    assert financial_counts(sessions) == (0, 0, 0)


def test_review_records_immutable_and_nullable_currency_cannot_bypass_candidate_constraint(review_db):
    _, sessions, _, source = review_db
    mid = add_message(sessions, source)
    assert process_pending(sessions) == 1
    with sessions() as session:
        with pytest.raises(DBAPIError), session.begin():
            session.execute(text("UPDATE binance_card_reviews SET reported_amount='1.00' WHERE message_id=:mid"), {"mid": mid})
    mid2 = add_message(sessions, source)
    with sessions() as session:
        with pytest.raises(DBAPIError), session.begin():
            session.execute(text("""INSERT INTO binance_card_reviews
              (message_id, parser_version, disposition, reason, reported_amount, merchant, event_at, notification_at)
              VALUES (:mid, 'synthetic', 'candidate', 'settlement_unresolved', '1.00', 'SYNTHETIC', now(), now())"""), {"mid": mid2})


def test_new_ingestion_is_atomic_replay_safe_and_does_not_post(review_db):
    _, sessions, _, source_id = review_db
    class Provider:
        calls = 0
        def get(self, _token, _path, **kwargs):
            self.calls += 1
            if kwargs["format"] == "metadata":
                return {"id": "synthetic-new", "labelIds": ["INBOX"], "payload": {"headers": [{"name": "From", "value": "do-not-reply@ses.binance.com"}]}}
            return {"id": "synthetic-new", "raw": base64.urlsafe_b64encode(raw_notice()).decode()}
    provider = Provider()
    with pytest.raises(RuntimeError), sessions.begin() as session:
        _store_message(session, session.get(GmailSource, source_id), provider, "synthetic-token", "synthetic-new")
        assert session.scalar(select(func.count()).select_from(BinanceCardReview)) == 1
        raise RuntimeError("Synthetic page failure")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 0
        assert session.scalar(select(func.count()).select_from(BinanceCardReview)) == 0
    with sessions.begin() as session:
        _store_message(session, session.get(GmailSource, source_id), provider, "synthetic-token", "synthetic-new")
    with sessions.begin() as session:
        _store_message(session, session.get(GmailSource, source_id), provider, "synthetic-token", "synthetic-new")
        assert session.scalar(select(func.count()).select_from(BinanceCardReview)) == 1
        assert session.scalar(select(BinanceCardReview.disposition)) == "candidate"
    assert provider.calls == 4
    assert process_pending(sessions) == 0
    assert financial_counts(sessions) == (0, 0, 0)


def test_same_headers_in_separate_mailboxes_retain_both_sources(review_db):
    _, sessions, plan, source = review_db
    other_source = uuid4()
    with sessions.begin() as session:
        session.add(GmailSource(id=other_source, plan_id=plan, status="disconnected", email="other-synthetic@example.invalid", allowed_senders=["do-not-reply@ses.binance.com"]))
    first = add_message(sessions, source, gmail_id="same-gmail-id")
    second = add_message(sessions, other_source, gmail_id="same-gmail-id")
    assert process_pending(sessions) == 2
    with sessions() as session:
        rows = session.scalars(select(BinanceCardReview)).all()
        assert {row.message_id for row in rows} == {first, second}
        assert {row.header_message_id for row in rows} == {SAMPLES[0]["message_id"]}
    assert financial_counts(sessions) == (0, 0, 0)


def test_unrecognized_card_subject_requires_review_with_no_claimed_financial_fields(review_db):
    api, sessions, plan, source = review_db
    sample = deepcopy(SAMPLES[0]); sample["subject"] = "Binance Card - Refund"
    add_message(sessions, source, sample=sample)
    process_pending(sessions)
    response = api.get(f"/plans/{plan}/gmail/binance-card-reviews").json()
    assert response["candidate_count"] == 0 and response["needs_review_count"] == 1
    item = response["items"][0]
    assert item["reported_amount"] is item["event_at"] is None
    assert item["reason"] == "unsupported_subject"
    assert financial_counts(sessions) == (0, 0, 0)
