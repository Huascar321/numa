from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Account, Plan
from app.db import session_factory_for
from app.ledger.models import Category, Transaction
from app.main import create_app
from app.settings import Settings
from app.watchers.binance_card import (
    BINANCE_CARD_SENDER,
    extract_merchant,
    extract_provider_uuid,
    extract_sender_address,
    parse_binance_card_message,
)
from app.watchers.models import (
    WatcherAccountMapping,
    WatcherCandidate,
    WatcherRawMessage,
    WatcherSource,
)
from app.watchers.schemas import (
    CreateAccountMappingRequest,
    ResolveCandidateRequest,
)
from app.watchers.service import (
    create_watcher_account_mapping,
    delete_watcher_account_mapping,
    get_watcher_candidate,
    ignore_candidate,
    list_watcher_account_mappings,
    list_watcher_candidates,
    process_plan_binance_card_messages,
    process_raw_message_for_binance_card,
    resolve_candidate,
)


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_watchers_db(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE watcher_candidates, watcher_account_mappings, "
        "watcher_raw_messages, watcher_sources, "
        "reconciliation_sessions, transfer_legs, transfers, "
        "transaction_tags, posted_account_movements, transaction_corrections, "
        "monthly_budget_assignments, transactions, tags, categories, "
        "category_groups, accounts, plans CASCADE"
    )
    with postgres_sessions.begin() as session:
        session.execute(statement)
    yield


@pytest.fixture
def configured_settings(migrated_postgres_url: str) -> Settings:
    return Settings(
        database_url=migrated_postgres_url,
        gmail_client_id="test-client-id.apps.googleusercontent.com",
        gmail_client_secret="test-client-secret",
        token_encryption_key="test-encryption-key-for-unit-tests",
    )


@pytest.fixture
def client(configured_settings: Settings) -> TestClient:
    return TestClient(create_app(configured_settings))


def create_test_plan(client: TestClient) -> str:
    plan_id = str(uuid4())
    resp = client.put(
        f"/plans/{plan_id}",
        json={
            "name": "Binance Watcher Test Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": "America/La_Paz",
        },
    )
    assert resp.status_code == 201
    return plan_id


def create_test_account(
    client: TestClient,
    plan_id: str,
    name: str = "Binance Funding",
    currency_code: str = "USDT",
    account_type: str = "Crypto",
) -> str:
    account_id = str(uuid4())
    resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={
            "name": name,
            "account_type": account_type,
            "currency_code": currency_code,
        },
    )
    assert resp.status_code == 201
    return account_id


