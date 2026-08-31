from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Account, Plan
from app.accounts.schemas import AccountCreate, PlanCreate
from app.accounts.service import create_account, create_plan
from app.ai.client import AIClient, AIProviderError, AIProviderUnavailableError
from app.ai.models import AIConfiguration, AISuggestion
from app.ai.schemas import AIConfigUpdate, StructuredLLMSuggestion
from app.ai.service import (
    accept_ai_suggestion,
    generate_candidate_suggestion,
    generate_transaction_suggestion,
    get_ai_config,
    get_ai_suggestion,
    list_ai_suggestions,
    reject_ai_suggestion,
    update_ai_config,
)
from app.ledger.models import Category, Tag, Transaction
from app.ledger.schemas import CategoryCreate, TagCreate, TransactionCreate
from app.ledger.service import create_category, create_tag, create_transaction, fingerprint, utc_now
from app.main import create_app
from app.settings import Settings
from app.watchers.crypto import decrypt_token, get_encryption_key
from app.watchers.models import WatcherCandidate, WatcherRawMessage, WatcherSource


pytestmark = pytest.mark.postgres


def _create_test_plan(session: Session, name: str = "AI Test Plan") -> tuple[Plan, Account, Category]:
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

    category = create_category(
        session,
        plan_id=plan_id,
        category_id=uuid4(),
        payload=CategoryCreate(name="Groceries"),
    ).resource

    return plan, account, category


def _create_watcher_source_and_candidate(
    session: Session,
    plan_id: UUID,
    candidate_type: str = "bcp_qr",
    reported_amount: Decimal = Decimal("50.00"),
    reported_currency: str = "BOB",
    merchant: str | None = None,
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
        internal_date=datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc),
        sender="notifications@bcp.com.bo",
        subject="Notice",
        snippet="Test notice",
        creation_fingerprint=fingerprint({"plan_id": str(plan_id), "type": "raw_msg"}),
    )
    session.add(raw_msg)
    session.flush()

    candidate = WatcherCandidate(
        id=uuid4(),
        plan_id=plan_id,
        raw_message_id=raw_msg.id,
        source_id=source.id,
        candidate_type=candidate_type,
        status="pending",
        event_at=datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc),
        notification_at=datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc),
        reported_amount=reported_amount,
        reported_currency=reported_currency,
        merchant=merchant,
        subject="Notice",
        sender="notifications@bcp.com.bo",
        glosa=glosa,
        raw_glosa=raw_glosa,
        direction="debit",
        rule_evidence=[],
        raw_payload={},
        provenance={},
        creation_fingerprint=fingerprint({"plan_id": str(plan_id), "type": "candidate"}),
    )
    session.add(candidate)
    session.flush()
    return candidate


def test_ai_configuration_encryption_and_masking(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )
    client = TestClient(create_app(settings))

    with postgres_sessions() as session:
        plan, _, _ = _create_test_plan(session, "AI Config Plan")
        session.commit()

    # 1. Read default AI config
    res = client.get(f"/plans/{plan.id}/ai/config")
    assert res.status_code == 200
    data = res.json()
    assert data["is_enabled"] is False
    assert data["provider"] == "openrouter"
    assert data["has_api_key"] is False
    assert data["masked_api_key"] is None

    # 2. Update config with plaintext API key
    raw_secret_key = "sk-or-v1-secret-test-key-12345"
    update_res = client.put(
        f"/plans/{plan.id}/ai/config",
        json={
            "provider": "openrouter",
            "model": "openai/gpt-4o-mini",
            "api_key": raw_secret_key,
            "is_enabled": True,
        },
    )
    assert update_res.status_code == 200
    update_data = update_res.json()
    assert update_data["is_enabled"] is True
    assert update_data["has_api_key"] is True
    assert update_data["masked_api_key"] == "••••••••"
    # Plaintext key MUST NEVER be present in response
    assert raw_secret_key not in str(update_data)

    # 3. Verify server-side authenticated encryption in database
    with postgres_sessions() as session:
        db_config = session.scalar(
            select(AIConfiguration).where(AIConfiguration.plan_id == plan.id)
        )
        assert db_config is not None
        assert db_config.encrypted_api_key is not None
        assert db_config.encrypted_api_key.startswith("v1:")
        assert raw_secret_key not in db_config.encrypted_api_key

        # Decrypt with crypto utility to verify authenticity
        decrypted = decrypt_token(
            db_config.encrypted_api_key,
            get_encryption_key(settings),
        )
        assert decrypted == raw_secret_key

    # 4. Clear API key
    clear_res = client.put(
        f"/plans/{plan.id}/ai/config",
        json={"clear_api_key": True},
    )
    assert clear_res.status_code == 200
    assert clear_res.json()["has_api_key"] is False
    assert clear_res.json()["masked_api_key"] is None


