from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_factory_for
from app.main import create_app
from app.settings import Settings
from app.ledger.service import transfer_rate


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean(postgres_sessions: sessionmaker[Session]):
    statement = text("TRUNCATE transfer_legs, transfers, transaction_tags, posted_account_movements, transaction_corrections, monthly_budget_assignments, transactions, tags, categories, category_groups, accounts, plans CASCADE")
    with postgres_sessions.begin() as session:
        session.execute(statement)
    yield


@pytest.fixture
def client(migrated_postgres_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=migrated_postgres_url)))


def setup(client: TestClient, currencies: tuple[str, str] = ("BOB", "BOB")) -> tuple[str, str, str]:
    plan, first, second = str(uuid4()), str(uuid4()), str(uuid4())
    assert client.put(f"/plans/{plan}", json={"name": "Transfer plan", "reporting_currency_code": "BOB", "budget_timezone": "America/La_Paz"}).status_code == 201
    for account, currency in ((first, currencies[0]), (second, currencies[1])):
        assert client.put(f"/plans/{plan}/accounts/{account}", json={"name": account, "account_type": "Bank", "currency_code": currency}).status_code == 201
    return plan, first, second


def payload(source: str, destination: str, *, outbound: str = "10.00", inbound: str = "10.00", source_evidence: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {"source_account_id": source, "destination_account_id": destination, "outbound_amount": outbound, "inbound_amount": inbound, "event_at": "2026-01-15T12:00:00Z", "memo": "  caf\u00e9  ", "provenance": {"kind": "test"}}
    if source_evidence is not None:
        result["rate_source"] = source_evidence
    return result


def test_same_currency_pair_idempotency_scale_and_grouped_projection(client: TestClient) -> None:
    plan, source, destination = setup(client)
    transfer = str(uuid4())
    body = payload(source, destination)
    first = client.put(f"/plans/{plan}/transfers/{transfer}", json=body)
    replay = client.put(f"/plans/{plan}/transfers/{transfer}", json={**body, "memo": "caf\u00e9"})
    assert [first.status_code, replay.status_code] == [201, 200]
    data = first.json()
    assert data["memo"] == "caf\u00e9" and data["rate"] == "1.00000000000000000000000000000000000000"
    assert "rate_source" not in data and [leg["role"] for leg in data["legs"]] == ["outbound", "inbound"]
    assert len(client.get(f"/plans/{plan}/transactions").json()) == 1
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination, outbound="10.001", inbound="10.001")).status_code == 422
    assert client.get(f"/plans/{plan}/accounts/{source}/balance").json()["amount"] == "-10.00"
    assert client.get(f"/plans/{plan}/accounts/{destination}/balance").json()["amount"] == "10.00"


def test_cross_currency_fx_ties_domain_and_reversal(client: TestClient) -> None:
    plan, source, destination = setup(client, ("USDT", "USDT"))
    # USDT permits six places, so create BOB/USDT accounts for ordinary evidence.
    plan, source, destination = setup(client, ("BOB", "USDT"))
    cross = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination, outbound="100.00", inbound="10.000000", source_evidence=" manual "))
    assert cross.status_code == 201 and cross.json()["rate"] == "10.00000000000000000000000000000000000000"
    assert cross.json()["rate_source"] == "manual"
    # Inputs beyond the selected Account scale and NUMERIC(38,18) domain fail before writes.
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination, outbound="100000000000000000000.00", inbound="0.000001", source_evidence="x")).status_code == 422
    reversal = client.put(f"/plans/{plan}/transfers/{cross.json()['id']}/reversals/{uuid4()}", json={"event_at": "2026-02-01T00:00:00Z", "reversal_reason": " reason ", "provenance": {}})
    assert reversal.status_code == 201 and reversal.json()["reversal_reason"] == "reason"
    assert reversal.json()["rate_source"] == "reversal"


