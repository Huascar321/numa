from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_db(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE reconciliation_sessions, transfer_legs, transfers, transaction_tags, posted_account_movements, "
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


def _create_plan(client: TestClient, *, timezone_name: str = "America/La_Paz") -> str:
    plan_id = str(uuid4())
    res = client.put(
        f"/plans/{plan_id}",
        json={
            "name": "Analytics Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": timezone_name,
        },
    )
    assert res.status_code == 201, res.text
    return plan_id


def _create_account(
    client: TestClient,
    plan_id: str,
    *,
    name: str = "Bank Account",
    currency: str = "BOB",
    account_type: str = "Bank",
) -> str:
    account_id = str(uuid4())
    res = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={
            "name": name,
            "account_type": account_type,
            "currency_code": currency,
        },
    )
    assert res.status_code == 201, res.text
    return account_id


def _create_category_group(client: TestClient, plan_id: str, name: str) -> str:
    group_id = str(uuid4())
    res = client.put(
        f"/plans/{plan_id}/category-groups/{group_id}",
        json={"name": name},
    )
    assert res.status_code == 201, res.text
    return group_id


def _create_category(
    client: TestClient,
    plan_id: str,
    name: str,
    *,
    group_id: str | None = None,
    goal_type: str | None = None,
    goal_target: str | None = None,
    goal_due_month: str | None = None,
) -> str:
    cat_id = str(uuid4())
    payload = {"name": name}
    if group_id:
        payload["group_id"] = group_id
    if goal_type:
        payload["goal_type"] = goal_type
        payload["goal_target"] = goal_target
        if goal_due_month:
            payload["goal_due_month"] = goal_due_month
    res = client.put(f"/plans/{plan_id}/categories/{cat_id}", json=payload)
    assert res.status_code == 201, res.text
    return cat_id


def _create_tag(client: TestClient, plan_id: str, name: str) -> str:
    tag_id = str(uuid4())
    res = client.put(f"/plans/{plan_id}/tags/{tag_id}", json={"name": name})
    assert res.status_code == 201, res.text
    return tag_id


def _create_transaction(
    client: TestClient,
    plan_id: str,
    account_id: str,
    *,
    amount: str,
    currency_code: str = "BOB",
    transaction_type: str = "expense",
    event_at: str = "2026-08-10T12:00:00Z",
    category_id: str | None = None,
    merchant: str | None = None,
    memo: str | None = None,
    location: dict | None = None,
    tags: list[str] | None = None,
) -> str:
    tx_id = str(uuid4())
    payload = {
        "type": transaction_type,
        "account_id": account_id,
        "amount": amount,
        "currency_code": currency_code,
        "event_at": event_at,
        "category_id": category_id,
        "merchant": merchant,
        "memo": memo,
        "location": location,
        "tags": tags or [],
        "source_metadata": {},
        "provenance": {},
    }
    res = client.put(f"/plans/{plan_id}/transactions/{tx_id}", json=payload)
    assert res.status_code == 201, res.text
    return tx_id


def _create_transfer(
    client: TestClient,
    plan_id: str,
    source_acc: str,
    dest_acc: str,
    *,
    outbound: str,
    inbound: str,
    event_at: str = "2026-08-15T10:00:00Z",
    rate_source: str | None = None,
) -> str:
    transfer_id = str(uuid4())
    payload = {
        "source_account_id": source_acc,
        "destination_account_id": dest_acc,
        "outbound_amount": outbound,
        "inbound_amount": inbound,
        "event_at": event_at,
        "provenance": {},
    }
    if rate_source:
        payload["rate_source"] = rate_source
    res = client.put(f"/plans/{plan_id}/transfers/{transfer_id}", json=payload)
    assert res.status_code == 201, res.text
    return transfer_id


