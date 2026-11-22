from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import session_factory_for
from app.main import create_app
from app.settings import Settings
from test_ledger_core import client, clean_ledger, _plan, _account, _category, _transaction

pytestmark = pytest.mark.postgres


def summary(client, plan, month="2026-02"):
    response = client.get(f"/plans/{plan}/budget/months/{month}")
    assert response.status_code == 200, response.text
    return response.json()


def assign(client, plan, category, amount, month="2026-02"):
    response = client.put(f"/plans/{plan}/budget-assignments/{uuid4()}",
        json=dict(category_id=category, month=month, amount=amount))
    assert response.status_code == 201, response.text


def action(client, plan, payload, identity=None):
    return client.put(f"/plans/{plan}/budget-actions/{identity or uuid4()}", json=payload)


def test_unassigned_continuity_future_funding_and_no_future_income(client):
    plan = _plan(client); bank = _account(client, plan); food = _category(client, plan)
    _transaction(client, plan, bank, transaction_type="income", amount="1000.00", event_at="2026-01-10T12:00:00Z")
    assign(client, plan, food, "800.00", "2026-01")
    assert summary(client, plan)["ready_to_assign"] == "200.00"
    assign(client, plan, food, "50.00", "2026-03")
    _transaction(client, plan, bank, transaction_type="income", amount="900.00", event_at="2026-03-10T12:00:00Z")
    assert summary(client, plan)["ready_to_assign"] == "150.00"
    assert summary(client, plan)["assigned_in_future"] == "50.00"
    assert summary(client, plan, "2026-03")["ready_to_assign"] == "1050.00"


def test_cash_overspending_deducted_once_and_cash_funded_before_credit(client):
    plan = _plan(client); bank = _account(client, plan); card = _account(client, plan, account_type="Credit Card")
    food = _category(client, plan)
    _transaction(client, plan, bank, transaction_type="income", amount="100.00", event_at="2026-01-01T12:00:00Z")
    assign(client, plan, food, "100.00")
    _transaction(client, plan, card, amount="80.00", category_id=food, event_at="2026-02-01T12:00:00Z")
    _transaction(client, plan, bank, amount="120.00", category_id=food, event_at="2026-02-02T12:00:00Z")
    envelope = next(e for e in summary(client, plan)["categories"] if e["category_id"] == food)
    assert (envelope["available"], envelope["cash_overspending"], envelope["credit_card_overspending"]) == ("-100.00", "20.00", "80.00")
    assert summary(client, plan, "2026-03")["ready_to_assign"] == "-20.00"
    assert summary(client, plan, "2026-04")["ready_to_assign"] == "-20.00"


def test_card_reserve_payment_reversal_and_category_guards(client):
    plan = _plan(client); bank = _account(client, plan); card = _account(client, plan, account_type="Credit Card")
    food = _category(client, plan)
    _transaction(client, plan, bank, transaction_type="income", amount="100.00", event_at="2026-02-01T12:00:00Z")
    assign(client, plan, food, "100.00")
    _transaction(client, plan, card, amount="30.00", category_id=food, event_at="2026-02-02T12:00:00Z")
    payment = next(e for e in summary(client, plan)["categories"] if e["payment_account_id"] == card)
    assert payment["available"] == "30.00"
    assert payment["payment_shortfall"] == "0.00"
    transfer = str(uuid4())
    result = client.put(f"/plans/{plan}/transfers/{transfer}", json=dict(source_account_id=bank,
        destination_account_id=card, outbound_amount="20.00", inbound_amount="20.00", event_at="2026-02-03T12:00:00Z", provenance={}))
    assert result.status_code == 201, result.text
    after = summary(client, plan)
    assert next(e for e in after["categories"] if e["payment_account_id"] == card)["available"] == "10.00"
    assert after["activity_total"] == "-30.00"
    assert client.put(f"/plans/{plan}/transfers/{transfer}/reversals/{uuid4()}",
        json=dict(event_at="2026-02-04T12:00:00Z", reversal_reason="Undo payment", provenance={})).status_code == 201
    assert next(e for e in summary(client, plan)["categories"] if e["payment_account_id"] == card)["available"] == "30.00"
    path = f"/plans/{plan}/categories/{payment['category_id']}"
    assert client.patch(path, json={"name":"Changed"}).status_code == 409
    assert client.post(path+"/archive").status_code == 409