def test_direct_sql_duplicate_movement_and_history_rewrite_are_rejected(client: TestClient, migrated_postgres_url: str) -> None:
    plan, source, destination = setup(client)
    created = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).json()
    factory = session_factory_for(migrated_postgres_url)
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(text("""
                INSERT INTO posted_account_movements (id, plan_id, account_id, transaction_id, currency_code, signed_amount, transaction_type, effective_at, category_id, source, source_metadata, provenance, movement_kind, correction_sequence)
                SELECT :id, plan_id, account_id, transaction_id, currency_code, signed_amount, transaction_type, effective_at, category_id, source, source_metadata, provenance, movement_kind, correction_sequence
                FROM posted_account_movements WHERE id = :movement
            """), {"id": uuid4(), "movement": created["legs"][0]["movement_id"]})
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(text("UPDATE transfers SET memo = 'rewrite' WHERE id = :id"), {"id": created["id"]})
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM posted_account_movements WHERE plan_id=:plan"), {"plan": plan}) == 2


def test_concurrent_create_is_one_pair(client: TestClient, migrated_postgres_url: str) -> None:
    plan, source, destination = setup(client)
    transfer, body, barrier = str(uuid4()), payload(source, destination), Barrier(2)
    def send() -> int:
        with TestClient(create_app(Settings(database_url=migrated_postgres_url))) as local:
            barrier.wait()
            return local.put(f"/plans/{plan}/transfers/{transfer}", json=body).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: send(), range(2))) == [200, 201]
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(text("SELECT count(*) FROM transfers WHERE id=:id"), {"id": transfer}) == 1
        assert session.scalar(text("SELECT count(*) FROM transfer_legs WHERE transfer_id=:id"), {"id": transfer}) == 2
        assert session.scalar(text("SELECT count(*) FROM posted_account_movements m JOIN transfer_legs l ON l.transaction_id=m.transaction_id WHERE l.transfer_id=:id"), {"id": transfer}) == 2


@pytest.mark.parametrize(("raw", "canonical"), [("  cafe\u0301  ", "caf\u00e9"), ("\u00a0 Keep \u00a0", "\u00a0 Keep \u00a0"), (" A  B ", "A  B")])
def test_canonical_text_python_api_and_sql_function_agree(client: TestClient, migrated_postgres_url: str, raw: str, canonical: str) -> None:
    plan, source, destination = setup(client)
    response = client.put(f"/plans/{plan}/transfers/{uuid4()}", json={**payload(source, destination), "memo": raw})
    assert response.status_code == 201
    assert response.json()["memo"] == canonical
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(text("SELECT canonical_transfer_text(:value)"), {"value": raw}) == canonical


@pytest.mark.parametrize("value", ["bad\u0001", "bad\u007f", "bad\u0085"])
def test_canonical_controls_are_rejected_by_api_and_sql(client: TestClient, migrated_postgres_url: str, value: str) -> None:
    plan, source, destination = setup(client)
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json={**payload(source, destination), "memo": value}).status_code == 422
    with session_factory_for(migrated_postgres_url)() as session:
        with pytest.raises(Exception):
            session.execute(text("SELECT canonical_transfer_text(:value)"), {"value": value})


def test_transfer_correction_is_conflict_and_budget_excludes_both_legs(client: TestClient) -> None:
    plan, source, destination = setup(client)
    created = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).json()
    correction = client.put(f"/plans/{plan}/transactions/{created['legs'][0]['transaction_id']}/corrections/{uuid4()}", json={"memo": "no"})
    assert correction.status_code == 409
    summary = client.get(f"/plans/{plan}/budget/months/2026-01").json()
    assert summary["ready_to_assign"] == "0.00"
    assert summary["activity_total"] == "0.00"
    assert summary["unconverted_by_currency"] == []