def make_raw_message(
    session: Session,
    plan_id: UUID,
    source_id: UUID,
    sender: str = "Binance <do-not-reply@ses.binance.com>",
    subject: str = "Binance Card - You have spent 15.50 USD on 2026-08-24 14:30:00 (UTC)",
    body_plain: str = "You have spent 15.50 USD at Uber with your Binance Card.",
    body_html: str = "<html><body><p>You have spent 15.50 USD at Uber with your Binance Card.</p><!-- uuid: 12345678-1234-5678-1234-567812345678 --></body></html>",
    date_header: str = "Mon, 24 Aug 2026 14:31:00 +0000",
    message_id_header: str = "<binance-notice-001@ses.binance.com>",
    external_id: str = "ext-msg-1",
) -> WatcherRawMessage:
    raw_message = WatcherRawMessage(
        id=uuid4(),
        plan_id=plan_id,
        source_id=source_id,
        external_message_id=external_id,
        external_thread_id="thread-1",
        internal_date=datetime(2026, 8, 24, 14, 31, 0, tzinfo=timezone.utc),
        history_id="100",
        sender=sender,
        recipient="user@example.com",
        subject=subject,
        snippet="You have spent 15.50 USD at Uber",
        raw_headers={
            "from": sender,
            "subject": subject,
            "date": date_header,
            "message-id": message_id_header,
        },
        body_plain=body_plain,
        body_html=body_html,
        mime_metadata={},
        provenance={"message_id": message_id_header},
        status="pending",
        creation_fingerprint=f"{source_id}:{external_id}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(raw_message)
    session.flush()
    return raw_message


def make_test_source(session: Session, plan_id: UUID) -> WatcherSource:
    source = WatcherSource(
        id=uuid4(),
        plan_id=plan_id,
        source_type="gmail",
        email_address="user@example.com",
        encrypted_refresh_token="v1:test-encrypted-token",
        status="active",
        creation_fingerprint=f"gmail:{uuid4()}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(source)
    session.flush()
    return source


# ---------------------------------------------------------------------------
# 1. Parser Unit Tests: Sender, Subject, UTC Event Time, Merchant, UUID
# ---------------------------------------------------------------------------


def test_binance_card_parser_exact_contract(postgres_sessions: sessionmaker[Session]):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="Parser Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="fp1",
        )
        session.add(plan)
        session.flush()
        source = make_test_source(session, plan.id)

        raw_msg = make_raw_message(
            session=session,
            plan_id=plan.id,
            source_id=source.id,
            sender="Binance <do-not-reply@ses.binance.com>",
            subject="Binance Card - You have spent 15.50 USD on 2026-08-24 14:30:00 (UTC)",
            body_plain="You have spent 15.50 USD at Uber with your Binance Card.",
            body_html="<html><body><p>You have spent 15.50 USD at Uber with your Binance Card.</p><!-- uuid: 98765432-1234-5678-1234-567812345678 --></body></html>",
            date_header="Mon, 24 Aug 2026 14:32:00 +0000",
            message_id_header="<msg-binance-xyz@ses.binance.com>",
        )

        result = parse_binance_card_message(raw_msg)
        assert result.is_binance_card is True
        assert result.reported_amount == Decimal("15.50")
        # Invariant: Reported USD is preserved and distinct from USDT
        assert result.reported_currency == "USD"
        # Invariant: Subject timestamp is event time in UTC
        assert result.event_at == datetime(2026, 8, 24, 14, 30, 0, tzinfo=timezone.utc)
        # Invariant: Date header is notification time
        assert result.notification_at == datetime(2026, 8, 24, 14, 32, 0, tzinfo=timezone.utc)
        assert result.merchant == "Uber"
        # Invariant: Provider UUID extracted as candidate metadata
        assert result.provider_uuid == "98765432-1234-5678-1234-567812345678"
        assert result.message_id_header == "<msg-binance-xyz@ses.binance.com>"


def test_binance_card_parser_rejection_of_non_matching():
    # Sender mismatch
    assert extract_sender_address("Binance Security <security@binance.com>") != BINANCE_CARD_SENDER
    assert extract_sender_address("phishing@ses.binance.com.attacker.com") != BINANCE_CARD_SENDER

    # Test parser with non-matching sender
    mock_msg_wrong_sender = MagicMock(spec=WatcherRawMessage)
    mock_msg_wrong_sender.sender = "Binance News <news@binance.com>"
    mock_msg_wrong_sender.subject = "Binance Card - You have spent 15.50 USD on 2026-08-24 14:30:00 (UTC)"
    mock_msg_wrong_sender.raw_headers = {}
    mock_msg_wrong_sender.provenance = {}
    res = parse_binance_card_message(mock_msg_wrong_sender)
    assert res.is_binance_card is False

    # Subject mismatch
    mock_msg_wrong_subject = MagicMock(spec=WatcherRawMessage)
    mock_msg_wrong_subject.sender = "do-not-reply@ses.binance.com"
    mock_msg_wrong_subject.subject = "Binance Card - Statement Available"
    mock_msg_wrong_subject.raw_headers = {}
    mock_msg_wrong_subject.provenance = {}
    res = parse_binance_card_message(mock_msg_wrong_subject)
    assert res.is_binance_card is False


# ---------------------------------------------------------------------------
# 2. USD Preservation & Unresolved Settlement Quarantine
# ---------------------------------------------------------------------------


def test_unresolved_settlement_creates_quarantined_candidate(
    postgres_sessions: sessionmaker[Session],
):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="Quarantine Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="fp-quarantine",
        )
        session.add(plan)
        session.flush()
        source = make_test_source(session, plan.id)

        raw_msg = make_raw_message(
            session=session,
            plan_id=plan.id,
            source_id=source.id,
            subject="Binance Card - You have spent 42.00 USD on 2026-08-24 18:00:00 (UTC)",
            body_plain="You have spent 42.00 USD at Starbucks with your Binance Card.",
        )

        # Process message without authoritative mapping
        candidate = process_raw_message_for_binance_card(session, raw_msg)
        assert candidate is not None
        session.commit()

        assert candidate.status == "quarantined"
        assert candidate.reported_amount == Decimal("42.00")
        # Invariant: Reported currency remains USD without assuming USDT
        assert candidate.reported_currency == "USD"
        assert candidate.settlement_amount is None
        assert candidate.settlement_currency is None
        assert candidate.transaction_id is None
        assert "Settlement unresolved: reported USD requires authoritative account mapping" in (
            candidate.quarantine_reason or ""
        )

        # Raw message status updated to quarantined
        updated_msg = session.get(WatcherRawMessage, raw_msg.id)
        assert updated_msg is not None
        assert updated_msg.status == "quarantined"


# ---------------------------------------------------------------------------
# 3. Authoritative Mapping: Auto-Resolve & Pending Review
# ---------------------------------------------------------------------------


