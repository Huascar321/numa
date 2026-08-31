from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Barrier, Event
from typing import Literal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import EXPECTED_REVISION, session_factory_for
from app.main import create_app
from app.settings import Settings
from app.ledger import service as ledger_service


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_reconciliation(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE reconciliation_sessions, transfer_legs, transfers, transaction_tags, "
        "posted_account_movements, transaction_corrections, monthly_budget_assignments, "
        "transactions, tags, categories, category_groups, accounts, plans CASCADE"
    )
    with postgres_sessions.begin() as session:
        session.execute(statement)
    yield
    with postgres_sessions.begin() as session:
        session.execute(statement)


def _client(
    database_url: str,
    *,
    policy: Literal["block", "warn"] = "warn",
    tolerance_atoms: int = 0,
) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_url=database_url,
                reconciliation_policy=policy,
                reconciliation_tolerance_atoms=tolerance_atoms,
            )
        )
    )


def _plan(client: TestClient) -> str:
    plan_id = str(uuid4())
    response = client.put(
        f"/plans/{plan_id}",
        json={
            "name": "Reconciliation Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": "America/La_Paz",
        },
    )
    assert response.status_code == 201, response.text
    return plan_id


def _account(client: TestClient, plan_id: str, *, currency: str = "BOB") -> str:
    account_id = str(uuid4())
    response = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={
            "name": "Statement account",
            "account_type": "Bank",
            "currency_code": currency,
        },
    )
    assert response.status_code == 201, response.text
    return account_id


def _transaction(
    client: TestClient,
    plan_id: str,
    account_id: str,
    *,
    amount: str,
    event_at: str,
    transaction_type: str = "income",
) -> None:
    response = client.put(
        f"/plans/{plan_id}/transactions/{uuid4()}",
        json={
            "type": transaction_type,
            "account_id": account_id,
            "amount": amount,
            "currency_code": "BOB",
            "event_at": event_at,
        },
    )
    assert response.status_code == 201, response.text


def _statement(balance: str, at: str = "2026-01-15T12:00:00Z") -> dict[str, object]:
    return {
        "statement_balance": balance,
        "currency_code": "BOB",
        "statement_at": at,
    }


def _preview_path(plan_id: str, account_id: str, session_id: str) -> str:
    return f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{session_id}/preview"


def _confirm_path(plan_id: str, account_id: str, session_id: str) -> str:
    return f"/plans/{plan_id}/accounts/{account_id}/reconciliations/{session_id}"


def test_preview_is_exact_inclusive_plan_scoped_and_side_effect_free(
    migrated_postgres_url: str,
) -> None:
    client = _client(migrated_postgres_url)
    plan = _plan(client)
    account = _account(client, plan)
    other_plan = _plan(client)
    other_account = _account(client, other_plan)
    _transaction(client, plan, account, amount="10.00", event_at="2026-01-01T00:00:00Z")
    _transaction(
        client,
        plan,
        account,
        amount="3.00",
        event_at="2026-01-15T12:00:00Z",
        transaction_type="expense",
    )
    _transaction(client, plan, account, amount="100.00", event_at="2026-01-15T12:00:01Z")
    _transaction(client, other_plan, other_account, amount="999.00", event_at="2026-01-01T00:00:00Z")
    reconciliation_id = str(uuid4())

    first = client.post(
        _preview_path(plan, account, reconciliation_id), json=_statement("9.00")
    )
    second = client.post(
        _preview_path(plan, account, reconciliation_id), json=_statement("9.00")
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["derived_balance"] == {"amount": "7.00", "currency": "BOB"}
    assert first.json()["discrepancy"] == {"amount": "2.00", "currency": "BOB"}
    assert first.json()["requires_warning_acceptance"] is True
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(text("SELECT count(*) FROM reconciliation_sessions")) == 0
        assert session.scalar(
            text("SELECT count(*) FROM transactions WHERE type='reconciliation_adjustment'")
        ) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"statement_balance": 1.5, "currency_code": "BOB", "statement_at": "2026-01-01T00:00:00Z"},
        {"statement_balance": "1.001", "currency_code": "BOB", "statement_at": "2026-01-01T00:00:00Z"},
        {"statement_balance": "1.00", "currency_code": "USDT", "statement_at": "2026-01-01T00:00:00Z"},
        {"statement_balance": "1.00", "currency_code": "BOB", "statement_at": "2026-01-01T00:00:00-04:00"},
        {"statement_balance": "1e999999", "currency_code": "BOB", "statement_at": "2026-01-01T00:00:00Z"},
        {"statement_balance": "100000000000000000000", "currency_code": "BOB", "statement_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_statement_contract_rejects_float_scale_currency_and_non_utc(
    migrated_postgres_url: str, payload: dict[str, object]
) -> None:
    client = _client(migrated_postgres_url)
    plan = _plan(client)
    account = _account(client, plan)
    response = client.post(_preview_path(plan, account, str(uuid4())), json=payload)
    assert response.status_code == 422
    assert client.get(f"/plans/{plan}/accounts/{account}/reconciliations").json() == []