def test_transfer_schema_has_exact_types_composite_keys_uniques_and_indexes(client: TestClient, migrated_postgres_url: str) -> None:
    # Inspect the migrated database, rather than migration source, so this also
    # proves PostgreSQL accepted the complete DDL contract.
    engine = session_factory_for(migrated_postgres_url).kw["bind"]
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("transfers")}
    assert str(columns["outbound_amount"]["type"]) == "NUMERIC(38, 18)"
    assert str(columns["inbound_amount"]["type"]) == "NUMERIC(38, 18)"
    assert str(columns["rate"]["type"]) == "NUMERIC(76, 38)"
    assert columns["event_at"]["type"].timezone is True
    assert columns["creation_fingerprint"]["nullable"] is False
    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("transfers")}
    assert {"fk_transfers_source_account_same_plan", "fk_transfers_destination_account_same_plan", "fk_transfers_reversal_same_plan"} <= foreign_keys
    uniques = {key["name"] for key in inspector.get_unique_constraints("transfer_legs")}
    assert {"uq_transfer_legs_transfer_role", "uq_transfer_legs_transaction"} <= uniques
    assert {index["name"] for index in inspector.get_indexes("transfers")} >= {"ix_transfers_plan_event", "ix_transfers_plan_reversal"}


@pytest.mark.parametrize("mutate", [
    lambda body: {**body, "source_account_id": body["destination_account_id"]},
    lambda body: {**body, "outbound_amount": "0"},
    lambda body: {**body, "outbound_amount": "1.001"},
    lambda body: {**body, "event_at": "2026-01-15T12:00:00"},
    lambda body: {**body, "memo": "bad\u0001"},
    lambda body: {**body, "rate_source": None},
])
def test_invalid_same_currency_requests_leave_no_durable_effects(client: TestClient, mutate) -> None:
    plan, source, destination = setup(client)
    response = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=mutate(payload(source, destination)))
    assert response.status_code == 422
    assert client.get(f"/plans/{plan}/transfers").json() == []
    assert client.get(f"/plans/{plan}/transactions").json() == []
    assert client.get(f"/plans/{plan}/accounts/{source}/balance").json()["amount"] == "0.00"
    assert client.get(f"/plans/{plan}/accounts/{destination}/balance").json()["amount"] == "0.00"


def test_cross_plan_unknown_and_archived_accounts_are_isolated_without_writes(client: TestClient) -> None:
    plan, source, destination = setup(client)
    other_plan, other_source, _ = setup(client)
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, other_source)).status_code == 404
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, str(uuid4()))).status_code == 404
    assert client.post(f"/plans/{plan}/accounts/{destination}/archive").status_code == 200
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).status_code == 422
    assert client.get(f"/plans/{plan}/transfers").json() == []
    assert client.get(f"/plans/{other_plan}/transfers").json() == []


def test_concurrent_conflicting_create_leaves_the_winning_pair_only(client: TestClient, migrated_postgres_url: str) -> None:
    plan, source, destination = setup(client)
    transfer, barrier = str(uuid4()), Barrier(2)
    bodies = [payload(source, destination), payload(source, destination, outbound="11.00", inbound="11.00")]
    def send(body: dict[str, object]) -> int:
        with TestClient(create_app(Settings(database_url=migrated_postgres_url))) as local:
            barrier.wait()
            return local.put(f"/plans/{plan}/transfers/{transfer}", json=body).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(send, bodies)) == [201, 409]
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(text("SELECT count(*) FROM transfers WHERE id=:id"), {"id": transfer}) == 1
        assert session.scalar(text("SELECT count(*) FROM transfer_legs WHERE transfer_id=:id"), {"id": transfer}) == 2


