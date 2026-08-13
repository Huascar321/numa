from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.accounts import Account, Plan
from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_accounts(postgres_sessions: sessionmaker[Session]):
    with postgres_sessions.begin() as session:
        session.execute(delete(Account))
        session.execute(delete(Plan))
    yield
    with postgres_sessions.begin() as session:
        session.execute(delete(Account))
        session.execute(delete(Plan))


@pytest.fixture
def client(migrated_postgres_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=migrated_postgres_url)))


def _create_plan(client: TestClient, *, name: str = "Plan") -> tuple[str, dict]:
    plan_id = str(uuid4())
    response = client.put(
        f"/plans/{plan_id}",
        json={"name": name, "reporting_currency_code": "BOB"},
    )
    assert response.status_code == 201
    return plan_id, response.json()


def test_currencies_and_plan_endpoints_have_authoritative_contracts(
    client: TestClient,
) -> None:
    currencies = client.get("/currencies")
    assert currencies.status_code == 200
    assert currencies.json() == [
        {"code": "BOB", "decimal_places": 2},
        {"code": "USDT", "decimal_places": 6},
    ]

    plan_id, plan = _create_plan(client)
    assert plan["id"] == plan_id
    assert plan["reporting_currency_code"] == "BOB"

    assert client.get("/plans").json() == [plan]
    assert client.get(f"/plans/{plan_id}").json() == plan

    renamed = client.patch(f"/plans/{plan_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["reporting_currency_code"] == "BOB"

    replay = client.put(
        f"/plans/{plan_id}",
        json={"name": "Plan", "reporting_currency_code": "BOB"},
    )
    assert replay.status_code == 200
    assert replay.json()["name"] == "Renamed"

    conflict = client.put(
        f"/plans/{plan_id}",
        json={"name": "Other", "reporting_currency_code": "USDT"},
    )
    assert conflict.status_code == 409
    assert client.get(f"/plans/{plan_id}").json()["name"] == "Renamed"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Plan", "reporting_currency_code": "BOB", "balance": "0.00"},
        {"name": "Plan", "reporting_currency_code": "BOB", "opening_balance": "0.00"},
        {"name": "Plan", "reporting_currency_code": "BOB", "currency_change": "USDT"},
        {"name": "Plan", "reporting_currency_code": "BOB", "tipo": "Bank"},
        {"name": "Plan", "reporting_currency_code": "BOB", "Plan": "other"},
    ],
)
def test_plan_create_rejects_additional_financial_or_identity_fields(
    client: TestClient,
    payload: dict,
) -> None:
    response = client.put(f"/plans/{uuid4()}", json=payload)

    assert response.status_code == 422


def test_account_endpoints_cover_replay_rename_archive_and_exact_balances(
    client: TestClient,
) -> None:
    plan_id, _ = _create_plan(client)
    account_id = str(uuid4())
    payload = {
        "name": "Cash account",
        "account_type": "Cash",
        "currency_code": "BOB",
    }
    created = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json=payload,
    )
    assert created.status_code == 201
    assert created.json()["balance"] == {"amount": "0.00", "currency": "BOB"}
    assert isinstance(created.json()["balance"]["amount"], str)

    replay = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json=payload,
    )
    assert replay.status_code == 200

    renamed = client.patch(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={"name": "Renamed cash"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed cash"

    archived = client.post(f"/plans/{plan_id}/accounts/{account_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    repeated = client.post(f"/plans/{plan_id}/accounts/{account_id}/archive")
    assert repeated.status_code == 200
    assert repeated.json() == archived.json()

    archived_rename = client.patch(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={"name": "Must fail"},
    )
    assert archived_rename.status_code == 409
    assert client.get(f"/plans/{plan_id}/accounts/{account_id}").json() == archived.json()
    assert client.get(f"/plans/{plan_id}/accounts").json() == [archived.json()]

    usdt_id = str(uuid4())
    usdt = client.put(
        f"/plans/{plan_id}/accounts/{usdt_id}",
        json={
            "name": "Crypto account",
            "account_type": "Crypto",
            "currency_code": "USDT",
        },
    )
    assert usdt.status_code == 201
    assert usdt.json()["balance"] == {
        "amount": "0.000000",
        "currency": "USDT",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "Account",
            "account_type": "Bank",
            "currency_code": "USD",
        },
        {
            "name": "Account",
            "account_type": "bank",
            "currency_code": "BOB",
        },
        {
            "name": "Account",
            "account_type": "Bank",
            "currency_code": "BOB",
            "balance": 1.5,
        },
        {
            "name": "Account",
            "account_type": "Bank",
            "currency_code": "BOB",
            "opening_balance": "1.00",
        },
        {
            "name": "Account",
            "account_type": "Bank",
            "currency_code": "BOB",
            "currency_change": "USDT",
        },
        {
            "name": "Account",
            "account_type": "Bank",
            "currency_code": "BOB",
            "tipo": "Cash",
        },
        {
            "name": "Account",
            "account_type": "Bank",
            "currency_code": "BOB",
            "Plan": str(uuid4()),
        },
    ],
)
def test_account_create_rejects_unknown_or_additional_fields(
    client: TestClient,
    payload: dict,
) -> None:
    plan_id, _ = _create_plan(client)
    response = client.put(
        f"/plans/{plan_id}/accounts/{uuid4()}",
        json=payload,
    )

    assert response.status_code == 422


def test_account_identity_is_immutable_and_cross_plan_access_is_not_found(
    client: TestClient,
) -> None:
    plan_a, _ = _create_plan(client, name="Plan A")
    plan_b, _ = _create_plan(client, name="Plan B")
    account_id = str(uuid4())
    created = client.put(
        f"/plans/{plan_a}/accounts/{account_id}",
        json={
            "name": "Account A",
            "account_type": "Wallet",
            "currency_code": "BOB",
        },
    )
    assert created.status_code == 201

    assert client.get(f"/plans/{plan_b}/accounts/{account_id}").status_code == 404
    assert (
        client.patch(
            f"/plans/{plan_b}/accounts/{account_id}",
            json={"name": "Leaked"},
        ).status_code
        == 404
    )
    assert client.post(f"/plans/{plan_b}/accounts/{account_id}/archive").status_code == 404

    original = client.get(f"/plans/{plan_a}/accounts/{account_id}").json()
    assert original["name"] == "Account A"
    assert original["account_type"] == "Wallet"
    assert original["currency_code"] == "BOB"
    assert original["status"] == "active"

    conflict = client.put(
        f"/plans/{plan_a}/accounts/{account_id}",
        json={
            "name": "Account A",
            "account_type": "Wallet",
            "currency_code": "USDT",
        },
    )
    assert conflict.status_code == 409
    assert client.get(f"/plans/{plan_a}/accounts/{account_id}").json() == original


def test_no_delete_or_currency_admin_routes_exist(client: TestClient) -> None:
    plan_id, _ = _create_plan(client)
    account_id = str(uuid4())

    assert client.delete(f"/plans/{plan_id}").status_code == 405
    assert client.delete(f"/plans/{plan_id}/accounts/{account_id}").status_code == 405
    assert client.post("/currencies").status_code == 405
    assert client.patch("/currencies/BOB").status_code in {404, 405}
    assert client.delete("/currencies/BOB").status_code in {404, 405}