def test_summary_kpis_and_transfer_exclusion(client: TestClient):
    plan_id = _create_plan(client)
    acc_bob = _create_account(client, plan_id, currency="BOB")
    acc_bob_2 = _create_account(client, plan_id, currency="BOB", name="Savings")

    # Income of 5000 BOB
    _create_transaction(
        client,
        plan_id,
        acc_bob,
        amount="5000.00",
        transaction_type="income",
        event_at="2026-08-01T10:00:00Z",
    )
    # Expense of 2000 BOB
    _create_transaction(
        client,
        plan_id,
        acc_bob,
        amount="2000.00",
        transaction_type="expense",
        event_at="2026-08-05T14:00:00Z",
    )
    # Transfer of 1000 BOB from Checking to Savings (must be EXCLUDED from income/expense/net)
    _create_transfer(
        client,
        plan_id,
        acc_bob,
        acc_bob_2,
        outbound="1000.00",
        inbound="1000.00",
        event_at="2026-08-10T12:00:00Z",
    )

    res = client.get(f"/plans/{plan_id}/analytics/summary?month=2026-08")
    assert res.status_code == 200
    data = res.json()

    assert data["reporting_currency_code"] == "BOB"
    assert data["total_income"] == "5000.00"
    assert data["total_expenses"] == "2000.00"
    assert data["net_cashflow"] == "3000.00"
    assert data["savings_rate"] == "60.00"
    assert data["transaction_count"] == 2
    assert data["transfers_count"] == 1
    assert "strictly excluded" in data["transfers_excluded_notice"]
    assert data["unconverted_totals"] == []


def test_foreign_currency_unconverted_isolation(client: TestClient):
    plan_id = _create_plan(client)
    acc_usdt = _create_account(client, plan_id, currency="USDT", name="Crypto")

    # USDT Income and Expense in BOB Plan
    _create_transaction(
        client,
        plan_id,
        acc_usdt,
        amount="100.000000",
        currency_code="USDT",
        transaction_type="income",
        event_at="2026-08-02T10:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc_usdt,
        amount="35.500000",
        currency_code="USDT",
        transaction_type="expense",
        event_at="2026-08-03T10:00:00Z",
    )

    res = client.get(f"/plans/{plan_id}/analytics/summary?month=2026-08")
    assert res.status_code == 200
    data = res.json()

    # Reporting currency remains 0.00 because no BOB movements occurred
    assert data["total_income"] == "0.00"
    assert data["total_expenses"] == "0.00"
    assert data["net_cashflow"] == "0.00"
    assert data["savings_rate"] == "0.00"
    assert data["transaction_count"] == 0

    assert len(data["unconverted_totals"]) == 1
    u = data["unconverted_totals"][0]
    assert u["currency_code"] == "USDT"
    assert u["total_income"] == "100.000000"
    assert u["total_expenses"] == "35.500000"
    assert u["net_amount"] == "64.500000"
    assert u["transaction_count"] == 2


def test_category_and_group_breakdowns(client: TestClient):
    plan_id = _create_plan(client)
    acc_bob = _create_account(client, plan_id, currency="BOB")
    acc_usdt = _create_account(client, plan_id, currency="USDT")

    gid = _create_category_group(client, plan_id, "Living")
    cat1 = _create_category(client, plan_id, "Rent", group_id=gid)
    cat2 = _create_category(client, plan_id, "Groceries", group_id=gid)
    cat3 = _create_category(client, plan_id, "Entertainment")  # Ungrouped

    # Expenses
    _create_transaction(
        client,
        plan_id,
        acc_bob,
        amount="1500.00",
        currency_code="BOB",
        category_id=cat1,
        event_at="2026-08-01T10:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc_bob,
        amount="500.00",
        currency_code="BOB",
        category_id=cat2,
        event_at="2026-08-02T10:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc_bob,
        amount="200.00",
        currency_code="BOB",
        category_id=cat3,
        event_at="2026-08-03T10:00:00Z",
    )
    # Foreign expense in Rent
    _create_transaction(
        client,
        plan_id,
        acc_usdt,
        amount="50.000000",
        currency_code="USDT",
        category_id=cat1,
        event_at="2026-08-04T10:00:00Z",
    )

    res = client.get(f"/plans/{plan_id}/analytics/categories?month=2026-08&type=expense")
    assert res.status_code == 200
    data = res.json()

    assert data["total_amount"] == "2200.00"
    categories = {c["category_name"]: c for c in data["categories"]}
    assert categories["Rent"]["amount"] == "1500.00"
    assert categories["Rent"]["percentage"] == "68.18"
    assert len(categories["Rent"]["unconverted_by_currency"]) == 1
    assert categories["Rent"]["unconverted_by_currency"][0]["currency_code"] == "USDT"
    assert categories["Rent"]["unconverted_by_currency"][0]["amount"] == "50.000000"

    assert categories["Groceries"]["amount"] == "500.00"
    assert categories["Groceries"]["percentage"] == "22.73"

    assert categories["Entertainment"]["amount"] == "200.00"
    assert categories["Entertainment"]["percentage"] == "9.09"

    groups = {g["group_name"]: g for g in data["groups"]}
    assert groups["Living"]["amount"] == "2000.00"
    assert groups["Living"]["percentage"] == "90.91"
    assert groups["Ungrouped"]["amount"] == "200.00"