def test_reversal_is_idempotent_compensatory_and_can_form_an_immediate_parent_chain(client: TestClient) -> None:
    plan, source, destination = setup(client, ("BOB", "USDT"))
    original = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination, outbound="100.00", inbound="10.000000", source_evidence="manual"))
    assert original.status_code == 201
    reversal_id = str(uuid4())
    reversal_payload = {"event_at": "2026-02-01T00:00:00Z", "reversal_reason": " duplicate ", "memo": "  undo ", "provenance": {}}
    first = client.put(f"/plans/{plan}/transfers/{original.json()['id']}/reversals/{reversal_id}", json=reversal_payload)
    replay = client.put(f"/plans/{plan}/transfers/{original.json()['id']}/reversals/{reversal_id}", json=reversal_payload)
    assert [first.status_code, replay.status_code] == [201, 200]
    child = first.json()
    assert child["reverses_transfer_id"] == original.json()["id"]
    assert child["outbound_amount"] == "10.000000" and child["inbound_amount"] == "100.00"
    assert child["rate"] == "0.10000000000000000000000000000000000000" and child["rate_source"] == "reversal"
    assert child["memo"] == "undo" and child["reversal_reason"] == "duplicate"
    assert client.get(f"/plans/{plan}/transfers/{original.json()['id']}").json()["memo"] == "café"
    grandchild = client.put(f"/plans/{plan}/transfers/{reversal_id}/reversals/{uuid4()}", json={"event_at": "2026-03-01T00:00:00Z", "reversal_reason": "undo undo", "provenance": {}})
    assert grandchild.status_code == 201 and grandchild.json()["reverses_transfer_id"] == reversal_id
    assert client.get(f"/plans/{plan}/accounts/{source}/balance").json()["amount"] == "-100.00"
    assert client.get(f"/plans/{plan}/accounts/{destination}/balance").json()["amount"] == "10.000000"


def test_transfer_routes_and_direct_leg_read_are_plan_scoped(client: TestClient) -> None:
    plan, source, destination = setup(client)
    other_plan, _, _ = setup(client)
    created = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).json()
    assert client.get(f"/plans/{other_plan}/transfers/{created['id']}").status_code == 404
    assert client.get(f"/plans/{other_plan}/transfers").json() == []
    assert client.get(f"/plans/{other_plan}/transactions/{created['legs'][0]['transaction_id']}").status_code == 404
    assert client.put(f"/plans/{other_plan}/transfers/{created['id']}/reversals/{uuid4()}", json={"event_at": "2026-02-01T00:00:00Z", "reversal_reason": "no", "provenance": {}}).status_code == 404
    leg = client.get(f"/plans/{plan}/transactions/{created['legs'][0]['transaction_id']}").json()
    assert leg["transfer_id"] == created["id"] and leg["transfer_role"] == "outbound"


def test_create_replay_and_conflict_use_durable_fingerprint_after_account_archival(client: TestClient) -> None:
    plan, source, destination = setup(client)
    transfer_id, body = str(uuid4()), payload(source, destination)
    assert client.put(f"/plans/{plan}/transfers/{transfer_id}", json=body).status_code == 201
    assert client.post(f"/plans/{plan}/accounts/{source}/archive").status_code == 200
    assert client.put(f"/plans/{plan}/transfers/{transfer_id}", json=body).status_code == 200
    assert client.put(f"/plans/{plan}/transfers/{transfer_id}", json={**body, "memo": "different"}).status_code == 409
    assert len(client.get(f"/plans/{plan}/transfers").json()) == 1


def test_reversal_replay_and_conflict_use_durable_fingerprint_after_account_archival(client: TestClient) -> None:
    plan, source, destination = setup(client)
    original = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).json()
    reversal_id = str(uuid4())
    reversal = {"event_at": "2026-02-01T00:00:00Z", "reversal_reason": "undo", "provenance": {}}
    assert client.put(f"/plans/{plan}/transfers/{original['id']}/reversals/{reversal_id}", json=reversal).status_code == 201
    assert client.post(f"/plans/{plan}/accounts/{source}/archive").status_code == 200
    assert client.put(f"/plans/{plan}/transfers/{original['id']}/reversals/{reversal_id}", json=reversal).status_code == 200
    assert client.put(f"/plans/{plan}/transfers/{original['id']}/reversals/{reversal_id}", json={**reversal, "reversal_reason": "different"}).status_code == 409