def test_warn_block_and_tolerance_boundary(migrated_postgres_url: str) -> None:
    warn = _client(migrated_postgres_url, policy="warn", tolerance_atoms=100)
    plan = _plan(warn)
    account = _account(warn, plan)

    at_boundary = str(uuid4())
    preview = warn.post(_preview_path(plan, account, at_boundary), json=_statement("1.00"))
    assert preview.json()["tolerance"]["amount"] == "1.00"
    assert preview.json()["requires_warning_acceptance"] is False
    assert warn.put(
        _confirm_path(plan, account, at_boundary),
        json={**_statement("1.00"), "warning_accepted": False},
    ).status_code == 201

    above = str(uuid4())
    denied = warn.put(
        _confirm_path(plan, account, above),
        json={**_statement("2.01", "2026-02-01T00:00:00Z"), "warning_accepted": False},
    )
    assert denied.status_code == 409
    accepted = warn.put(
        _confirm_path(plan, account, above),
        json={**_statement("2.01", "2026-02-01T00:00:00Z"), "warning_accepted": True},
    )
    assert accepted.status_code == 201

    blocked_client = _client(migrated_postgres_url, policy="block", tolerance_atoms=100)
    blocked = blocked_client.put(
        _confirm_path(plan, account, str(uuid4())),
        json={**_statement("4.00", "2026-03-01T00:00:00Z"), "warning_accepted": True},
    )
    assert blocked.status_code == 409


def test_zero_confirmation_is_auditable_without_movement_even_when_archived(
    migrated_postgres_url: str,
) -> None:
    client = _client(migrated_postgres_url)
    plan = _plan(client)
    account = _account(client, plan)
    _transaction(client, plan, account, amount="7.00", event_at="2026-01-01T00:00:00Z")
    assert client.post(f"/plans/{plan}/accounts/{account}/archive").status_code == 200

    zero = client.put(
        _confirm_path(plan, account, str(uuid4())),
        json={**_statement("7.00"), "warning_accepted": False},
    )
    assert zero.status_code == 201
    assert zero.json()["discrepancy"]["amount"] == "0.00"
    assert zero.json()["adjustment_transaction_id"] is None
    assert zero.json()["adjustment_movement_id"] is None

    mismatch = client.put(
        _confirm_path(plan, account, str(uuid4())),
        json={**_statement("8.00"), "warning_accepted": True},
    )
    assert mismatch.status_code == 409
    history = client.get(f"/plans/{plan}/accounts/{account}/reconciliations").json()
    assert len(history) == 1