def test_merchant_rankings_and_limits(client: TestClient):
    plan_id = _create_plan(client)
    acc = _create_account(client, plan_id, currency="BOB")

    _create_transaction(
        client,
        plan_id,
        acc,
        amount="300.00",
        merchant="Supermarket Hipermaxi",
        event_at="2026-08-01T10:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="200.00",
        merchant="Supermarket Hipermaxi",
        event_at="2026-08-05T10:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="50.00",
        merchant="Cafe Typica",
        event_at="2026-08-06T10:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="100.00",
        merchant=None,  # Unspecified
        event_at="2026-08-07T10:00:00Z",
    )

    res = client.get(f"/plans/{plan_id}/analytics/merchants?month=2026-08&limit=2")
    assert res.status_code == 200
    data = res.json()

    assert data["total_expense_amount"] == "650.00"
    assert len(data["merchants"]) == 2

    m1 = data["merchants"][0]
    assert m1["merchant"] == "Supermarket Hipermaxi"
    assert m1["total_amount"] == "500.00"
    assert m1["transaction_count"] == 2
    assert m1["average_amount"] == "250.00"
    assert m1["percentage"] == "76.92"


def test_tag_breakdowns(client: TestClient):
    plan_id = _create_plan(client)
    acc = _create_account(client, plan_id, currency="BOB")

    tag_vacation = _create_tag(client, plan_id, "Vacation")
    tag_dining = _create_tag(client, plan_id, "Dining")

    # Transaction with 2 tags
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="120.00",
        tags=[tag_vacation, tag_dining],
        event_at="2026-08-02T10:00:00Z",
    )
    # Transaction with 1 tag
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="80.00",
        tags=[tag_vacation],
        event_at="2026-08-03T10:00:00Z",
    )
    # Untagged transaction
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="50.00",
        tags=[],
        event_at="2026-08-04T10:00:00Z",
    )

    res = client.get(f"/plans/{plan_id}/analytics/tags?month=2026-08&type=expense")
    assert res.status_code == 200
    data = res.json()

    assert data["total_tagged_amount"] == "320.00"  # 200 vacation + 120 dining
    assert data["untagged_amount"] == "50.00"
    assert data["untagged_transaction_count"] == 1

    tags_by_name = {t["tag_name"]: t for t in data["tags"]}
    assert tags_by_name["Vacation"]["amount"] == "200.00"
    assert tags_by_name["Vacation"]["transaction_count"] == 2
    assert tags_by_name["Dining"]["amount"] == "120.00"
    assert tags_by_name["Dining"]["transaction_count"] == 1


def test_cashflow_trends_intervals(client: TestClient):
    plan_id = _create_plan(client)
    acc = _create_account(client, plan_id, currency="BOB")

    _create_transaction(
        client,
        plan_id,
        acc,
        amount="1000.00",
        transaction_type="income",
        event_at="2026-08-01T12:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="200.00",
        transaction_type="expense",
        event_at="2026-08-01T15:00:00Z",
    )
    _create_transaction(
        client,
        plan_id,
        acc,
        amount="300.00",
        transaction_type="expense",
        event_at="2026-08-02T15:00:00Z",
    )

    # Daily interval
    res = client.get(f"/plans/{plan_id}/analytics/trends?month=2026-08&interval=day")
    assert res.status_code == 200
    data = res.json()
    points = {p["bucket_key"]: p for p in data["points"]}

    assert "2026-08-01" in points
    assert points["2026-08-01"]["income"] == "1000.00"
    assert points["2026-08-01"]["expense"] == "200.00"
    assert points["2026-08-01"]["net"] == "800.00"
    assert points["2026-08-01"]["cumulative_net"] == "800.00"

    assert "2026-08-02" in points
    assert points["2026-08-02"]["expense"] == "300.00"
    assert points["2026-08-02"]["net"] == "-300.00"
    assert points["2026-08-02"]["cumulative_net"] == "500.00"