@pytest.mark.parametrize("same_id", [True, False])
def test_concurrent_reversals_are_idempotent_or_conflicting_with_one_child(client: TestClient, migrated_postgres_url: str, same_id: bool) -> None:
    plan, source, destination = setup(client)
    original = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).json()
    barrier = Barrier(2)
    reversal_ids = [str(uuid4()), str(uuid4())]
    if same_id:
        reversal_ids[1] = reversal_ids[0]
    reversal = {"event_at": "2026-02-01T00:00:00Z", "reversal_reason": "undo", "provenance": {}}
    def send(reversal_id: str) -> int:
        with TestClient(create_app(Settings(database_url=migrated_postgres_url))) as local:
            barrier.wait()
            return local.put(f"/plans/{plan}/transfers/{original['id']}/reversals/{reversal_id}", json=reversal).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(send, reversal_ids)) == ([200, 201] if same_id else [201, 409])
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(text("SELECT count(*) FROM transfers WHERE reverses_transfer_id=:id"), {"id": original["id"]}) == 1
        assert session.scalar(text("SELECT count(*) FROM transfer_legs WHERE transfer_id IN (SELECT id FROM transfers WHERE reverses_transfer_id=:id)"), {"id": original["id"]}) == 2
    assert client.get(f"/plans/{plan}/accounts/{source}/balance").json()["amount"] == "0.00"
    assert client.get(f"/plans/{plan}/accounts/{destination}/balance").json()["amount"] == "0.00"


def test_transfer_uuid_owned_by_another_plan_is_not_disclosed_or_written(client: TestClient) -> None:
    plan_a, source_a, destination_a = setup(client)
    plan_b, source_b, destination_b = setup(client)
    transfer_id = str(uuid4())
    created = client.put(f"/plans/{plan_a}/transfers/{transfer_id}", json=payload(source_a, destination_a))
    assert created.status_code == 201
    assert client.put(f"/plans/{plan_b}/transfers/{transfer_id}", json=payload(source_b, destination_b)).status_code == 404
    assert client.put(f"/plans/{plan_b}/transfers/{transfer_id}", json=payload(source_b, destination_b, outbound="11.00", inbound="11.00")).status_code == 404
    assert client.get(f"/plans/{plan_b}/transfers").json() == []
    assert client.get(f"/plans/{plan_b}/accounts/{source_b}/balance").json()["amount"] == "0.00"
    assert client.get(f"/plans/{plan_b}/accounts/{destination_b}/balance").json()["amount"] == "0.00"


def test_nonterminating_sql_rate_guard_commits_exact_38_place_rate_and_reversal(client: TestClient) -> None:
    plan, source, destination = setup(client, ("USDT", "BOB"))
    transfer_id = str(uuid4())
    body = payload(source, destination, outbound="1.000000", inbound="3.00", source_evidence="manual")
    created = client.put(f"/plans/{plan}/transfers/{transfer_id}", json=body)
    assert created.status_code == 201
    assert created.json()["rate"] == "0.33333333333333333333333333333333333333"
    assert client.put(f"/plans/{plan}/transfers/{transfer_id}", json=body).status_code == 200
    reversal = client.put(f"/plans/{plan}/transfers/{transfer_id}/reversals/{uuid4()}", json={"event_at": "2026-02-01T00:00:00Z", "reversal_reason": "undo", "provenance": {}})
    assert reversal.status_code == 201
    assert reversal.json()["rate"] == "3.00000000000000000000000000000000000000"


def test_sql_rate_uses_exact_integer_divmod_for_adversarial_near_divisor_remainder(client: TestClient, migrated_postgres_url: str) -> None:
    plan, source, destination = setup(client, ("BOB", "USDT"))
    outbound = Decimal("99999999999999999998.99")
    inbound = Decimal("9999999999999999.999999")
    expected = transfer_rate(outbound, inbound)
    factory = session_factory_for(migrated_postgres_url)
    with factory() as session:
        sql_rate = session.scalar(text("SELECT numa_transfer_rate(:outbound, :inbound)"), {"outbound": outbound, "inbound": inbound})
    assert Decimal(sql_rate) == expected
    body = payload(source, destination, outbound=str(outbound), inbound=str(inbound), source_evidence="manual")
    transfer_id = str(uuid4())
    created = client.put(f"/plans/{plan}/transfers/{transfer_id}", json=body)
    assert created.status_code == 201
    assert Decimal(created.json()["rate"]) == expected
    assert client.put(f"/plans/{plan}/transfers/{transfer_id}", json=body).status_code == 200