def test_authoritative_mapping_auto_resolves_to_transaction(
    postgres_sessions: sessionmaker[Session],
):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="Auto Resolve Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="fp-autoresolve",
        )
        session.add(plan)
        session.flush()

        # Create USDT wallet account
        account = Account(
            id=uuid4(),
            plan_id=plan.id,
            name="Binance USDT Funding",
            account_type="Crypto",
            currency_code="USDT",
            status="active",
            creation_fingerprint="acc-fp",
        )
        session.add(account)
        session.flush()

        # Create protected pending category
        cat = Category(
            id=uuid4(),
            plan_id=plan.id,
            group_id=None,
            name="Pendientes",
            is_pending=True,
            status="active",
            creation_fingerprint="cat-fp",
        )
        session.add(cat)
        session.flush()

        # Authoritative account mapping with auto_resolve=True
        mapping = create_watcher_account_mapping(
            session=session,
            plan_id=plan.id,
            payload=CreateAccountMappingRequest(
                source_type="binance_card",
                pattern="*",
                account_id=account.id,
                default_category_id=cat.id,
                auto_resolve=True,
            ),
        )
        session.flush()

        source = make_test_source(session, plan.id)
        raw_msg = make_raw_message(
            session=session,
            plan_id=plan.id,
            source_id=source.id,
            subject="Binance Card - You have spent 25.00 USD on 2026-08-24 10:00:00 (UTC)",
            body_plain="You have spent 25.00 USD at Steam with your Binance Card.",
        )

        candidate = process_raw_message_for_binance_card(session, raw_msg)
        assert candidate is not None
        session.commit()

        # Candidate is resolved
        assert candidate.status == "resolved"
        assert candidate.reported_amount == Decimal("25.00")
        assert candidate.reported_currency == "USD"
        assert candidate.settlement_amount == Decimal("25.00")
        assert candidate.settlement_currency == "USDT"
        assert candidate.transaction_id is not None

        # Verify posted Transaction
        tx = session.get(Transaction, candidate.transaction_id)
        assert tx is not None
        assert tx.account_id == account.id
        assert tx.amount == Decimal("25.00")
        assert tx.currency_code == "USDT"
        assert tx.type == "expense"
        assert tx.merchant == "Steam"
        assert tx.provenance["source"] == "watcher:binance_card"


# ---------------------------------------------------------------------------
# 4. Manual Review & Resolution of Quarantined Candidate
# ---------------------------------------------------------------------------


def test_manual_resolution_of_quarantined_candidate(
    postgres_sessions: sessionmaker[Session],
):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="Manual Review Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="fp-manual",
        )
        session.add(plan)
        session.flush()

        account = Account(
            id=uuid4(),
            plan_id=plan.id,
            name="Binance Card Wallet",
            account_type="Crypto",
            currency_code="USDT",
            status="active",
            creation_fingerprint="acc-fp-2",
        )
        session.add(account)
        session.flush()

        cat = Category(
            id=uuid4(),
            plan_id=plan.id,
            group_id=None,
            name="Pendientes",
            is_pending=True,
            status="active",
            creation_fingerprint="cat-fp-2",
        )
        session.add(cat)
        session.flush()

        source = make_test_source(session, plan.id)
        raw_msg = make_raw_message(
            session=session,
            plan_id=plan.id,
            source_id=source.id,
            subject="Binance Card - You have spent 10.00 USD on 2026-08-24 12:00:00 (UTC)",
            body_plain="You have spent 10.00 USD at Spotify with your Binance Card.",
        )

        candidate = process_raw_message_for_binance_card(session, raw_msg)
        assert candidate is not None
        assert candidate.status == "quarantined"
        session.commit()
        candidate_id = candidate.id

    # Resolve manually
    with postgres_sessions() as session:
        resolved = resolve_candidate(
            session=session,
            plan_id=plan.id,
            candidate_id=candidate_id,
            payload=ResolveCandidateRequest(
                account_id=account.id,
                category_id=cat.id,
                settlement_amount=Decimal("10.00"),
                settlement_currency="USDT",
                memo="Spotify Subscription",
            ),
        )
        session.commit()

        assert resolved.status == "resolved"
        assert resolved.reported_currency == "USD"
        assert resolved.settlement_amount == Decimal("10.00")
        assert resolved.settlement_currency == "USDT"
        assert resolved.transaction_id is not None
        assert resolved.quarantine_reason is None

        tx = session.get(Transaction, resolved.transaction_id)
        assert tx is not None
        assert tx.account_id == account.id
        assert tx.amount == Decimal("10.00")
        assert tx.currency_code == "USDT"
        assert tx.memo == "Spotify Subscription"


# ---------------------------------------------------------------------------
# 5. Idempotency of Candidate Ingestion & Processing
# ---------------------------------------------------------------------------


