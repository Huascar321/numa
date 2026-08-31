from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_factory_for
from app.ledger.models import (
    Category,
    PostedAccountMovement,
    ReconciliationSession,
    Transaction,
)
from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE reconciliation_sessions, transfer_legs, transfers, transaction_tags, posted_account_movements, "
        "transaction_corrections, monthly_budget_assignments, transactions, "
        "tags, categories, category_groups, accounts, plans CASCADE"
    )
    with postgres_sessions.begin() as session:
        session.execute(statement)
    yield


@pytest.fixture
def client(migrated_postgres_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=migrated_postgres_url)))


def setup_plan_and_account(
    client: TestClient, *, currency: str = "BOB"
) -> tuple[str, str, str]:
    plan_id = str(uuid4())
    account_id = str(uuid4())
    plan_resp = client.put(
        f"/plans/{plan_id}",
        json={
            "name": "Reconciliation Plan",
            "reporting_currency_code": currency,
            "budget_timezone": "America/La_Paz",
        },
    )
    assert plan_resp.status_code == 201
    account_resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={
            "name": "Checking Account",
            "account_type": "Bank",
            "currency_code": currency,
        },
    )
    assert account_resp.status_code == 201

    # Find the protected Pendientes category
    categories = client.get(f"/plans/{plan_id}/categories").json()
    pending_cat = next(c for c in categories if c["is_pending"])
    return plan_id, account_id, pending_cat["id"]


def post_income(
    client: TestClient,
    plan_id: str,
    account_id: str,
    amount: str,
    *,
    event_at: str = "2026-08-10T12:00:00Z",
) -> str:
    tx_id = str(uuid4())
    resp = client.put(
        f"/plans/{plan_id}/transactions/{tx_id}",
        json={
            "type": "income",
            "account_id": account_id,
            "amount": amount,
            "currency_code": "BOB",
            "event_at": event_at,
        },
    )
    assert resp.status_code == 201
    return tx_id


def test_preview_reconciliation_zero_discrepancy_and_confirm_balanced(
    client: TestClient, migrated_postgres_url: str
) -> None:
    plan_id, account_id, _ = setup_plan_and_account(client)
    post_income(client, plan_id, account_id, "100.00")

    # Preview reconciliation with exact matching statement balance
    preview_resp = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["account_id"] == account_id
    assert preview["currency_code"] == "BOB"
    assert preview["statement_balance"] == "100.00"
    assert preview["derived_balance"] == "100.00"
    assert preview["discrepancy"] == "0.00"
    assert preview["status"] == "balanced"

    # Verify preview is strictly side-effect free
    factory = session_factory_for(migrated_postgres_url)
    with factory() as session:
        count = session.scalar(
            select(text("count(*)")).select_from(ReconciliationSession)
        )
        assert count == 0

    # Confirm reconciliation
    rec_id = str(uuid4())
    confirm_resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00Z",
            "memo": "Clean balance reconciliation",
            "provenance": {"source": "manual_entry"},
        },
    )
    assert confirm_resp.status_code == 201
    session_data = confirm_resp.json()
    assert session_data["id"] == rec_id
    assert session_data["status"] == "balanced"
    assert session_data["statement_balance"] == "100.00"
    assert session_data["derived_balance"] == "100.00"
    assert session_data["discrepancy"] == "0.00"
    assert session_data["adjustment_transaction_id"] is None
    assert session_data["memo"] == "Clean balance reconciliation"

    # Verify no adjustment transaction was created
    with factory() as session:
        adj_count = session.scalar(
            select(text("count(*)")).select_from(Transaction).where(
                Transaction.type == "reconciliation_adjustment"
            )
        )
        assert adj_count == 0

    # Balance remains 100.00
    bal_resp = client.get(f"/plans/{plan_id}/accounts/{account_id}/balance").json()
    assert bal_resp["amount"] == "100.00"


def test_reconciliation_positive_discrepancy_creates_adjustment(
    client: TestClient, migrated_postgres_url: str
) -> None:
    plan_id, account_id, pending_id = setup_plan_and_account(client)
    post_income(client, plan_id, account_id, "100.00")

    # Statement has 125.50, derived is 100.00 -> discrepancy is +25.50
    preview_resp = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "125.50",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["discrepancy"] == "25.50"
    assert preview_resp.json()["status"] == "adjusted"

    rec_id = str(uuid4())
    confirm_resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json={
            "statement_balance": "125.50",
            "statement_date": "2026-08-15T12:00:00Z",
            "memo": "Found missing cash",
        },
    )
    assert confirm_resp.status_code == 201
    session_data = confirm_resp.json()
    assert session_data["status"] == "adjusted"
    assert session_data["discrepancy"] == "25.50"
    adj_tx_id = session_data["adjustment_transaction_id"]
    assert adj_tx_id is not None

    # Verify transaction and movement in database
    factory = session_factory_for(migrated_postgres_url)
    with factory() as session:
        adj_tx = session.get(Transaction, adj_tx_id)
        assert adj_tx is not None
        assert adj_tx.type == "reconciliation_adjustment"
        assert adj_tx.amount == Decimal("25.50")
        assert adj_tx.category_id == Decimal(0) or str(adj_tx.category_id) == pending_id
        assert adj_tx.source == "reconciliation"

        movement = session.scalar(
            select(PostedAccountMovement).where(
                PostedAccountMovement.transaction_id == adj_tx.id
            )
        )
        assert movement is not None
        assert movement.signed_amount == Decimal("25.50")
        assert movement.transaction_type == "reconciliation_adjustment"

    # Balance is now updated to 125.50
    bal_resp = client.get(f"/plans/{plan_id}/accounts/{account_id}/balance").json()
    assert bal_resp["amount"] == "125.50"