def test_budget_move_atomic_retry_conflict_and_no_movements(client, migrated_postgres_url):
    plan = _plan(client); bank = _account(client, plan); food = _category(client, plan); travel = _category(client, plan, "Travel")
    _transaction(client, plan, bank, amount="100.00", transaction_type="income", event_at="2026-02-01T12:00:00Z")
    assign(client, plan, food, "100.00")
    payload = dict(kind="move", month="2026-02", source_category_id=food, category_id=travel, amount="25.00")
    identity = str(uuid4())
    assert action(client, plan, payload, identity).status_code == 201
    assert action(client, plan, payload, identity).status_code == 200
    assert action(client, plan, {**payload,"amount":"26.00"}, identity).status_code == 409
    assert action(client, plan, {**payload,"amount":"100.00"}).status_code == 422
    envelopes = {e["category_id"]: e for e in summary(client, plan)["categories"]}
    assert envelopes[food]["available"] == "75.00"
    assert envelopes[travel]["available"] == "25.00"
    with session_factory_for(migrated_postgres_url)() as session:
        assert session.scalar(text("SELECT count(*) FROM posted_account_movements WHERE plan_id=:p"), {"p":plan}) == 1
    other = _plan(client)
    assert action(client, other, payload).status_code == 404


def test_simultaneous_moves_cannot_spend_same_available_twice(client, migrated_postgres_url):
    plan = _plan(client); source = _category(client, plan); target = _category(client, plan, "Target")
    assign(client, plan, source, "100.00")
    barrier = Barrier(2)
    def move(_):
        with TestClient(create_app(Settings(database_url=migrated_postgres_url))) as concurrent:
            barrier.wait()
            return action(concurrent, plan, dict(kind="move", month="2026-02", source_category_id=source,
                category_id=target, amount="80.00")).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(move, range(2))) == [201,422]


def test_set_assigned_retry_and_target_shortfall(client):
    plan = _plan(client); bank = _account(client, plan); category = _category(client, plan)
    _transaction(client, plan, bank, amount="100.00", transaction_type="income", event_at="2026-02-01T12:00:00Z")
    assert client.patch(f"/plans/{plan}/categories/{category}",
        json=dict(goal_type="monthly_funding",goal_target="80.00")).status_code == 200
    payload = dict(kind="set_assigned", month="2026-02", category_id=category, amount="30.00")
    identity = str(uuid4())
    assert action(client, plan, payload, identity).status_code == 201
    assert action(client, plan, payload, identity).status_code == 200
    assert action(client, plan, dict(kind="fund_target", month="2026-02", category_id=category)).status_code == 201
    envelope = next(e for e in summary(client, plan)["categories"] if e["category_id"] == category)
    assert envelope["assigned"] == "80.00"
    assert envelope["goal"]["required_contribution"] == "0.00"


def test_old_card_debt_can_be_funded_without_spending_twice(client):
    plan=_plan(client);bank=_account(client,plan);card=_account(client,plan,account_type="Credit Card");food=_category(client,plan)
    _transaction(client,plan,card,amount="100.00",category_id=food,event_at="2026-01-02T12:00:00Z")
    _transaction(client,plan,bank,amount="100.00",transaction_type="income",event_at="2026-02-01T12:00:00Z")
    payment=next(e for e in summary(client,plan)["categories"] if e["payment_account_id"]==card)
    assert action(client,plan,dict(kind="set_assigned",month="2026-02",category_id=payment["category_id"],amount="40.00")).status_code==201
    after=summary(client,plan)
    payment=next(e for e in after["categories"] if e["payment_account_id"]==card)
    assert (payment["available"],payment["payment_shortfall"])==("40.00","60.00")
    assert after["ready_to_assign"]=="60.00"
    assert after["activity_total"]=="0.00"


def test_correction_replays_funding_in_its_correct_month(client):
    plan=_plan(client);card=_account(client,plan,account_type="Credit Card");food=_category(client,plan)
    assign(client,plan,food,"100.00")
    transaction,_=_transaction(client,plan,card,amount="30.00",category_id=food,event_at="2026-02-10T12:00:00Z")
    assert client.put(f"/plans/{plan}/transactions/{transaction}/corrections/{uuid4()}",
        json=dict(event_at="2026-03-10T12:00:00Z")).status_code==201
    february=summary(client,plan);march=summary(client,plan,"2026-03")
    assert next(e for e in february["categories"] if e["payment_account_id"]==card)["available"]=="0.00"
    assert next(e for e in march["categories"] if e["payment_account_id"]==card)["available"]=="30.00"
    assert february["activity_total"]=="0.00"
    assert march["activity_total"]=="-30.00"