def test_ai_recommended_models_endpoint(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    settings = Settings(database_url=migrated_postgres_url)
    client = TestClient(create_app(settings))

    with postgres_sessions() as session:
        plan, _, _ = _create_test_plan(session, "Models Plan")
        session.commit()

    res_all = client.get(f"/plans/{plan.id}/ai/models")
    assert res_all.status_code == 200
    models_all = res_all.json()
    assert any(m["provider"] == "openrouter" for m in models_all)
    assert any(m["provider"] == "groq" for m in models_all)
    assert any(m["id"] == "gpt-oss-120b" for m in models_all)
    assert any(m["id"] == "gpt-oss-20b" for m in models_all)

    res_groq = client.get(f"/plans/{plan.id}/ai/models?provider=groq")
    assert res_groq.status_code == 200
    models_groq = res_groq.json()
    assert all(m["provider"] == "groq" for m in models_groq)
    assert any(m["id"] == "llama-3.3-70b-versatile" for m in models_groq)


def test_ai_suggestion_for_candidate_with_valid_output(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )
    client = TestClient(create_app(settings))

    with postgres_sessions() as session:
        plan, _, category = _create_test_plan(session, "Candidate Suggestion Plan")
        # Enable AI
        update_ai_config(
            session,
            plan.id,
            AIConfigUpdate(
                provider="openrouter",
                model="openai/gpt-4o-mini",
                api_key="test-api-key",
                is_enabled=True,
            ),
            settings,
        )
        candidate = _create_watcher_source_and_candidate(
            session,
            plan.id,
            candidate_type="binance_card",
            reported_amount=Decimal("15.50"),
            merchant="SUPERMERCADO HIPERMAXI",
            glosa="COMPRA HIPERMAXI LA PAZ",
        )
        session.commit()

    mock_client = MagicMock(spec=AIClient)
    mock_client.generate_structured_completion.return_value = {
        "category_id": str(category.id),
        "merchant": "Hipermaxi",
        "glosa": "COMPRA HIPERMAXI LA PAZ",
        "tags": ["groceries", "supermarket"],
        "confidence": 0.95,
        "reasoning": "Purchase was made at Hipermaxi supermarket, matching Groceries category.",
    }

    with postgres_sessions() as session:
        suggestion_resp = generate_candidate_suggestion(
            session, plan.id, candidate.id, settings, ai_client=mock_client
        )
        session.commit()

        assert suggestion_resp.status == "suggested"
        assert suggestion_resp.suggested_category_id == category.id
        assert suggestion_resp.suggested_merchant == "Hipermaxi"
        assert suggestion_resp.confidence == Decimal("0.9500")
        assert "Hipermaxi supermarket" in (suggestion_resp.reasoning or "")
        assert suggestion_resp.validation_errors is None


def test_ai_suggestion_invalid_output_quarantined(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )

    with postgres_sessions() as session:
        plan, _, _ = _create_test_plan(session, "Quarantine Suggestion Plan")
        update_ai_config(
            session,
            plan.id,
            AIConfigUpdate(
                provider="openrouter",
                model="openai/gpt-4o-mini",
                api_key="test-api-key",
                is_enabled=True,
            ),
            settings,
        )
        candidate = _create_watcher_source_and_candidate(
            session,
            plan.id,
            candidate_type="binance_card",
            reported_amount=Decimal("20.00"),
        )
        session.commit()

    # Mock client returning schema-invalid output (e.g. confidence > 1.0 which fails pydantic ge/le)
    mock_client = MagicMock(spec=AIClient)
    mock_client.generate_structured_completion.return_value = {
        "category_id": "not-a-valid-category",
        "confidence": 99.0,  # Invalid: confidence must be <= 1.0
    }

    with postgres_sessions() as session:
        suggestion_resp = generate_candidate_suggestion(
            session, plan.id, candidate.id, settings, ai_client=mock_client
        )
        session.commit()

        assert suggestion_resp.status == "quarantined"
        assert suggestion_resp.validation_errors is not None
        assert "Pydantic validation error" in str(suggestion_resp.validation_errors)


def test_bcp_qr_glosa_boundary_default_or_missing(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    """For BCP QR, missing glosa or 'BM BM QR INTERBANCARIA' MUST NOT invent glosa or suggest a category."""
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )

    with postgres_sessions() as session:
        plan, _, category = _create_test_plan(session, "BCP QR Boundary Plan")
        update_ai_config(
            session,
            plan.id,
            AIConfigUpdate(
                provider="openrouter",
                model="openai/gpt-4o-mini",
                api_key="test-api-key",
                is_enabled=True,
            ),
            settings,
        )
        # Case A: Default glosa "BM BM QR INTERBANCARIA"
        candidate_default = _create_watcher_source_and_candidate(
            session,
            plan.id,
            candidate_type="bcp_qr",
            reported_amount=Decimal("100.00"),
            raw_glosa="BM BM QR INTERBANCARIA",
        )
        # Case B: Missing / empty glosa
        candidate_empty = _create_watcher_source_and_candidate(
            session,
            plan.id,
            candidate_type="bcp_qr",
            reported_amount=Decimal("200.00"),
            raw_glosa="",
            glosa=None,
        )
        session.commit()

    mock_client = MagicMock(spec=AIClient)

    with postgres_sessions() as session:
        # Case A evaluation
        resp_a = generate_candidate_suggestion(
            session, plan.id, candidate_default.id, settings, ai_client=mock_client
        )
        assert resp_a.suggested_category_id is None
        assert resp_a.confidence == Decimal("0.0")
        assert "BM BM QR INTERBANCARIA" in (resp_a.reasoning or "")
        # LLM client should NOT even be called because glosa boundary was caught deterministically
        mock_client.generate_structured_completion.assert_not_called()

        # Case B evaluation
        resp_b = generate_candidate_suggestion(
            session, plan.id, candidate_empty.id, settings, ai_client=mock_client
        )
        assert resp_b.suggested_category_id is None
        assert resp_b.confidence == Decimal("0.0")
        mock_client.generate_structured_completion.assert_not_called()


def test_bcp_qr_glosa_boundary_informative(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    """For BCP QR with informative glosa ('BM BM QR PAGO DE PRODUCTOS'), AI may suggest an active category."""
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )

    with postgres_sessions() as session:
        plan, _, category = _create_test_plan(session, "BCP QR Informative Plan")
        update_ai_config(
            session,
            plan.id,
            AIConfigUpdate(
                provider="openrouter",
                model="openai/gpt-4o-mini",
                api_key="test-api-key",
                is_enabled=True,
            ),
            settings,
        )
        candidate = _create_watcher_source_and_candidate(
            session,
            plan.id,
            candidate_type="bcp_qr",
            reported_amount=Decimal("85.00"),
            raw_glosa="BM BM QR PAGO DE PRODUCTOS",
            glosa="BM BM QR PAGO DE PRODUCTOS",
        )
        session.commit()

    mock_client = MagicMock(spec=AIClient)
    mock_client.generate_structured_completion.return_value = {
        "category_id": str(category.id),
        "merchant": "Pago de Productos",
        "glosa": "BM BM QR PAGO DE PRODUCTOS",
        "tags": ["qr_payment"],
        "confidence": 0.88,
        "reasoning": "Informative glosa indicates product purchase, matching Groceries.",
    }

    with postgres_sessions() as session:
        resp = generate_candidate_suggestion(
            session, plan.id, candidate.id, settings, ai_client=mock_client
        )
        session.commit()

        mock_client.generate_structured_completion.assert_called_once()
        assert resp.status == "suggested"
        assert resp.suggested_category_id == category.id
        assert resp.suggested_glosa == "BM BM QR PAGO DE PRODUCTOS"


def test_ai_disabled_or_provider_outage_fallback(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )
    client = TestClient(create_app(settings))

    with postgres_sessions() as session:
        plan, _, _ = _create_test_plan(session, "Outage Fallback Plan")
        candidate = _create_watcher_source_and_candidate(
            session, plan.id, candidate_type="binance_card", merchant="Test Merchant"
        )
        session.commit()

    # 1. AI is disabled by default -> calling suggest endpoint returns 422
    res_disabled = client.post(f"/plans/{plan.id}/ai/suggest/candidate/{candidate.id}")
    assert res_disabled.status_code == 422
    assert "disabled or unconfigured" in res_disabled.json()["detail"]

    # 2. Enable AI, but provider has network outage
    with postgres_sessions() as session:
        update_ai_config(
            session,
            plan.id,
            AIConfigUpdate(
                provider="openrouter",
                model="openai/gpt-4o-mini",
                api_key="test-api-key",
                is_enabled=True,
            ),
            settings,
        )
        session.commit()

    mock_client = MagicMock(spec=AIClient)
    mock_client.generate_structured_completion.side_effect = AIProviderUnavailableError(
        "Provider connection timed out"
    )

    with postgres_sessions() as session:
        with pytest.raises(ValueError, match="AI Provider error"):
            generate_candidate_suggestion(
                session, plan.id, candidate.id, settings, ai_client=mock_client
            )


def test_accept_and_reject_ai_suggestion_invariants(
    postgres_sessions: sessionmaker[Session],
    migrated_postgres_url: str,
) -> None:
    settings = Settings(
        database_url=migrated_postgres_url,
        token_encryption_key="test-encryption-key-32byteslong!!",
    )
    client = TestClient(create_app(settings))

    with postgres_sessions() as session:
        plan, account, category = _create_test_plan(session, "Accept Reject Plan")
        txn = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=uuid4(),
            payload=TransactionCreate(
                type="expense",
                account_id=account.id,
                amount="45.00",
                currency_code="BOB",
                event_at=datetime(2026, 8, 14, 10, 0, 0, tzinfo=timezone.utc),
                category_id=None,
                merchant=None,
                memo="Store purchase",
            ),
        ).resource
        # Create suggestion manually
        sug = AISuggestion(
            id=uuid4(),
            plan_id=plan.id,
            candidate_id=None,
            transaction_id=txn.id,
            suggestion_type="categorization",
            status="suggested",
            suggested_category_id=category.id,
            suggested_merchant="Organic Grocer",
            suggested_glosa=None,
            suggested_tags=["organic"],
            confidence=Decimal("0.9000"),
            reasoning="Matched based on memo.",
            provenance={},
            creation_fingerprint=fingerprint({"plan_id": str(plan.id), "txn": str(txn.id)}),
        )
        session.add(sug)
        session.commit()
        suggestion_id = sug.id
        txn_id = txn.id

    # 1. Accept suggestion via endpoint
    accept_res = client.post(f"/plans/{plan.id}/ai/suggestions/{suggestion_id}/accept")
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == "accepted"

    # 2. Verify non-financial mutation: category and merchant updated, amount/account/currency/event_at unchanged
    with postgres_sessions() as session:
        updated_txn = session.get(Transaction, txn_id)
        assert updated_txn is not None
        assert updated_txn.category_id == category.id
        assert updated_txn.merchant == "Organic Grocer"
        assert updated_txn.amount == Decimal("45.00")
        assert updated_txn.currency_code == "BOB"
        assert updated_txn.account_id == account.id
        assert updated_txn.event_at == datetime(2026, 8, 14, 10, 0, 0, tzinfo=timezone.utc)

    # 3. Test Reject suggestion
    with postgres_sessions() as session:
        sug_reject = AISuggestion(
            id=uuid4(),
            plan_id=plan.id,
            candidate_id=None,
            transaction_id=txn_id,
            suggestion_type="categorization",
            status="suggested",
            suggested_category_id=None,
            suggested_merchant=None,
            confidence=Decimal("0.5000"),
            reasoning="Uncertain match.",
            provenance={},
            creation_fingerprint=fingerprint({"plan_id": str(plan.id), "reject": True}),
        )
        session.add(sug_reject)
        session.commit()
        reject_id = sug_reject.id

    reject_res = client.post(
        f"/plans/{plan.id}/ai/suggestions/{reject_id}/reject",
        json={"reason": "Incorrect category"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"
