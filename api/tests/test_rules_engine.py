from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Account, Plan
from app.db import session_factory_for
from app.ledger.models import Category, Transaction
from app.main import create_app
from app.rules.engine import evaluate_rules_for_candidate
from app.rules.models import Rule
from app.rules.schemas import RuleCreate, RuleUpdate
from app.rules.service import (
    apply_rules_to_candidate,
    create_rule,
    get_rule,
    list_rules,
    replay_plan_rules,
    update_rule,
)
from app.settings import Settings
from app.watchers.models import WatcherCandidate, WatcherRawMessage, WatcherSource


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_rules_db(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE rules, watcher_candidates, watcher_account_mappings, "
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
            "name": "Rules Test Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": "America/La_Paz",
        },
    )
    assert resp.status_code == 201
    return plan_id


def create_test_account(
    client: TestClient,
    plan_id: str,
    name: str = "Test Bank",
    currency_code: str = "BOB",
) -> str:
    account_id = str(uuid4())
    resp = client.put(
        f"/plans/{plan_id}/accounts/{account_id}",
        json={
            "name": name,
            "account_type": "Bank",
            "currency_code": currency_code,
        },
    )
    assert resp.status_code == 201
    return account_id


def make_candidate(
    plan_id: UUID,
    candidate_type: str = "bcp_qr",
    reported_amount: Decimal = Decimal("50.00"),
    reported_currency: str = "BOB",
    merchant: str | None = "Fidalga",
    raw_glosa: str | None = None,
    glosa: str | None = None,
    account_suffix: str | None = None,
    direction: str | None = "debit",
    status: str = "pending",
) -> WatcherCandidate:
    now = datetime.now(timezone.utc)
    return WatcherCandidate(
        id=uuid4(),
        plan_id=plan_id,
        raw_message_id=uuid4(),
        source_id=uuid4(),
        candidate_type=candidate_type,
        status=status,
        event_at=now,
        notification_at=now,
        reported_amount=reported_amount,
        reported_currency=reported_currency,
        settlement_amount=None,
        settlement_currency=None,
        merchant=merchant,
        subject=f"{candidate_type} notice",
        sender="notice@example.com",
        provider_uuid="prov-uuid-1",
        message_id_header="<msg-1@example.com>",
        quarantine_reason=None,
        rule_evidence=[],
        glosa=glosa,
        raw_glosa=raw_glosa,
        qr_subtype=None,
        account_suffix=account_suffix,
        direction=direction,
        raw_payload={},
        provenance={},
        transaction_id=None,
        creation_fingerprint=f"cand:{uuid4()}",
        created_at=now,
        updated_at=now,
    )