def test_candidate_creation_and_processing_is_idempotent(
    postgres_sessions: sessionmaker[Session],
):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="Idempotency Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="fp-idempotent",
        )
        session.add(plan)
        session.flush()
        source = make_test_source(session, plan.id)

        raw_msg = make_raw_message(
            session=session,
            plan_id=plan.id,
            source_id=source.id,
            subject="Binance Card - You have spent 50.00 USD on 2026-08-24 15:00:00 (UTC)",
            body_plain="You have spent 50.00 USD at Amazon with your Binance Card.",
        )

        # 1. First processing pass
        c1 = process_raw_message_for_binance_card(session, raw_msg)
        assert c1 is not None
        session.commit()

        candidates_1 = list_watcher_candidates(session, plan.id)
        assert len(candidates_1) == 1

        # 2. Second processing pass on same raw message -> returns exact same candidate
        c2 = process_raw_message_for_binance_card(session, raw_msg)
        assert c2 is not None
        assert c2.id == c1.id
        session.commit()

        candidates_2 = list_watcher_candidates(session, plan.id)
        assert len(candidates_2) == 1

        # 3. Batch processing endpoint on plan -> 0 new candidates created
        batch_resp = process_plan_binance_card_messages(session, plan.id)
        assert batch_resp.candidates_created == 0


# ---------------------------------------------------------------------------
# 6. REST API Endpoints Lifecycle
# ---------------------------------------------------------------------------


def test_binance_card_watcher_api_endpoints(
    client: TestClient,
    postgres_sessions: sessionmaker[Session],
):
    plan_id = create_test_plan(client)
    account_id = create_test_account(client, plan_id, name="Crypto USDT", currency_code="USDT")

    # Ingest a raw Binance Card message directly in DB
    with postgres_sessions() as session:
        source = make_test_source(session, UUID(plan_id))
        raw_msg = make_raw_message(
            session=session,
            plan_id=UUID(plan_id),
            source_id=source.id,
            subject="Binance Card - You have spent 18.25 USD on 2026-08-24 20:15:00 (UTC)",
            body_plain="You have spent 18.25 USD at Target with your Binance Card.",
        )
        session.commit()
        msg_id = str(raw_msg.id)

    # 1. Trigger candidate processing via REST API
    proc_resp = client.post(f"/plans/{plan_id}/watchers/candidates/process")
    assert proc_resp.status_code == 200
    proc_data = proc_resp.json()
    assert proc_data["processed_count"] == 1
    assert proc_data["candidates_created"] == 1
    assert proc_data["candidates_quarantined"] == 1

    # 2. List candidates
    list_resp = client.get(f"/plans/{plan_id}/watchers/candidates")
    assert list_resp.status_code == 200
    candidates_list = list_resp.json()
    assert len(candidates_list) == 1
    candidate = candidates_list[0]
    assert candidate["merchant"] == "Target"
    assert candidate["reported_amount"] == "18.250000000000000000" or float(candidate["reported_amount"]) == 18.25
    assert candidate["reported_currency"] == "USD"
    assert candidate["status"] == "quarantined"
    candidate_id = candidate["id"]

    # 3. Get candidate detail
    detail_resp = client.get(f"/plans/{plan_id}/watchers/candidates/{candidate_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == candidate_id

    # 4. Resolve candidate via REST API
    resolve_resp = client.post(
        f"/plans/{plan_id}/watchers/candidates/{candidate_id}/resolve",
        json={
            "account_id": account_id,
            "settlement_amount": "18.25",
            "settlement_currency": "USDT",
            "memo": "Target Purchase",
        },
    )
    assert resolve_resp.status_code == 200
    resolved_data = resolve_resp.json()
    assert resolved_data["status"] == "resolved"
    assert resolved_data["transaction_id"] is not None

    # 5. Verify Transaction in Ledger
    txs_resp = client.get(f"/plans/{plan_id}/transactions")
    assert txs_resp.status_code == 200
    txs = txs_resp.json()
    assert len(txs) == 1
    assert txs[0]["account_id"] == account_id
    assert txs[0]["currency_code"] == "USDT"

    # 6. Create Account Mapping via REST API
    map_resp = client.post(
        f"/plans/{plan_id}/watchers/mappings",
        json={
            "source_type": "binance_card",
            "pattern": "*",
            "account_id": account_id,
            "auto_resolve": False,
        },
    )
    assert map_resp.status_code == 201
    mapping_data = map_resp.json()
    assert mapping_data["source_type"] == "binance_card"
    mapping_id = mapping_data["id"]

    # 7. List Mappings
    maps_resp = client.get(f"/plans/{plan_id}/watchers/mappings")
    assert maps_resp.status_code == 200
    assert len(maps_resp.json()) == 1

    # 8. Delete Mapping
    del_resp = client.post(f"/plans/{plan_id}/watchers/mappings/{mapping_id}/delete")
    assert del_resp.status_code == 204