def test_reconciliation_negative_discrepancy_creates_negative_adjustment(
    client: TestClient, migrated_postgres_url: str
) -> None:
    plan_id, account_id, pending_id = setup_plan_and_account(client)
    post_income(client, plan_id, account_id, "100.00")

    # Statement has 70.00, derived is 100.00 -> discrepancy is -30.00
    preview_resp = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "70.00",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["discrepancy"] == "-30.00"
    assert preview_resp.json()["status"] == "adjusted"

    rec_id = str(uuid4())
    confirm_resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json={
            "statement_balance": "70.00",
            "statement_date": "2026-08-15T12:00:00Z",
            "memo": "Bank fee adjustment",
        },
    )
    assert confirm_resp.status_code == 201
    session_data = confirm_resp.json()
    assert session_data["status"] == "adjusted"
    assert session_data["discrepancy"] == "-30.00"
    adj_tx_id = session_data["adjustment_transaction_id"]

    factory = session_factory_for(migrated_postgres_url)
    with factory() as session:
        adj_tx = session.get(Transaction, adj_tx_id)
        assert adj_tx is not None
        assert adj_tx.type == "reconciliation_adjustment"
        assert adj_tx.amount == Decimal("30.00")  # Amount is positive abs value
        assert str(adj_tx.category_id) == pending_id

        movement = session.scalar(
            select(PostedAccountMovement).where(
                PostedAccountMovement.transaction_id == adj_tx.id
            )
        )
        assert movement is not None
        assert movement.signed_amount == Decimal("-30.00")  # Signed movement is negative

    # Balance is now updated to 70.00
    bal_resp = client.get(f"/plans/{plan_id}/accounts/{account_id}/balance").json()
    assert bal_resp["amount"] == "70.00"


def test_reconciliation_as_of_statement_date_boundary(client: TestClient) -> None:
    plan_id, account_id, _ = setup_plan_and_account(client)
    # Movement 1: Aug 10, +100
    post_income(client, plan_id, account_id, "100.00", event_at="2026-08-10T12:00:00Z")
    # Movement 2: Aug 20, +50
    post_income(client, plan_id, account_id, "50.00", event_at="2026-08-20T12:00:00Z")

    # Reconcile as of Aug 15 -> should only see +100
    preview_resp = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["derived_balance"] == "100.00"
    assert preview_resp.json()["discrepancy"] == "0.00"
    assert preview_resp.json()["status"] == "balanced"


def test_reconciliation_client_uuid_idempotency(client: TestClient) -> None:
    plan_id, account_id, _ = setup_plan_and_account(client)
    post_income(client, plan_id, account_id, "50.00")

    rec_id = str(uuid4())
    payload = {
        "statement_balance": "50.00",
        "statement_date": "2026-08-15T12:00:00Z",
        "memo": "Idempotent check",
    }
    first = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json=payload,
    )
    replay = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json=payload,
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json() == replay.json()

    # Different payload with same UUID returns 409
    conflict = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json={**payload, "statement_balance": "60.00"},
    )
    assert conflict.status_code == 409


def test_reconciliation_validations_and_timezone_checks(client: TestClient) -> None:
    plan_id, account_id, _ = setup_plan_and_account(client)

    # Naive timestamp rejected
    naive_preview = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00",
        },
    )
    assert naive_preview.status_code == 422

    # Excess decimal scale rejected
    excess_scale = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "100.005",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert excess_scale.status_code == 422

    # Non-existent plan
    non_existent = client.post(
        f"/plans/{uuid4()}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert non_existent.status_code == 404

    # Archived account rejected
    client.post(f"/plans/{plan_id}/accounts/{account_id}/archive")
    archived = client.post(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/preview",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    assert archived.status_code == 422


def test_reconciliation_history_list_and_get(client: TestClient) -> None:
    plan_id, account_id, _ = setup_plan_and_account(client)
    post_income(client, plan_id, account_id, "100.00")

    rec1 = str(uuid4())
    client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec1}",
        json={
            "statement_balance": "100.00",
            "statement_date": "2026-08-15T12:00:00Z",
            "memo": "First session",
        },
    )
    rec2 = str(uuid4())
    client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec2}",
        json={
            "statement_balance": "120.00",
            "statement_date": "2026-08-20T12:00:00Z",
            "memo": "Second session",
        },
    )

    history = client.get(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations"
    ).json()
    assert len(history) == 2
    assert [h["id"] for h in history] == [rec2, rec1]

    single = client.get(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec1}"
    ).json()
    assert single["id"] == rec1
    assert single["memo"] == "First session"


def test_reconciliation_adjustment_transaction_cannot_be_corrected(
    client: TestClient,
) -> None:
    plan_id, account_id, _ = setup_plan_and_account(client)
    post_income(client, plan_id, account_id, "100.00")

    rec_id = str(uuid4())
    confirm_resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{rec_id}",
        json={
            "statement_balance": "110.00",
            "statement_date": "2026-08-15T12:00:00Z",
        },
    )
    adj_tx_id = confirm_resp.json()["adjustment_transaction_id"]

    # Attempt to correct the reconciliation adjustment transaction
    correction_resp = client.put(
        f"/plans/{plan_id}/transactions/{adj_tx_id}/corrections/{uuid4()}",
        json={"amount": "15.00"},
    )
    assert correction_resp.status_code == 409
