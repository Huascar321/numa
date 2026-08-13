from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from collections.abc import Mapping
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Account, Plan
from app.accounts.schemas import AccountCreate, PlanCreate
from app.accounts.service import create_account, create_plan
from app.db import session_factory_for
from app.ledger.models import (
    Category,
    CategoryGroup,
    MonthlyBudgetAssignment,
    PostedAccountMovement,
    Tag,
    Transaction,
    TransactionCorrection,
    TransactionTag,
)
from app.ledger.schemas import TransactionCreate
from app.ledger.service import create_transaction
from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_ledger(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE transaction_tags, posted_account_movements, "
        "transaction_corrections, monthly_budget_assignments, transactions, "
        "tags, categories, category_groups, accounts, plans CASCADE"
    )
    with postgres_sessions.begin() as session:
        session.execute(statement)
    yield
    with postgres_sessions.begin() as session:
        session.execute(statement)


@pytest.fixture
def client(migrated_postgres_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=migrated_postgres_url)))


def _plan(client: TestClient, *, timezone_name: str = "America/La_Paz") -> str:
    plan_id = str(uuid4())
    response = client.put(
        f"/plans/{plan_id}",
        json={
            "name": "Ledger Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": timezone_name,
        },
    )
    assert response.status_code == 201, response.text
    return plan_id


def _account(
    client: TestClient,
    plan_id: str,
    *,
    currency: str = "BOB",
    account_type: str = "Bank",
) -> str:
    account_id = str(uuid4())
    response = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={
            "name": f"{account_type} account",
            "account_type": account_type,
            "currency_code": currency,
        },
    )
    assert response.status_code == 201, response.text
    return account_id


def _category(client: TestClient, plan_id: str, name: str = "Groceries") -> str:
    category_id = str(uuid4())
    response = client.put(
        f"/plans/{plan_id}/categories/{category_id}", json={"name": name}
    )
    assert response.status_code == 201, response.text
    return category_id