def test_adjustment_is_categoryless_protected_and_budget_excluded(
    migrated_postgres_url: str,
) -> None:
    client = _client(migrated_postgres_url)
    plan = _plan(client)
    account = _account(client, plan)
    reconciliation_id = str(uuid4())
    confirmed = client.put(
        _confirm_path(plan, account, reconciliation_id),
        json={**_statement("5.00"), "warning_accepted": True},
    )
    assert confirmed.status_code == 201, confirmed.text
    body = confirmed.json()
    assert body["adjustment_transaction_id"]
    assert client.post(
        _preview_path(plan, account, str(uuid4())), json=_statement("5.00")
    ).json()["discrepancy"]["amount"] == "0.00"
    correction = client.put(
        f"/plans/{plan}/transactions/{body['adjustment_transaction_id']}/corrections/{uuid4()}",
        json={"memo": "forbidden"},
    )
    assert correction.status_code == 409
    summary = client.get(f"/plans/{plan}/budget/months/2026-01").json()
    assert summary["ready_to_assign"] == "0.00"
    assert summary["activity_total"] == "0.00"
    assert summary["unconverted_by_currency"] == []

    factory = session_factory_for(migrated_postgres_url)
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(
                text("UPDATE reconciliation_sessions SET statement_balance=6 WHERE id=:id"),
                {"id": reconciliation_id},
            )
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(
                text("DELETE FROM reconciliation_sessions WHERE id=:id"),
                {"id": reconciliation_id},
            )
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(
                text("UPDATE transactions SET memo='changed' WHERE id=:id"),
                {"id": body["adjustment_transaction_id"]},
            )
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(
                text("DELETE FROM transactions WHERE id=:id"),
                {"id": body["adjustment_transaction_id"]},
            )
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(
                text(
                    "INSERT INTO posted_account_movements "
                    "(id, plan_id, account_id, transaction_id, currency_code, signed_amount, "
                    "transaction_type, effective_at, category_id, source, source_metadata, "
                    "provenance, movement_kind, correction_sequence, reconciliation_session_id) "
                    "SELECT :new_id, plan_id, account_id, transaction_id, currency_code, signed_amount, "
                    "transaction_type, effective_at, category_id, source, source_metadata, provenance, "
                    "movement_kind, correction_sequence, reconciliation_session_id "
                    "FROM posted_account_movements WHERE id=:movement_id"
                ),
                {"new_id": uuid4(), "movement_id": body["adjustment_movement_id"]},
            )


def test_confirmation_uuid_replay_conflict_concurrency_and_plan_isolation(
    migrated_postgres_url: str,
) -> None:
    client = _client(migrated_postgres_url)
    plan = _plan(client)
    account = _account(client, plan)
    other_plan = _plan(client)
    reconciliation_id = str(uuid4())
    path = _confirm_path(plan, account, reconciliation_id)
    payload = {**_statement("3.00"), "warning_accepted": True}
    barrier = Barrier(2)

    def send() -> tuple[int, dict[str, object]]:
        with _client(migrated_postgres_url) as local:
            barrier.wait()
            response = local.put(path, json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: send(), range(2)))
    assert sorted(status_code for status_code, _ in results) == [200, 201]
    assert results[0][1] == results[1][1]
    assert client.put(path, json=payload).status_code == 200
    assert client.put(path, json={**payload, "statement_balance": "4.00"}).status_code == 409
    assert client.get(
        f"/plans/{other_plan}/accounts/{account}/reconciliations"
    ).status_code == 404
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(
            text("SELECT count(*) FROM reconciliation_sessions WHERE id=:id"),
            {"id": reconciliation_id},
        ) == 1
        assert session.scalar(
            text("SELECT count(*) FROM transactions WHERE reconciliation_session_id=:id"),
            {"id": reconciliation_id},
        ) == 1
        assert session.scalar(
            text("SELECT count(*) FROM posted_account_movements WHERE reconciliation_session_id=:id"),
            {"id": reconciliation_id},
        ) == 1