class TestRulesEngineUnit:
    def test_priority_ordering_execution(self):
        plan_id = uuid4()
        now = datetime.now(timezone.utc)
        cand = make_candidate(plan_id, merchant="Uber")

        rule_low_priority = Rule(
            id=uuid4(),
            plan_id=plan_id,
            name="Low priority (runs second)",
            stage="watcher_candidate",
            priority=200,
            enabled=True,
            predicate={"merchant": "Uber"},
            action={"qr_subtype": "secondary"},
            version=1,
            creation_fingerprint="r1",
            created_at=now,
            updated_at=now,
        )
        rule_high_priority = Rule(
            id=uuid4(),
            plan_id=plan_id,
            name="High priority (runs first)",
            stage="watcher_candidate",
            priority=10,
            enabled=True,
            predicate={"merchant": "Uber"},
            action={"merchant": "Uber BV"},
            version=1,
            creation_fingerprint="r2",
            created_at=now,
            updated_at=now,
        )

        outcome = evaluate_rules_for_candidate(cand, [rule_low_priority, rule_high_priority])
        assert outcome.has_conflict is False
        assert len(outcome.rule_evidence) == 2
        # High priority evaluated first
        assert outcome.rule_evidence[0]["rule_name"] == "High priority (runs first)"
        assert outcome.rule_evidence[1]["rule_name"] == "Low priority (runs second)"

    def test_conflicting_rules_cause_quarantine_with_conflict_evidence(self):
        plan_id = uuid4()
        now = datetime.now(timezone.utc)
        cand = make_candidate(plan_id, raw_glosa="BM BM QR PAGO DE PRODUCTOS")

        rule1 = Rule(
            id=uuid4(),
            plan_id=plan_id,
            name="Set subtype to product_payment",
            stage="watcher_candidate",
            priority=10,
            enabled=True,
            predicate={"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"},
            action={"qr_subtype": "product_payment"},
            version=1,
            creation_fingerprint="r1",
            created_at=now,
            updated_at=now,
        )
        rule2 = Rule(
            id=uuid4(),
            plan_id=plan_id,
            name="Conflicting rule: set subtype to interbank",
            stage="watcher_candidate",
            priority=20,
            enabled=True,
            predicate={"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"},
            action={"qr_subtype": "interbank"},
            version=1,
            creation_fingerprint="r2",
            created_at=now,
            updated_at=now,
        )

        outcome = evaluate_rules_for_candidate(cand, [rule1, rule2])
        assert outcome.has_conflict is True
        assert outcome.conflict_reason == "rule_conflict"
        conflict_items = [e for e in outcome.rule_evidence if e["result"] == "conflict"]
        assert len(conflict_items) == 1
        assert conflict_items[0]["conflicting_field"] == "qr_subtype"
        assert conflict_items[0]["existing_value"] == "product_payment"
        assert conflict_items[0]["attempted_value"] == "interbank"

    def test_exact_qr_glosa_matching_and_null_glosa_preservation(self):
        plan_id = uuid4()
        now = datetime.now(timezone.utc)

        rule_product = Rule(
            id=uuid4(),
            plan_id=plan_id,
            name="Classify QR product payment",
            stage="watcher_candidate",
            priority=10,
            enabled=True,
            predicate={"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"},
            action={"qr_subtype": "product_payment"},
            version=1,
            creation_fingerprint="r1",
            created_at=now,
            updated_at=now,
        )

        # 1. Matching candidate
        cand_with_glosa = make_candidate(
            plan_id,
            raw_glosa="BM BM QR PAGO DE PRODUCTOS",
            glosa="BM BM QR PAGO DE PRODUCTOS",
        )
        outcome1 = evaluate_rules_for_candidate(cand_with_glosa, [rule_product])
        assert outcome1.has_conflict is False
        assert outcome1.applied_fields.get("qr_subtype") == "product_payment"

        # 2. Candidate with null glosa MUST NOT match and glosa MUST remain None
        cand_null_glosa = make_candidate(
            plan_id,
            raw_glosa=None,
            glosa=None,
        )
        outcome2 = evaluate_rules_for_candidate(cand_null_glosa, [rule_product])
        assert outcome2.has_conflict is False
        assert "qr_subtype" not in outcome2.applied_fields
        assert cand_null_glosa.glosa is None
        assert cand_null_glosa.raw_glosa is None