def test_activity_heatmap_and_consent_aware_location(client: TestClient):
    plan_id = _create_plan(client)
    acc = _create_account(client, plan_id, currency="BOB")

    _create_transaction(
        client,
        plan_id,
        acc,
        amount="150.00",
        transaction_type="expense",
        merchant="Plaza Cafe",
        event_at="2026-08-10T14:30:00Z",
        location={"latitude": -17.7833, "longitude": -63.1821, "city": "Santa Cruz"},
    )

    # 1. include_locations=false -> location_clusters must be null / omitted
    res1 = client.get(f"/plans/{plan_id}/analytics/heatmap?month=2026-08&include_locations=false")
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["location_clusters"] is None
    assert len(d1["day_hour_matrix"]) == 168  # 7 days * 24 hours

    # 2. include_locations=true -> location_clusters must contain coordinates
    res2 = client.get(f"/plans/{plan_id}/analytics/heatmap?month=2026-08&include_locations=true")
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["location_clusters"] is not None
    assert len(d2["location_clusters"]) == 1
    loc = d2["location_clusters"][0]
    assert pytest.approx(loc["latitude"], 0.001) == -17.7833
    assert pytest.approx(loc["longitude"], 0.001) == -63.1821
    assert loc["merchant"] == "Plaza Cafe"
    assert loc["amount"] == "150.00"


def test_goals_analytics(client: TestClient):
    plan_id = _create_plan(client)
    acc = _create_account(client, plan_id, currency="BOB")

    # Target balance goal: target 1000
    cat_target = _create_category(
        client,
        plan_id,
        "Emergency Fund",
        goal_type="target_balance",
        goal_target="1000.00",
    )
    # Monthly funding goal: target 200
    cat_monthly = _create_category(
        client,
        plan_id,
        "Gym",
        goal_type="monthly_funding",
        goal_target="200.00",
    )

    # Assign 1000 to Emergency Fund in 2026-08
    ass_id1 = str(uuid4())
    res_a1 = client.put(
        f"/plans/{plan_id}/budget-assignments/{ass_id1}",
        json={"category_id": cat_target, "month": "2026-08", "amount": "1000.00"},
    )
    assert res_a1.status_code == 201, res_a1.text
    # Assign 150 to Gym in 2026-08
    ass_id2 = str(uuid4())
    res_a2 = client.put(
        f"/plans/{plan_id}/budget-assignments/{ass_id2}",
        json={"category_id": cat_monthly, "month": "2026-08", "amount": "150.00"},
    )
    assert res_a2.status_code == 201, res_a2.text

    res = client.get(f"/plans/{plan_id}/analytics/goals?as_of_month=2026-08")
    assert res.status_code == 200
    data = res.json()

    goals = {g["category_name"]: g for g in data["goals"]}
    assert goals["Emergency Fund"]["status"] == "completed"
    assert goals["Emergency Fund"]["progress_percentage"] == "100.00"
    assert goals["Emergency Fund"]["remaining_amount"] == "0.00"

    assert goals["Gym"]["status"] == "underfunded"
    assert goals["Gym"]["progress_percentage"] == "75.00"
    assert goals["Gym"]["remaining_amount"] == "50.00"


def test_transfer_reversals_excluded_from_analytics(client: TestClient):
    plan_id = _create_plan(client)
    acc1 = _create_account(client, plan_id, currency="BOB", name="Acc 1")
    acc2 = _create_account(client, plan_id, currency="BOB", name="Acc 2")

    # Initial Income
    _create_transaction(
        client,
        plan_id,
        acc1,
        amount="3000.00",
        transaction_type="income",
        event_at="2026-08-01T10:00:00Z",
    )

    # Transfer
    t_id = _create_transfer(
        client,
        plan_id,
        acc1,
        acc2,
        outbound="500.00",
        inbound="500.00",
        event_at="2026-08-05T10:00:00Z",
    )

    # Reverse transfer
    rev_id = str(uuid4())
    res_rev = client.put(
        f"/plans/{plan_id}/transfers/{t_id}/reversals/{rev_id}",
        json={
            "event_at": "2026-08-06T10:00:00Z",
            "reversal_reason": "Sent by mistake",
            "provenance": {},
        },
    )
    assert res_rev.status_code == 201

    # Analytics summary
    res = client.get(f"/plans/{plan_id}/analytics/summary?month=2026-08")
    assert res.status_code == 200
    data = res.json()

    # Total income must be exactly 3000.00, expenses 0.00, net 3000.00
    assert data["total_income"] == "3000.00"
    assert data["total_expenses"] == "0.00"
    assert data["net_cashflow"] == "3000.00"
