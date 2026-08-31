from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Account, Plan
from app.accounts.schemas import AccountCreate, PlanCreate
from app.accounts.service import create_account, create_plan
from app.automation.detector import detect_automation_suggestions
from app.automation.models import AutomationRuleSuggestion
from app.automation.schemas import AutomationSuggestionAcceptRequest
from app.automation.service import (
    accept_suggestion,
    dismiss_suggestion,
    discover_suggestions,
    get_suggestion,
    list_suggestions,
    reject_suggestion,
)
from app.ledger.models import Category, PostedAccountMovement, Transaction
from app.ledger.schemas import CategoryCreate, TransactionCreate
from app.ledger.service import create_category, create_transaction, fingerprint, utc_now
from app.main import create_app
from app.rules.models import Rule
from app.rules.schemas import RuleCreate
from app.rules.service import create_rule
from app.settings import Settings
from app.watchers.models import WatcherCandidate, WatcherRawMessage, WatcherSource


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_automation_db(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE automation_rule_suggestions, rules, watcher_candidates, "
        "watcher_account_mappings, watcher_raw_messages, watcher_sources, "
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


def _create_test_plan(
    session: Session, name: str = "Automation Test Plan"
) -> tuple[Plan, Account, Category, Category]:
    plan_id = uuid4()
    plan = create_plan(
        session,
        plan_id=plan_id,
        payload=PlanCreate(
            name=name,
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
        ),
    ).resource

    account_id = uuid4()
    account = create_account(
        session,
        plan_id=plan_id,
        account_id=account_id,
        payload=AccountCreate(
            name="Bank Checking",
            account_type="Bank",
            currency_code="BOB",
        ),
    ).resource

    cat_pharmacy = create_category(
        session,
        plan_id=plan_id,
        category_id=uuid4(),
        payload=CategoryCreate(name="Pharmacy"),
    ).resource

    cat_groceries = create_category(
        session,
        plan_id=plan_id,
        category_id=uuid4(),
        payload=CategoryCreate(name="Groceries"),
    ).resource

    return plan, account, cat_pharmacy, cat_groceries


def _create_watcher_candidate(
    session: Session,
    plan_id: UUID,
    candidate_type: str = "bcp_qr",
    reported_amount: Decimal = Decimal("100.00"),
    reported_currency: str = "BOB",
    glosa: str | None = None,
    raw_glosa: str | None = None,
) -> WatcherCandidate:
    source = WatcherSource(
        id=uuid4(),
        plan_id=plan_id,
        source_type="gmail",
        email_address=f"user_{uuid4().hex[:8]}@example.com",
        encrypted_refresh_token="v1:fake_token",
        creation_fingerprint=fingerprint({"plan_id": str(plan_id), "type": "source"}),
    )
    session.add(source)
    session.flush()

    raw_msg = WatcherRawMessage(
        id=uuid4(),
        plan_id=plan_id,
        source_id=source.id,
        external_message_id=f"msg_{uuid4().hex}",
        internal_date=utc_now(),
        sender="notificaciones@bcp.com.bo",
        subject="Aviso de Transferencia QR",
        snippet="Aviso QR",
        creation_fingerprint=fingerprint({"plan_id": str(plan_id), "type": "raw_msg"}),
    )
    session.add(raw_msg)
    session.flush()

    cand = WatcherCandidate(
        id=uuid4(),
        plan_id=plan_id,
        source_id=source.id,
        raw_message_id=raw_msg.id,
        candidate_type=candidate_type,
        status="pending",
        reported_amount=reported_amount,
        reported_currency=reported_currency,
        event_at=utc_now(),
        subject="Aviso de Transferencia QR",
        sender="notificaciones@bcp.com.bo",
        glosa=glosa,
        raw_glosa=raw_glosa,
        raw_payload={},
        provenance={"source": "test"},
        creation_fingerprint=fingerprint({"plan_id": str(plan_id), "type": "cand"}),
    )
    session.add(cand)
    session.flush()
    return cand


def _create_tx(
    session: Session,
    plan_id: UUID,
    account_id: UUID,
    category_id: UUID,
    merchant: str,
    amount: str = "25.00",
) -> Transaction:
    tx = create_transaction(
        session=session,
        plan_id=plan_id,
        transaction_id=uuid4(),
        payload=TransactionCreate(
            type="expense",
            account_id=account_id,
            amount=amount,
            currency_code="BOB",
            event_at=utc_now(),
            category_id=category_id,
            merchant=merchant,
            memo="Test memo",
            tags=[],
        ),
    ).resource
    return tx


class TestPatternDetector:
    def test_recurring_merchant_category_detection(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            # Create 3 transactions for "Farmacorp" mapped to Pharmacy
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "10.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "20.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "30.00")

            detected = detect_automation_suggestions(session, plan.id)
            assert len(detected) == 1
            s = detected[0]
            assert s["suggestion_type"] == "merchant_category"
            assert s["predicate"] == {"merchant": "Farmacorp"}
            assert s["action"] == {"category_id": str(cat_pharmacy.id)}
            assert s["confidence"] >= Decimal("0.90")
            assert s["evidence"]["occurrence_count"] == 3

    def test_informative_qr_glosa_detection(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, _, _, _ = _create_test_plan(session)
            # Create BCP QR candidate with informative glosa
            _create_watcher_candidate(
                session,
                plan_id=plan.id,
                candidate_type="bcp_qr",
                raw_glosa="BM BM QR PAGO DE PRODUCTOS",
            )

            detected = detect_automation_suggestions(session, plan.id)
            assert len(detected) == 1
            s = detected[0]
            assert s["suggestion_type"] == "qr_glosa_subtype"
            assert s["predicate"] == {"raw_glosa": "BM BM QR PAGO DE PRODUCTOS"}
            assert s["action"] == {"qr_subtype": "product_payment"}
            assert s["confidence"] == Decimal("0.95")

    def test_no_suggestions_on_missing_or_default_interbancaria_glosa(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, _, _, _ = _create_test_plan(session)
            # Candidate 1: Missing glosa
            _create_watcher_candidate(
                session,
                plan_id=plan.id,
                candidate_type="bcp_qr",
                raw_glosa=None,
                glosa=None,
            )
            # Candidate 2: Common default INTERBANCARIA glosa
            _create_watcher_candidate(
                session,
                plan_id=plan.id,
                candidate_type="bcp_qr",
                raw_glosa="BM BM QR INTERBANCARIA",
                glosa="BM BM QR INTERBANCARIA",
            )

            detected = detect_automation_suggestions(session, plan.id)
            assert len(detected) == 0

    def test_existing_active_rule_prevents_duplicate_suggestion(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "15.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "25.00")

            # Create existing active rule for Farmacorp
            create_rule(
                session=session,
                plan_id=plan.id,
                payload=RuleCreate(
                    name="Existing Farmacorp Rule",
                    stage="watcher_candidate",
                    priority=100,
                    enabled=True,
                    predicate={"merchant": "Farmacorp"},
                    action={"category_id": str(cat_pharmacy.id)},
                ),
            )

            detected = detect_automation_suggestions(session, plan.id)
            assert len(detected) == 0


class TestAutomationService:
    def test_discover_is_idempotent(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Hipermaxi", "50.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Hipermaxi", "70.00")

            disc_count_1, created_count_1, suggestions_1 = discover_suggestions(
                session, plan.id
            )
            assert disc_count_1 == 1
            assert created_count_1 == 1
            assert len(suggestions_1) == 1

            # Discover again without new data
            disc_count_2, created_count_2, suggestions_2 = discover_suggestions(
                session, plan.id
            )
            assert disc_count_2 == 1
            assert created_count_2 == 0
            assert len(suggestions_2) == 1

    def test_accept_creates_active_rule_and_preserves_provenance(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "10.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "20.00")

            _, _, suggestions = discover_suggestions(session, plan.id)
            sugg_id = suggestions[0].id

            # Initial rule count
            rules_before = session.scalars(
                select(Rule).where(Rule.plan_id == plan.id)
            ).all()
            assert len(rules_before) == 0

            sugg, created_rule = accept_suggestion(session, plan.id, sugg_id)

            assert sugg.status == "accepted"
            assert sugg.created_rule_id == created_rule.id
            assert sugg.decided_at is not None

            # Verify the created rule
            assert created_rule.plan_id == plan.id
            assert created_rule.enabled is True
            assert created_rule.predicate == {"merchant": "Farmacorp"}
            assert created_rule.action == {"category_id": str(cat_pharmacy.id)}

    def test_reject_and_dismiss_workflow(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "StoreA", "10.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "StoreA", "20.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "StoreB", "30.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "StoreB", "40.00")

            _, _, suggestions = discover_suggestions(session, plan.id)
            assert len(suggestions) == 2

            sugg_a = next(s for s in suggestions if "StoreA" in s.title)
            sugg_b = next(s for s in suggestions if "StoreB" in s.title)

            # Reject StoreA with reason
            rejected = reject_suggestion(
                session, plan.id, sugg_a.id, reason="Incorrect category mapping"
            )
            assert rejected.status == "rejected"
            assert rejected.evidence.get("rejection_reason") == "Incorrect category mapping"
            assert rejected.decided_at is not None

            # Dismiss StoreB
            dismissed = dismiss_suggestion(session, plan.id, sugg_b.id)
            assert dismissed.status == "dismissed"
            assert dismissed.decided_at is not None

    def test_zero_money_mutation_invariant(
        self, postgres_sessions: sessionmaker[Session]
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "10.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Farmacorp", "20.00")

            tx_count_before = len(
                session.scalars(select(Transaction).where(Transaction.plan_id == plan.id)).all()
            )
            mov_count_before = len(
                session.scalars(
                    select(PostedAccountMovement).where(
                        PostedAccountMovement.plan_id == plan.id
                    )
                ).all()
            )

            # Discover
            _, _, suggestions = discover_suggestions(session, plan.id)
            # Accept
            accept_suggestion(session, plan.id, suggestions[0].id)

            tx_count_after = len(
                session.scalars(select(Transaction).where(Transaction.plan_id == plan.id)).all()
            )
            mov_count_after = len(
                session.scalars(
                    select(PostedAccountMovement).where(
                        PostedAccountMovement.plan_id == plan.id
                    )
                ).all()
            )

            # Money and ledger movements MUST NOT be altered
            assert tx_count_before == tx_count_after
            assert mov_count_before == mov_count_after


class TestAutomationApi:
    def test_api_discovery_and_lifecycle(
        self,
        client: TestClient,
        postgres_sessions: sessionmaker[Session],
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Fidalga", "100.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "Fidalga", "200.00")
            plan_id = str(plan.id)

        # 1. Discover suggestions via API
        resp = client.post(f"/plans/{plan_id}/automation/suggestions/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["discovered_count"] == 1
        assert data["created_count"] == 1
        assert len(data["suggestions"]) == 1
        suggestion_id = data["suggestions"][0]["id"]

        # 2. List suggestions
        resp = client.get(f"/plans/{plan_id}/automation/suggestions")
        assert resp.status_code == 200
        list_data = resp.json()
        assert len(list_data) == 1
        assert list_data[0]["id"] == suggestion_id
        assert list_data[0]["status"] == "suggested"

        # 3. Get single suggestion
        resp = client.get(f"/plans/{plan_id}/automation/suggestions/{suggestion_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == suggestion_id

        # 4. Accept suggestion
        resp = client.post(
            f"/plans/{plan_id}/automation/suggestions/{suggestion_id}/accept",
            json={"name": "Custom Fidalga Rule Name"},
        )
        assert resp.status_code == 200
        accepted_data = resp.json()
        assert accepted_data["status"] == "accepted"
        assert accepted_data["created_rule_id"] is not None

        # Verify rule was created and visible in rules API
        rule_resp = client.get(f"/plans/{plan_id}/rules")
        assert rule_resp.status_code == 200
        rules = rule_resp.json()
        assert len(rules) == 1
        assert rules[0]["id"] == accepted_data["created_rule_id"]
        assert rules[0]["name"] == "Custom Fidalga Rule Name"

    def test_api_reject_and_dismiss(
        self,
        client: TestClient,
        postgres_sessions: sessionmaker[Session],
    ) -> None:
        with postgres_sessions.begin() as session:
            plan, account, cat_pharmacy, _ = _create_test_plan(session)
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "StoreX", "10.00")
            _create_tx(session, plan.id, account.id, cat_pharmacy.id, "StoreX", "20.00")
            _create_watcher_candidate(
                session,
                plan_id=plan.id,
                candidate_type="bcp_qr",
                raw_glosa="BM BM QR PAGO DE PRODUCTOS",
            )
            plan_id = str(plan.id)

        # Discover
        disc_resp = client.post(f"/plans/{plan_id}/automation/suggestions/discover")
        assert disc_resp.status_code == 200
        suggestions = disc_resp.json()["suggestions"]
        assert len(suggestions) == 2

        sugg_1_id = suggestions[0]["id"]
        sugg_2_id = suggestions[1]["id"]

        # Reject first
        rej_resp = client.post(
            f"/plans/{plan_id}/automation/suggestions/{sugg_1_id}/reject",
            json={"reason": "User rejected"},
        )
        assert rej_resp.status_code == 200
        assert rej_resp.json()["status"] == "rejected"

        # Dismiss second
        dism_resp = client.post(
            f"/plans/{plan_id}/automation/suggestions/{sugg_2_id}/dismiss"
        )
        assert dism_resp.status_code == 200
        assert dism_resp.json()["status"] == "dismissed"