@pytest.mark.parametrize("writer_kind", ["manual", "correction", "transfer", "reversal"])
def test_reconciliation_waits_for_every_current_movement_writer(
    migrated_postgres_url: str, monkeypatch: pytest.MonkeyPatch, writer_kind: str
) -> None:
    client = _client(migrated_postgres_url)
    plan = _plan(client)
    primary = _account(client, plan)
    secondary = _account(client, plan)
    event_at = "2026-01-15T12:00:00Z"

    if writer_kind == "manual":
        expected_balance = "5.00"

        def write(local: TestClient):
            return local.put(
                f"/plans/{plan}/transactions/{uuid4()}",
                json={
                    "type": "income",
                    "account_id": primary,
                    "amount": "5.00",
                    "currency_code": "BOB",
                    "event_at": event_at,
                },
            )

    elif writer_kind == "correction":
        transaction_id = str(uuid4())
        created = client.put(
            f"/plans/{plan}/transactions/{transaction_id}",
            json={
                "type": "income",
                "account_id": primary,
                "amount": "5.00",
                "currency_code": "BOB",
                "event_at": event_at,
            },
        )
        assert created.status_code == 201, created.text
        expected_balance = "7.00"

        def write(local: TestClient):
            return local.put(
                f"/plans/{plan}/transactions/{transaction_id}/corrections/{uuid4()}",
                json={"amount": "7.00"},
            )

    elif writer_kind == "transfer":
        expected_balance = "3.00"

        def write(local: TestClient):
            return local.put(
                f"/plans/{plan}/transfers/{uuid4()}",
                json={
                    "source_account_id": secondary,
                    "destination_account_id": primary,
                    "outbound_amount": "3.00",
                    "inbound_amount": "3.00",
                    "event_at": event_at,
                    "memo": None,
                    "provenance": {},
                },
            )

    else:
        transfer_id = str(uuid4())
        created = client.put(
            f"/plans/{plan}/transfers/{transfer_id}",
            json={
                "source_account_id": secondary,
                "destination_account_id": primary,
                "outbound_amount": "3.00",
                "inbound_amount": "3.00",
                "event_at": event_at,
                "memo": None,
                "provenance": {},
            },
        )
        assert created.status_code == 201, created.text
        expected_balance = "0.00"

        def write(local: TestClient):
            return local.put(
                f"/plans/{plan}/transfers/{transfer_id}/reversals/{uuid4()}",
                json={
                    "event_at": event_at,
                    "reversal_reason": "concurrency regression",
                    "memo": None,
                    "provenance": {},
                },
            )

    writer_locked = Event()
    release_writer = Event()
    original_lock = ledger_service.lock_movement_accounts

    def pause_after_lock(session, plan_id, account_ids):
        accounts = original_lock(session, plan_id, account_ids)
        writer_locked.set()
        if not release_writer.wait(5):
            raise RuntimeError("timed out waiting to release movement writer")
        return accounts

    monkeypatch.setattr(ledger_service, "lock_movement_accounts", pause_after_lock)

    def send_writer():
        with _client(migrated_postgres_url) as local:
            return write(local)

    def send_confirmation():
        with _client(migrated_postgres_url) as local:
            return local.put(
                _confirm_path(plan, primary, str(uuid4())),
                json={
                    **_statement(expected_balance, event_at),
                    "warning_accepted": False,
                },
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer_future = executor.submit(send_writer)
        assert writer_locked.wait(5)
        confirmation_future = executor.submit(send_confirmation)
        try:
            confirmation_future.result(timeout=0.25)
        except FutureTimeout:
            pass
        else:
            pytest.fail("reconciliation did not wait for the Account movement lock")
        finally:
            release_writer.set()

        writer_response = writer_future.result(timeout=5)
        confirmation_response = confirmation_future.result(timeout=5)

    assert writer_response.status_code == 201, writer_response.text
    assert confirmation_response.status_code == 201, confirmation_response.text
    assert confirmation_response.json()["derived_balance"]["amount"] == expected_balance
    assert confirmation_response.json()["discrepancy"]["amount"] == "0.00"


def test_reconciliation_schema_and_revision_contract(migrated_postgres_url: str) -> None:
    engine = session_factory_for(migrated_postgres_url).kw["bind"]
    inspector = inspect(engine)
    assert EXPECTED_REVISION == "006_reconciliation"
    columns = {item["name"]: item for item in inspector.get_columns("reconciliation_sessions")}
    assert columns["statement_at"]["type"].timezone is True
    for name in ("statement_balance", "derived_balance", "discrepancy", "tolerance"):
        assert columns[name]["type"].__class__.__name__.upper() == "NUMERIC"
    assert all(
        column["type"].__class__.__name__.upper() not in {"REAL", "DOUBLE", "FLOAT"}
        for column in columns.values()
    )
    assert {
        "ck_reconciliation_sessions_policy",
        "ck_reconciliation_sessions_tolerance_nonnegative",
        "ck_reconciliation_sessions_amounts_finite",
    } <= {item["name"] for item in inspector.get_check_constraints("reconciliation_sessions")}
    assert {
        "fk_reconciliation_sessions_plan",
        "fk_reconciliation_sessions_plan_account_same_plan",
        "fk_reconciliation_sessions_currency",
    } <= {item["name"] for item in inspector.get_foreign_keys("reconciliation_sessions")}
    assert "ix_reconciliation_sessions_account_confirmed" in {
        item["name"] for item in inspector.get_indexes("reconciliation_sessions")
    }
    assert {
        "uq_transactions_reconciliation_session",
    } <= {item["name"] for item in inspector.get_unique_constraints("transactions")}
    assert {
        "uq_posted_movements_reconciliation_session",
    } <= {item["name"] for item in inspector.get_unique_constraints("posted_account_movements")}