def test_foreign_card_is_unconverted_without_reporting_currency_reserve(client):
    plan=_plan(client);card=_account(client,plan,account_type="Credit Card",currency="USDT");food=_category(client,plan)
    _transaction(client,plan,card,amount="10.123456",currency="USDT",category_id=food,event_at="2026-02-10T12:00:00Z")
    result=summary(client,plan)
    assert all(e["payment_account_id"] is None for e in result["categories"])
    assert result["activity_total"]=="0.00"
    assert result["unconverted_by_currency"][0]["amount"]=="-10.123456"


def test_exact_action_money_and_canonical_retry(client):
    plan=_plan(client);category=_category(client,plan);identity=str(uuid4())
    payload=dict(kind="set_assigned",month="2026-02",category_id=category,amount="9007199254740993.01")
    assert action(client,plan,payload,identity).status_code==201
    assert action(client,plan,{**payload,"amount":"9007199254740993.010"},identity).status_code==200
    assert next(e for e in summary(client,plan)["categories"] if e["category_id"]==category)["assigned"]==payload["amount"]
    assert action(client,plan,{**payload,"amount":1.01}).status_code==422


def test_payment_identity_and_action_receipts_are_protected_in_sql(client,migrated_postgres_url):
    plan=_plan(client);card=_account(client,plan,account_type="Credit Card")
    payment=next(e for e in summary(client,plan)["categories"] if e["payment_account_id"]==card)
    receipt=str(uuid4())
    assert action(client,plan,dict(kind="set_assigned",month="2026-02",category_id=payment["category_id"],amount="1.00"),receipt).status_code==201
    for query,identity in [("UPDATE categories SET name='Changed' WHERE id=:id",payment["category_id"]),
                           ("DELETE FROM budget_actions WHERE id=:id",receipt)]:
        with pytest.raises(DBAPIError),session_factory_for(migrated_postgres_url).begin() as session:
            session.execute(text(query),{"id":identity})


def test_positive_card_balance_is_cash_until_it_creates_debt(client):
    plan=_plan(client);card=_account(client,plan,account_type="Credit Card");food=_category(client,plan)
    _transaction(client,plan,card,amount="100.00",transaction_type="income",event_at="2026-02-01T12:00:00Z")
    assign(client,plan,food,"100.00")
    _transaction(client,plan,card,amount="130.00",category_id=food,event_at="2026-02-02T12:00:00Z")
    result=summary(client,plan)
    envelope=next(e for e in result["categories"] if e["category_id"]==food)
    payment=next(e for e in result["categories"] if e["payment_account_id"]==card)
    assert (result["ready_to_assign"],result["credit_cash_inflow"])==("0.00","100.00")
    assert (envelope["cash_overspending"],envelope["credit_card_overspending"])==("0.00","30.00")
    assert (payment["available"],payment["payment_debt"])==("0.00","30.00")


def test_credit_inflow_only_funds_positive_balance_and_overpayment_is_visible(client):
    plan=_plan(client);bank=_account(client,plan);card=_account(client,plan,account_type="Credit Card");food=_category(client,plan)
    _transaction(client,plan,bank,amount="100.00",transaction_type="income",event_at="2026-02-01T12:00:00Z")
    assign(client,plan,food,"20.00")
    _transaction(client,plan,card,amount="20.00",category_id=food,event_at="2026-02-02T12:00:00Z")
    transfer=str(uuid4())
    assert client.put(f"/plans/{plan}/transfers/{transfer}",json=dict(source_account_id=bank,destination_account_id=card,
        outbound_amount="30.00",inbound_amount="30.00",event_at="2026-02-03T12:00:00Z",provenance={})).status_code==201
    result=summary(client,plan)
    assert result["ready_to_assign"]=="90.00"
    assert next(e for e in result["categories"] if e["payment_account_id"]==card)["available"]=="-10.00"
    assert summary(client,plan,"2026-03")["ready_to_assign"]=="80.00"


def test_cash_advance_adds_available_cash_and_reversal_removes_it(client):
    plan=_plan(client);bank=_account(client,plan);card=_account(client,plan,account_type="Credit Card")
    transfer=str(uuid4())
    assert client.put(f"/plans/{plan}/transfers/{transfer}",json=dict(source_account_id=card,destination_account_id=bank,
        outbound_amount="50.00",inbound_amount="50.00",event_at="2026-02-03T12:00:00Z",provenance={})).status_code==201
    assert summary(client,plan)["ready_to_assign"]=="50.00"
    assert client.put(f"/plans/{plan}/transfers/{transfer}/reversals/{uuid4()}",
        json=dict(event_at="2026-02-04T12:00:00Z",reversal_reason="Undo cash advance",provenance={})).status_code==201
    assert summary(client,plan)["ready_to_assign"]=="0.00"