@pytest.mark.parametrize("special", ["NaN", "Infinity", "-Infinity"])
def test_api_rejects_nonfinite_transfer_amounts_without_writes(client: TestClient, special: str) -> None:
    plan, source, destination = setup(client)
    assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination, outbound=special)).status_code == 422
    assert client.get(f"/plans/{plan}/transfers").json() == []


@pytest.mark.parametrize("special", ["NaN", "Infinity", "-Infinity"])
def test_sql_rejects_nonfinite_transfer_root_transaction_and_movement(client: TestClient, migrated_postgres_url: str, special: str) -> None:
    plan, source, destination = setup(client)
    created = client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination)).json()
    factory = session_factory_for(migrated_postgres_url)
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(text("""INSERT INTO transfers (id, plan_id, source_account_id, destination_account_id, outbound_amount, outbound_currency_code, inbound_amount, inbound_currency_code, event_at, rate, rate_source, memo, reversal_reason, provenance, creation_fingerprint)
                SELECT :id, plan_id, source_account_id, destination_account_id, CAST(:special AS numeric), outbound_currency_code, inbound_amount, inbound_currency_code, event_at, rate, rate_source, memo, reversal_reason, provenance, :fingerprint FROM transfers WHERE id=:source"""), {"id": uuid4(), "source": created["id"], "special": special, "fingerprint": "f" * 64})
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(text("""INSERT INTO transactions (id, plan_id, account_id, type, amount, currency_code, event_at, category_id, source, source_metadata, provenance, creation_fingerprint)
                VALUES (:id, :plan, :account, 'transfer', CAST(:special AS numeric), 'BOB', now(), NULL, 'transfer', '{}'::jsonb, '{}'::jsonb, :fingerprint)"""), {"id": uuid4(), "plan": plan, "account": source, "special": special, "fingerprint": "f" * 64})
    with pytest.raises(Exception):
        with factory.begin() as session:
            session.execute(text("""INSERT INTO posted_account_movements (id, plan_id, account_id, transaction_id, correction_id, correction_sequence, currency_code, signed_amount, transaction_type, effective_at, category_id, source, source_metadata, provenance, movement_kind)
                SELECT :id, plan_id, account_id, transaction_id, NULL, 0, currency_code, CAST(:special AS numeric), 'transfer', effective_at, NULL, 'transfer', '{}'::jsonb, '{}'::jsonb, 'original' FROM posted_account_movements WHERE id=:movement"""), {"id": uuid4(), "movement": created["legs"][0]["movement_id"], "special": special})
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM transfers WHERE plan_id=:plan"), {"plan": plan}) == 1


def test_account_balances_support_more_than_default_decimal_precision_from_transfers(client: TestClient) -> None:
    plan, source, destination = setup(client, ("USDT", "USDT"))
    amount = "99999999999999999999.999999"
    for _ in range(101):
        assert client.put(f"/plans/{plan}/transfers/{uuid4()}", json=payload(source, destination, outbound=amount, inbound=amount)).status_code == 201
    accounts = {account["id"]: account for account in client.get(f"/plans/{plan}/accounts").json()}
    expected = "10099999999999999999999.999899"
    assert accounts[destination]["balance"] == {"amount": expected, "currency": "USDT"}
    assert accounts[source]["balance"] == {"amount": f"-{expected}", "currency": "USDT"}

    bob_plan, bob_source, bob_destination = setup(client)
    assert client.put(f"/plans/{bob_plan}/transfers/{uuid4()}", json=payload(bob_source, bob_destination)).status_code == 201
    bob_accounts = {account["id"]: account for account in client.get(f"/plans/{bob_plan}/accounts").json()}
    assert bob_accounts[bob_destination]["balance"] == {"amount": "10.00", "currency": "BOB"}