class TestRulesApiAndService:
    def test_rules_crud_lifecycle(self, client: TestClient):
        plan_id = create_test_plan(client)

        # 1. Create rule
        create_resp = client.post(
            f"/plans/{plan_id}/rules",
            json={
                "name": "Classify BCP QR Product Payment",
                "stage": "watcher_candidate",
                "priority": 10,
                "enabled": True,
                "predicate": {"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"},
                "action": {"qr_subtype": "product_payment"},
            },
        )
        assert create_resp.status_code == 201
        rule = create_resp.json()
        rule_id = rule["id"]
        assert rule["name"] == "Classify BCP QR Product Payment"
        assert rule["priority"] == 10
        assert rule["version"] == 1

        # 2. List rules
        list_resp = client.get(f"/plans/{plan_id}/rules")
        assert list_resp.status_code == 200
        rules = list_resp.json()
        assert len(rules) == 1
        assert rules[0]["id"] == rule_id

        # 3. Get rule
        get_resp = client.get(f"/plans/{plan_id}/rules/{rule_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == rule_id

        # 4. Update rule
        update_resp = client.patch(
            f"/plans/{plan_id}/rules/{rule_id}",
            json={"priority": 5, "enabled": False},
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["priority"] == 5
        assert updated["enabled"] is False
        assert updated["version"] == 2

        # 5. Delete rule
        del_resp = client.post(f"/plans/{plan_id}/rules/{rule_id}/delete")
        assert del_resp.status_code == 204
        assert client.get(f"/plans/{plan_id}/rules/{rule_id}").status_code == 404

    def test_rule_replay_and_conflict_quarantine_flow(
        self,
        client: TestClient,
        postgres_sessions: sessionmaker[Session],
    ):
        plan_id = create_test_plan(client)
        account_id = create_test_account(client, plan_id)

        # Create source and candidate
        plan_uuid = UUID(plan_id)
        source_uuid = uuid4()
        raw_msg_uuid = uuid4()
        now = datetime.now(timezone.utc)

        with postgres_sessions.begin() as session:
            source = WatcherSource(
                id=source_uuid,
                plan_id=plan_uuid,
                source_type="gmail",
                email_address="user@example.com",
                encrypted_refresh_token="token",
                status="active",
                creation_fingerprint=f"src:{source_uuid}",
            )
            session.add(source)
            session.flush()

            raw_msg = WatcherRawMessage(
                id=raw_msg_uuid,
                plan_id=plan_uuid,
                source_id=source_uuid,
                external_message_id="ext-bcp-1",
                internal_date=now,
                sender="notificaciones@bcp.com.bo",
                subject="Transferencia QR",
                raw_headers={},
                status="pending",
                creation_fingerprint=f"raw:{raw_msg_uuid}",
            )
            session.add(raw_msg)
            session.flush()

            candidate = WatcherCandidate(
                id=uuid4(),
                plan_id=plan_uuid,
                raw_message_id=raw_msg_uuid,
                source_id=source_uuid,
                candidate_type="bcp_qr",
                status="pending",
                event_at=now,
                notification_at=now,
                reported_amount=Decimal("120.00"),
                reported_currency="BOB",
                merchant="Farmacia",
                subject="Transferencia QR",
                sender="notificaciones@bcp.com.bo",
                message_id_header="<msg-qr-1@bcp.com.bo>",
                rule_evidence=[],
                glosa="BM BM QR PAGO DE PRODUCTOS",
                raw_glosa="BM BM QR PAGO DE PRODUCTOS",
                creation_fingerprint=f"cand:{raw_msg_uuid}",
            )
            session.add(candidate)
            session.flush()

        # Create two conflicting rules
        client.post(
            f"/plans/{plan_id}/rules",
            json={
                "name": "Rule 1: Set subtype A",
                "priority": 10,
                "predicate": {"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"},
                "action": {"qr_subtype": "subtype_A"},
            },
        )
        client.post(
            f"/plans/{plan_id}/rules",
            json={
                "name": "Rule 2: Set subtype B (conflict)",
                "priority": 20,
                "predicate": {"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"},
                "action": {"qr_subtype": "subtype_B"},
            },
        )

        # Replay rules
        replay_resp = client.post(f"/plans/{plan_id}/rules/replay")
        assert replay_resp.status_code == 200
        replay_data = replay_resp.json()
        assert replay_data["replayed_count"] == 1
        assert replay_data["quarantined_count"] == 1

        # Check candidate status
        cand_list = client.get(f"/plans/{plan_id}/watchers/candidates").json()
        assert len(cand_list) == 1
        cand_item = cand_list[0]
        assert cand_item["status"] == "quarantined"
        assert cand_item["quarantine_reason"] == "rule_conflict"
        assert any(e["result"] == "conflict" for e in cand_item["rule_evidence"])