def _transaction(
    client: TestClient,
    plan_id: str,
    account_id: str,
    *,
    amount: str = "20.00",
    event_at: str = "2026-01-15T12:00:00Z",
    category_id: str | None = None,
    transaction_id: str | None = None,
    transaction_type: str = "expense",
    currency: str = "BOB",
    merchant: str | None = None,
    memo: str | None = None,
) -> tuple[str, object]:
    transaction_id = transaction_id or str(uuid4())
    payload = {
        "type": transaction_type,
        "account_id": account_id,
        "amount": amount,
        "currency_code": currency,
        "event_at": event_at,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    if merchant is not None:
        payload["merchant"] = merchant
    if memo is not None:
        payload["memo"] = memo
    response = client.put(
        f"/plans/{plan_id}/transactions/{transaction_id}", json=payload
    )
    assert response.status_code == 201, response.text
    return transaction_id, response


def _parallel_put(
    database_url: str,
    requests: list[tuple[str, Mapping[str, object]]],
) -> list[tuple[int, dict[str, object]]]:
    """Send real concurrent HTTP requests, each with its own DB session."""

    barrier = Barrier(len(requests))

    def send(request: tuple[str, Mapping[str, object]]) -> tuple[int, dict[str, object]]:
        path, payload = request
        with TestClient(create_app(Settings(database_url=database_url))) as local_client:
            barrier.wait()
            response = local_client.put(path, json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return list(executor.map(send, requests))


def _parallel_posts(
    database_url: str,
    requests: list[tuple[str, dict[str, object]]],
) -> list[tuple[int, dict[str, object]]]:
    barrier = Barrier(len(requests))

    def send(request: tuple[str, dict[str, object]]) -> tuple[int, dict[str, object]]:
        path, payload = request
        with TestClient(create_app(Settings(database_url=database_url))) as local_client:
            barrier.wait()
            response = local_client.post(path, json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return list(executor.map(send, requests))


def test_pending_is_atomic_plan_identity_and_plan_isolation(client: TestClient) -> None:
    plan_a = _plan(client)
    plan_b = _plan(client)
    pending_a = client.get(f"/plans/{plan_a}/categories").json()
    pending_b = client.get(f"/plans/{plan_b}/categories").json()
    assert len(pending_a) == len(pending_b) == 1
    assert pending_a[0]["name"] == pending_b[0]["name"] == "Pendientes"
    assert pending_a[0]["is_pending"] is True
    account_b = _account(client, plan_b)
    cross_plan = client.put(
        f"/plans/{plan_b}/transactions/{uuid4()}",
        json={
            "type": "expense",
            "account_id": account_b,
            "amount": "1.00",
            "currency_code": "BOB",
            "event_at": "2026-01-01T00:00:00Z",
            "category_id": pending_a[0]["id"],
        },
    )
    assert cross_plan.status_code == 404


def test_legacy_plan_replay_without_timezone_preserves_idempotency(
    client: TestClient,
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan_id = uuid4()
    legacy_payload = {"name": "Legacy", "reporting_currency_code": "BOB"}
    legacy_fingerprint = hashlib.sha256(
        json.dumps(
            legacy_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    with postgres_sessions.begin() as session:
        session.add(
            Plan(
                id=plan_id,
                name="Renamed legacy",
                reporting_currency_code="BOB",
                budget_timezone="America/La_Paz",
                creation_fingerprint=legacy_fingerprint,
            )
        )
        session.add(
            Category(
                id=uuid4(),
                plan_id=plan_id,
                name="Pendientes",
                is_pending=True,
                status="active",
                creation_fingerprint=hashlib.sha256(b"legacy-pending").hexdigest(),
            )
        )
    replay = client.put(
        f"/plans/{plan_id}",
        json=legacy_payload,
    )
    assert replay.status_code == 200
    assert replay.json()["name"] == "Renamed legacy"
    assert replay.json()["budget_timezone"] == "America/La_Paz"


def test_plan_and_pending_provision_rollback_is_atomic(
    migrated_postgres_url: str,
) -> None:
    factory = session_factory_for(migrated_postgres_url)
    with pytest.raises(RuntimeError, match="abort Plan"):
        with factory.begin() as session:
            create_plan(
                session,
                plan_id=uuid4(),
                payload=PlanCreate(
                    name="Aborted",
                    reporting_currency_code="BOB",
                    budget_timezone="America/La_Paz",
                ),
            )
            raise RuntimeError("abort Plan")
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM plans")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM categories")).scalar() == 0


def test_posting_idempotency_exact_signs_and_atomic_rollback(
    client: TestClient,
    migrated_postgres_url: str,
) -> None:
    plan_id = _plan(client)
    account_id = _account(client, plan_id)
    transaction_id = str(uuid4())
    payload = {
        "type": "expense",
        "account_id": account_id,
        "amount": "3.25",
        "currency_code": "BOB",
        "event_at": "2026-01-15T12:00:00Z",
    }
    first = client.put(f"/plans/{plan_id}/transactions/{transaction_id}", json=payload)
    replay = client.put(f"/plans/{plan_id}/transactions/{transaction_id}", json=payload)
    conflict = client.put(
        f"/plans/{plan_id}/transactions/{transaction_id}",
        json={**payload, "amount": "4.25"},
    )
    assert [first.status_code, replay.status_code, conflict.status_code] == [201, 200, 409]
    income_id, _ = _transaction(
        client,
        plan_id,
        account_id,
        amount="10.00",
        transaction_type="income",
    )
    assert income_id
    tag_id = str(uuid4())
    assert client.put(
        f"/plans/{plan_id}/tags/{tag_id}", json={"name": "Rollback tag"}
    ).status_code == 201
    factory = session_factory_for(migrated_postgres_url)
    with pytest.raises(RuntimeError, match="abort posting"):
        with factory.begin() as session:
            create_transaction(
                session,
                plan_id=UUID(plan_id),
                transaction_id=uuid4(),
                payload=TransactionCreate.model_validate(
                    {
                        "type": "expense",
                        "account_id": account_id,
                        "amount": "1.00",
                        "currency_code": "BOB",
                            "event_at": "2026-01-15T12:00:00Z",
                            "tags": [tag_id],
                    }
                ),
            )
            raise RuntimeError("abort posting")
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM transactions")).scalar() == 2
        assert session.execute(text("SELECT count(*) FROM posted_account_movements")).scalar() == 2
        assert session.execute(text("SELECT count(*) FROM transaction_tags")).scalar() == 0
        assert session.execute(text("SELECT sum(signed_amount) FROM posted_account_movements")).scalar() == Decimal("6.75")


def test_concurrent_uuid_idempotency_for_taxonomy_transactions_and_assignments(
    client: TestClient,
    migrated_postgres_url: str,
) -> None:
    plan_id = _plan(client)

    group_id = str(uuid4())
    group_path = f"/plans/{plan_id}/category-groups/{group_id}"
    group_payload = {"name": "Concurrent group"}
    group_results = _parallel_put(
        migrated_postgres_url,
        [(group_path, group_payload), (group_path, group_payload)],
    )
    assert sorted(status_code for status_code, _ in group_results) == [200, 201]

    category_id = str(uuid4())
    category_path = f"/plans/{plan_id}/categories/{category_id}"
    category_payload = {"name": "Concurrent category", "group_id": group_id}
    category_results = _parallel_put(
        migrated_postgres_url,
        [(category_path, category_payload), (category_path, category_payload)],
    )
    assert sorted(status_code for status_code, _ in category_results) == [200, 201]

    conflicting_group_id = str(uuid4())
    conflicting_group_path = f"/plans/{plan_id}/category-groups/{conflicting_group_id}"
    conflicting_group_results = _parallel_put(
        migrated_postgres_url,
        [
            (conflicting_group_path, {"name": "Group winner"}),
            (conflicting_group_path, {"name": "Group conflict"}),
        ],
    )
    assert sorted(status_code for status_code, _ in conflicting_group_results) == [201, 409]

    conflicting_category_id = str(uuid4())
    conflicting_category_path = f"/plans/{plan_id}/categories/{conflicting_category_id}"
    conflicting_category_results = _parallel_put(
        migrated_postgres_url,
        [
            (conflicting_category_path, {"name": "Category winner", "group_id": group_id}),
            (conflicting_category_path, {"name": "Category conflict", "group_id": group_id}),
        ],
    )
    assert sorted(status_code for status_code, _ in conflicting_category_results) == [201, 409]

    tag_id = str(uuid4())
    tag_path = f"/plans/{plan_id}/tags/{tag_id}"
    tag_payload = {"name": "Concurrent tag"}
    tag_results = _parallel_put(
        migrated_postgres_url,
        [(tag_path, tag_payload), (tag_path, tag_payload)],
    )
    assert sorted(status_code for status_code, _ in tag_results) == [200, 201]

    conflicting_tag_id = str(uuid4())
    conflicting_tag_path = f"/plans/{plan_id}/tags/{conflicting_tag_id}"
    conflicting_tag_results = _parallel_put(
        migrated_postgres_url,
        [
            (conflicting_tag_path, {"name": "Tag winner"}),
            (conflicting_tag_path, {"name": "Tag conflict"}),
        ],
    )
    assert sorted(status_code for status_code, _ in conflicting_tag_results) == [201, 409]

    account_id = _account(client, plan_id)
    transaction_id = str(uuid4())
    transaction_path = f"/plans/{plan_id}/transactions/{transaction_id}"
    transaction_payload = {
        "type": "expense",
        "account_id": account_id,
        "amount": "12.00",
        "currency_code": "BOB",
        "event_at": "2026-08-13T12:00:00Z",
        "category_id": category_id,
        "tags": [tag_id],
    }
    transaction_results = _parallel_put(
        migrated_postgres_url,
        [(transaction_path, transaction_payload), (transaction_path, transaction_payload)],
    )
    assert sorted(status_code for status_code, _ in transaction_results) == [200, 201]

    conflicting_transaction_id = str(uuid4())
    conflicting_path = f"/plans/{plan_id}/transactions/{conflicting_transaction_id}"
    conflicting_results = _parallel_put(
        migrated_postgres_url,
        [
            (conflicting_path, {**transaction_payload, "amount": "13.00"}),
            (conflicting_path, {**transaction_payload, "amount": "14.00"}),
        ],
    )
    assert sorted(status_code for status_code, _ in conflicting_results) == [201, 409]

    assignment_id = str(uuid4())
    assignment_path = f"/plans/{plan_id}/budget-assignments/{assignment_id}"
    assignment_payload = {
        "category_id": category_id,
        "month": "2026-08",
        "amount": "20.00",
    }
    assignment_results = _parallel_put(
        migrated_postgres_url,
        [(assignment_path, assignment_payload), (assignment_path, assignment_payload)],
    )
    assert sorted(status_code for status_code, _ in assignment_results) == [200, 201]

    archive_results = _parallel_posts(
        migrated_postgres_url,
        [
            (f"/plans/{plan_id}/tags/{tag_id}/archive", {}),
            (f"/plans/{plan_id}/tags/{tag_id}/archive", {}),
        ],
    )
    assert [status_code for status_code, _ in archive_results] == [200, 200]

    conflicting_assignment_id = str(uuid4())
    conflicting_assignment_path = (
        f"/plans/{plan_id}/budget-assignments/{conflicting_assignment_id}"
    )
    conflicting_assignment_results = _parallel_put(
        migrated_postgres_url,
        [
            (conflicting_assignment_path, {**assignment_payload, "amount": "21.00"}),
            (conflicting_assignment_path, {**assignment_payload, "amount": "22.00"}),
        ],
    )
    assert sorted(status_code for status_code, _ in conflicting_assignment_results) == [
        201,
        409,
    ]

    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(
            text("SELECT count(*) FROM category_groups WHERE id = :id"),
            {"id": group_id},
        ) == 1
        assert session.scalar(
            text("SELECT count(*) FROM categories WHERE id = :id"),
            {"id": category_id},
        ) == 1
        assert session.scalar(
            text("SELECT count(*) FROM tags WHERE id = :id"), {"id": tag_id}
        ) == 1
        assert session.scalar(
            text("SELECT count(*) FROM transactions WHERE id IN (:one, :two)"),
            {"one": transaction_id, "two": conflicting_transaction_id},
        ) == 2
        assert session.scalar(
            text(
                "SELECT count(*) FROM posted_account_movements "
                "WHERE transaction_id IN (:one, :two)"
            ),
            {"one": transaction_id, "two": conflicting_transaction_id},
        ) == 2
        assert session.scalar(
            text("SELECT count(*) FROM monthly_budget_assignments WHERE id IN (:one, :two)"),
            {"one": assignment_id, "two": conflicting_assignment_id},
        ) == 2


def test_concurrent_correction_uuid_replay_and_conflict_are_atomic(
    client: TestClient,
    migrated_postgres_url: str,
) -> None:
    plan_id = _plan(client)
    account_id = _account(client, plan_id)
    transaction_id, _ = _transaction(client, plan_id, account_id)
    correction_id = str(uuid4())
    correction_path = (
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{correction_id}"
    )
    correction_payload = {"merchant": "Concurrent correction"}

    identical_results = _parallel_put(
        migrated_postgres_url,
        [(correction_path, correction_payload), (correction_path, correction_payload)],
    )
    assert sorted(status_code for status_code, _ in identical_results) == [200, 201]

    conflict_transaction_id, _ = _transaction(client, plan_id, account_id)
    conflict_correction_id = str(uuid4())
    conflict_path = (
        f"/plans/{plan_id}/transactions/{conflict_transaction_id}/corrections/"
        f"{conflict_correction_id}"
    )
    conflict_results = _parallel_put(
        migrated_postgres_url,
        [
            (conflict_path, {"amount": "21.00"}),
            (conflict_path, {"amount": "22.00"}),
        ],
    )
    assert sorted(status_code for status_code, _ in conflict_results) == [201, 409]

    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(
            text("SELECT count(*) FROM transaction_corrections WHERE id = :id"),
            {"id": correction_id},
        ) == 1
        assert session.scalar(
            text("SELECT count(*) FROM posted_account_movements WHERE transaction_id = :id"),
            {"id": transaction_id},
        ) == 3
        assert session.scalar(
            text("SELECT count(*) FROM transaction_corrections WHERE id = :id"),
            {"id": conflict_correction_id},
        ) == 1
        assert session.scalar(
            text(
                "SELECT count(*) FROM posted_account_movements WHERE transaction_id = :id"
            ),
            {"id": conflict_transaction_id},
        ) == 3


def test_two_different_concurrent_corrections_are_serialized_and_projected(
    client: TestClient,
    migrated_postgres_url: str,
) -> None:
    plan_id = _plan(client, timezone_name="America/La_Paz")
    account_id = _account(client, plan_id)
    first_category = _category(client, plan_id, "Original category")
    final_category = _category(client, plan_id, "Final category")
    transaction_id, _ = _transaction(
        client,
        plan_id,
        account_id,
        category_id=first_category,
        event_at="2026-01-15T12:00:00Z",
    )
    category_correction_path = (
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{uuid4()}"
    )
    timestamp_correction_path = (
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{uuid4()}"
    )
    results = _parallel_put(
        migrated_postgres_url,
        [
            (category_correction_path, {"category_id": final_category}),
            (timestamp_correction_path, {"event_at": "2026-02-15T12:00:00Z"}),
        ],
    )
    assert sorted(status_code for status_code, _ in results) == [201, 201]

    with session_factory_for(migrated_postgres_url)() as session:
        corrections = session.execute(
            text(
                "SELECT correction_sequence, before_snapshot, after_snapshot "
                "FROM transaction_corrections WHERE transaction_id = :id "
                "ORDER BY correction_sequence"
            ),
            {"id": transaction_id},
        ).all()
        movements = session.execute(
            text(
                "SELECT correction_sequence, movement_kind, signed_amount, category_id, effective_at "
                "FROM posted_account_movements WHERE transaction_id = :id "
                "ORDER BY correction_sequence, movement_kind"
            ),
            {"id": transaction_id},
        ).all()
        assert [row[0] for row in corrections] == [1, 2]
        assert [(row[0], row[1]) for row in movements] == [
            (0, "original"),
            (1, "compensation"),
            (1, "replacement"),
            (2, "compensation"),
            (2, "replacement"),
        ]
        for index in (1, 2):
            compensation = next(
                row for row in movements if row[0] == index and row[1] == "compensation"
            )
            replacement = next(
                row for row in movements if row[0] == index and row[1] == "replacement"
            )
            previous = movements[0] if index == 1 else next(
                row for row in movements if row[0] == index - 1 and row[1] == "replacement"
            )
            assert compensation[2] == -previous[2]
            assert replacement[2] == -Decimal("20.000000000000000000")

        final_snapshot = corrections[-1][2]
        assert final_snapshot["category_id"] == final_category
        assert final_snapshot["event_at"].startswith("2026-02-15T12:00:00")
        assert session.scalar(
            text("SELECT sum(signed_amount) FROM posted_account_movements WHERE account_id = :id"),
            {"id": account_id},
        ) == Decimal("-20.000000000000000000")

    final_transaction = client.get(
        f"/plans/{plan_id}/transactions/{transaction_id}"
    ).json()
    assert final_transaction["category_id"] == final_category
    assert final_transaction["event_at"].startswith("2026-02-15T12:00:00")
    assert client.get(f"/plans/{plan_id}/accounts/{account_id}/balance").json()["amount"] == "-20.00"
    january = client.get(f"/plans/{plan_id}/budget/months/2026-01").json()
    february = client.get(f"/plans/{plan_id}/budget/months/2026-02").json()
    assert january["activity_total"] == "0.00"
    assert february["activity_total"] == "-20.00"
    assert next(
        envelope for envelope in february["categories"] if envelope["category_id"] == final_category
    )["activity"] == "-20.00"
    assert len(client.get(f"/plans/{plan_id}/transactions/{transaction_id}/corrections").json()) == 2


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"amount": 1.5},
        {"amount": "1.001"},
        {"amount": "0.00"},
        {"amount": "-1.00"},
    ],
)
def test_rejects_float_invalid_scale_and_sign_without_writes(
    client: TestClient,
    bad_payload: dict[str, object],
) -> None:
    plan_id = _plan(client)
    account_id = _account(client, plan_id)
    payload: dict[str, object] = {
        "type": "expense",
        "account_id": account_id,
        "amount": "1.00",
        "currency_code": "BOB",
        "event_at": "2026-01-15T12:00:00Z",
    }
    payload.update(bad_payload)
    response = client.put(f"/plans/{plan_id}/transactions/{uuid4()}", json=payload)
    assert response.status_code == 422
    assert client.get(f"/plans/{plan_id}/transactions").json() == []


def test_rejects_incompatible_currency_and_archived_account(client: TestClient) -> None:
    plan_id = _plan(client)
    bob_account = _account(client, plan_id)
    usdt_payload = {
        "type": "expense",
        "account_id": bob_account,
        "amount": "1.000000",
        "currency_code": "USDT",
        "event_at": "2026-01-15T12:00:00Z",
    }
    assert client.put(f"/plans/{plan_id}/transactions/{uuid4()}", json=usdt_payload).status_code == 422
    assert client.post(f"/plans/{plan_id}/accounts/{bob_account}/archive").status_code == 200
    valid_payload = {**usdt_payload, "amount": "1.00", "currency_code": "BOB"}
    assert client.put(f"/plans/{plan_id}/transactions/{uuid4()}", json=valid_payload).status_code == 422


def test_all_six_account_types_and_derived_balances(client: TestClient) -> None:
    plan_id = _plan(client)
    for account_type in ("Bank", "Cash", "Wallet", "Credit Card", "Crypto", "Other"):
        currency = "USDT" if account_type in {"Crypto", "Other"} else "BOB"
        account_id = _account(client, plan_id, currency=currency, account_type=account_type)
        assert client.get(f"/plans/{plan_id}/accounts/{account_id}").json()["balance"]["amount"] == (
            "0.000000" if currency == "USDT" else "0.00"
        )
    bob_account = client.get(f"/plans/{plan_id}/accounts").json()[0]["id"]
    _transaction(client, plan_id, bob_account, amount="10.00", transaction_type="income")
    _transaction(client, plan_id, bob_account, amount="3.25")
    assert client.get(f"/plans/{plan_id}/accounts/{bob_account}/balance").json() == {
        "amount": "6.75",
        "currency": "BOB",
    }


def test_taxonomy_lifecycle_and_pending_protection(client: TestClient) -> None:
    plan_id = _plan(client)
    group_id = str(uuid4())
    category_id = _category(client, plan_id)
    assert client.put(
        f"/plans/{plan_id}/category-groups/{group_id}", json={"name": "Needs"}
    ).status_code == 201
    assert client.patch(
        f"/plans/{plan_id}/categories/{category_id}", json={"group_id": group_id}
    ).status_code == 200
    assert client.post(f"/plans/{plan_id}/category-groups/{group_id}/archive").status_code == 409
    assert client.post(f"/plans/{plan_id}/categories/{category_id}/archive").status_code == 200
    assert client.post(f"/plans/{plan_id}/category-groups/{group_id}/archive").status_code == 200
    pending_id = client.get(f"/plans/{plan_id}/categories").json()[0]["id"]
    assert client.patch(f"/plans/{plan_id}/categories/{pending_id}", json={"name": "Nope"}).status_code == 409
    assert client.post(f"/plans/{plan_id}/categories/{pending_id}/archive").status_code == 409
    assert client.delete(f"/plans/{plan_id}/categories/{pending_id}").status_code == 405


@pytest.mark.parametrize(
    ("field", "replacement", "expected_balance"),
    [
        ("amount", "30.00", "-30.00"),
        ("account_id", "SECOND_ACCOUNT", "-20.00"),
        ("category_id", "SECOND_CATEGORY", "-20.00"),
        ("event_at", "2026-02-01T12:00:00Z", "-20.00"),
        ("merchant", "Corrected merchant", "-20.00"),
        ("memo", "Corrected memo", "-20.00"),
    ],
)
def test_independent_corrections_are_compensating_and_immutable(
    client: TestClient,
    field: str,
    replacement: str,
    expected_balance: str,
) -> None:
    plan_id = _plan(client)
    first_account = _account(client, plan_id)
    second_account = _account(client, plan_id, account_type="Cash")
    first_category = _category(client, plan_id, "First")
    second_category = _category(client, plan_id, "Second")
    transaction_id, _ = _transaction(
        client,
        plan_id,
        first_account,
        category_id=first_category,
        merchant="Original merchant",
        memo="Original memo",
    )
    value = {
        "account_id": second_account if replacement == "SECOND_ACCOUNT" else None,
        "category_id": second_category if replacement == "SECOND_CATEGORY" else None,
    }.get(field, replacement)
    response = client.put(
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{uuid4()}",
        json={field: value},
    )
    assert response.status_code == 201, response.text
    movements = client.get(f"/plans/{plan_id}/transactions/{transaction_id}").json()
    assert movements["amount"] == (replacement if field == "amount" else "20.00")
    account_id = second_account if field == "account_id" else first_account
    assert client.get(f"/plans/{plan_id}/accounts/{account_id}/balance").json()["amount"] == expected_balance
    if field == "account_id":
        assert client.get(f"/plans/{plan_id}/accounts/{first_account}/balance").json()["amount"] == "0.00"


def test_each_correction_field_preserves_snapshots_movements_balances_and_activity(
    client: TestClient,
    migrated_postgres_url: str,
) -> None:
    plan_id = _plan(client, timezone_name="America/New_York")
    original_account = _account(client, plan_id, account_type="Bank")
    replacement_account = _account(client, plan_id, account_type="Cash")
    original_category = _category(client, plan_id, "Original")
    replacement_category = _category(client, plan_id, "Replacement")
    transaction_id, _ = _transaction(
        client,
        plan_id,
        original_account,
        category_id=original_category,
        event_at="2026-01-15T12:00:00Z",
        merchant="Original merchant",
        memo="Original memo",
    )

    corrections = [
        {"amount": "30.00"},
        {"account_id": replacement_account},
        {"category_id": replacement_category},
        {"event_at": "2026-03-15T12:00:00Z"},
        {"merchant": "Corrected merchant"},
        {"memo": "Corrected memo"},
    ]
    for payload in corrections:
        response = client.put(
            f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{uuid4()}",
            json=payload,
        )
        assert response.status_code == 201, response.text

    with session_factory_for(migrated_postgres_url)() as session:
        correction_rows = session.execute(
            text(
                "SELECT correction_sequence, before_snapshot, after_snapshot "
                "FROM transaction_corrections WHERE transaction_id = :id "
                "ORDER BY correction_sequence"
            ),
            {"id": transaction_id},
        ).all()
        movement_rows = session.execute(
            text(
                "SELECT correction_sequence, movement_kind, account_id, category_id, "
                "signed_amount, effective_at, merchant, memo "
                "FROM posted_account_movements WHERE transaction_id = :id "
                "ORDER BY correction_sequence, movement_kind, id"
            ),
            {"id": transaction_id},
        ).all()
        assert [row[0] for row in correction_rows] == [1, 2, 3, 4, 5, 6]
        assert len(movement_rows) == 13
        assert sum(row[1] == "compensation" for row in movement_rows) == 6
        assert sum(row[1] == "replacement" for row in movement_rows) == 6
        for sequence in range(1, 7):
            compensation = next(
                row for row in movement_rows
                if row[0] == sequence and row[1] == "compensation"
            )
            replacement = next(
                row for row in movement_rows
                if row[0] == sequence and row[1] == "replacement"
            )
            prior = (
                movement_rows[0]
                if sequence == 1
                else next(
                    row for row in movement_rows
                    if row[0] == sequence - 1 and row[1] == "replacement"
                )
            )
            assert compensation[4] == -prior[4]
            assert compensation[2] == prior[2]
            assert compensation[3] == prior[3]
            assert replacement[4] == Decimal("-30.000000000000000000")

        assert correction_rows[0][1]["amount"] == "20.00"
        assert correction_rows[0][2]["amount"] == "30.00"
        assert correction_rows[1][1]["account_id"] == original_account
        assert correction_rows[1][2]["account_id"] == replacement_account
        assert correction_rows[2][1]["category_id"] == original_category
        assert correction_rows[2][2]["category_id"] == replacement_category
        assert correction_rows[3][1]["event_at"].startswith("2026-01-15T12:00:00")
        assert correction_rows[3][2]["event_at"].startswith("2026-03-15T12:00:00")
        assert correction_rows[4][1]["merchant"] == "Original merchant"
        assert correction_rows[4][2]["merchant"] == "Corrected merchant"
        assert correction_rows[5][1]["memo"] == "Original memo"
        assert correction_rows[5][2]["memo"] == "Corrected memo"

        assert session.scalar(
            text("SELECT sum(signed_amount) FROM posted_account_movements WHERE account_id = :id"),
            {"id": original_account},
        ) == Decimal("0E-18")
        assert session.scalar(
            text("SELECT sum(signed_amount) FROM posted_account_movements WHERE account_id = :id"),
            {"id": replacement_account},
        ) == Decimal("-30.000000000000000000")

        with pytest.raises(Exception):
            session.execute(
                text(
                    "UPDATE posted_account_movements SET signed_amount = 0 "
                    "WHERE transaction_id = :id"
                ),
                {"id": transaction_id},
            )
        session.rollback()

    january = client.get(f"/plans/{plan_id}/budget/months/2026-01").json()
    march = client.get(f"/plans/{plan_id}/budget/months/2026-03").json()
    assert january["activity_total"] == "0.00"
    assert march["activity_total"] == "-30.00"
    assert next(
        envelope for envelope in march["categories"]
        if envelope["category_id"] == replacement_category
    )["activity"] == "-30.00"
    assert client.get(
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections"
    ).status_code == 200


def test_correction_history_and_movement_chain(client: TestClient, migrated_postgres_url: str) -> None:
    plan_id = _plan(client)
    account_id = _account(client, plan_id)
    transaction_id, _ = _transaction(client, plan_id, account_id)
    correction_id = str(uuid4())
    assert client.put(
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{correction_id}",
        json={"merchant": "Updated"},
    ).status_code == 201
    assert client.put(
        f"/plans/{plan_id}/transactions/{transaction_id}/corrections/{correction_id}",
        json={"merchant": "Updated"},
    ).status_code == 200
    with session_factory_for(migrated_postgres_url)() as session:
        rows = session.execute(
            text(
                "SELECT correction_sequence, movement_kind, signed_amount "
                "FROM posted_account_movements "
                "WHERE transaction_id = :transaction_id "
                "ORDER BY correction_sequence, movement_kind, id"
            ),
            {"transaction_id": transaction_id},
        ).all()
        assert [row[1] for row in rows] == ["original", "compensation", "replacement"]
        assert rows[0][2] == Decimal("-20.000000000000000000")
    assert len(client.get(f"/plans/{plan_id}/transactions/{transaction_id}/corrections").json()) == 1


def test_month_boundaries_assignments_dst_and_unconverted_reporting(client: TestClient) -> None:
    plan_id = _plan(client, timezone_name="America/New_York")
    bob = _account(client, plan_id)
    usdt = _account(client, plan_id, currency="USDT", account_type="Crypto")
    category_id = _category(client, plan_id)
    _transaction(client, plan_id, bob, amount="100.00", transaction_type="income", event_at="2026-03-01T04:59:59Z")
    _transaction(client, plan_id, bob, amount="20.00", category_id=category_id, event_at="2026-03-08T07:00:00Z")
    _transaction(client, plan_id, usdt, amount="1.000000", category_id=category_id, currency="USDT", event_at="2026-03-08T07:00:00Z")
    assert client.put(
        f"/plans/{plan_id}/budget-assignments/{uuid4()}",
        json={"category_id": category_id, "month": "2026-02", "amount": "60.00"},
    ).status_code == 201
    assert client.put(
        f"/plans/{plan_id}/budget-assignments/{uuid4()}",
        json={"category_id": category_id, "month": "2026-02", "amount": "-10.00"},
    ).status_code == 201
    february = client.get(f"/plans/{plan_id}/budget/months/2026-02").json()
    march = client.get(f"/plans/{plan_id}/budget/months/2026-03").json()
    assert february["ready_to_assign"] == "50.00"
    assert march["ready_to_assign"] == "0.00"
    assert february["unconverted_by_currency"] == []
    assert march["unconverted_by_currency"][0]["currency"] == "USDT"
    assert march["unconverted_by_currency"][0]["amount"] == "-1.000000"


def test_no_forbidden_ledger_capabilities(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert all("delete" not in operations for operations in paths.values())
    forbidden = ("transfer", "cleared", "reconciliation", "rollover", "goal", "target", "fx")
    assert not any(any(word in path.lower() for word in forbidden) for path in paths)
