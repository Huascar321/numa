from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.schemas import PlanCreate
from app.accounts.service import create_plan
from app.fx.models import ExchangeRateQuote
from app.fx.providers import BCBOfficialProvider, BinanceP2POptionalAdapter, ManualQuoteProvider
from app.fx.schemas import ConvertRequest, QuoteCreate
from app.fx.service import (
    NoQuoteAvailable,
    convert_currency,
    create_quote,
    get_latest_quotes,
    list_providers,
    list_quotes,
)
from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_fx_db(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE exchange_rate_quotes, automation_rule_suggestions, rules, "
        "watcher_candidates, watcher_account_mappings, watcher_raw_messages, "
        "watcher_sources, reconciliation_sessions, transfer_legs, transfers, "
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


def _create_test_plan(session: Session, name: str = "FX Test Plan") -> UUID:
    plan_id = uuid4()
    create_plan(
        session,
        plan_id=plan_id,
        payload=PlanCreate(
            name=name,
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
        ),
    )
    return plan_id


def test_manual_buy_usdt_quote_formula(postgres_sessions: sessionmaker[Session]):
    """BUY_USDT formula: rate = BOB paid / USDT received, with 8 decimal precision."""
    with postgres_sessions() as session:
        with session.begin():
            plan_id = _create_test_plan(session)
            payload = QuoteCreate(
                side="BUY_USDT",
                bob_amount=Decimal("75.50"),
                usdt_amount=Decimal("10.00"),
                payment_method="QR Interbancario",
                source="manual",
            )
            quote = create_quote(session, plan_id, payload)

        assert quote.rate == Decimal("7.55000000")
        assert quote.bob_amount == Decimal("75.5000")
        assert quote.usdt_amount == Decimal("10.000000")
        assert quote.side == "BUY_USDT"
        assert quote.source == "manual"
        assert quote.payment_method == "QR Interbancario"


def test_manual_sell_usdt_quote_formula(postgres_sessions: sessionmaker[Session]):
    """SELL_USDT formula: rate = BOB received / USDT sold, with 8 decimal precision."""
    with postgres_sessions() as session:
        with session.begin():
            plan_id = _create_test_plan(session)
            payload = QuoteCreate(
                side="SELL_USDT",
                bob_amount=Decimal("74.50"),
                usdt_amount=Decimal("10.00"),
                payment_method="Bank Transfer",
                source="manual",
            )
            quote = create_quote(session, plan_id, payload)

        assert quote.rate == Decimal("7.45000000")
        assert quote.bob_amount == Decimal("74.5000")
        assert quote.usdt_amount == Decimal("10.000000")
        assert quote.side == "SELL_USDT"
        assert quote.source == "manual"


def test_no_assumed_6_96_bcb_rate(postgres_sessions: sessionmaker[Session]):
    """Official 6.96 rate is NEVER assumed as primary or default fallback."""
    with postgres_sessions() as session:
        with session.begin():
            plan_id = _create_test_plan(session)

        # Attempt to convert BOB -> USDT without quotes
        with pytest.raises(NoQuoteAvailable) as exc_info:
            convert_currency(
                session,
                plan_id,
                ConvertRequest(
                    from_currency="BOB",
                    to_currency="USDT",
                    amount=Decimal("100.00"),
                ),
            )
        assert "No exchange rate quote available" in str(exc_info.value)
        assert "6.96" in str(exc_info.value)

        # Attempt to convert USDT -> BOB without quotes
        with pytest.raises(NoQuoteAvailable) as exc_info_sell:
            convert_currency(
                session,
                plan_id,
                ConvertRequest(
                    from_currency="USDT",
                    to_currency="BOB",
                    amount=Decimal("10.00"),
                ),
            )
        assert "No exchange rate quote available" in str(exc_info_sell.value)


def test_staleness_detection(postgres_sessions: sessionmaker[Session]):
    """Quotes older than 24h are marked stale; recent quotes are fresh."""
    with postgres_sessions() as session:
        with session.begin():
            plan_id = _create_test_plan(session)
            now = datetime.now(timezone.utc)
            stale_time = now - timedelta(hours=25)

            # Create stale quote
            stale_quote = create_quote(
                session,
                plan_id,
                QuoteCreate(
                    side="BUY_USDT",
                    bob_amount=Decimal("75.00"),
                    usdt_amount=Decimal("10.00"),
                    observed_at=stale_time,
                ),
            )

        latest = get_latest_quotes(session, plan_id, max_age_hours=24)
        assert latest.has_quote is True
        assert latest.has_fresh_quote is False
        assert latest.is_stale is True
        assert latest.buy_quote is not None
        assert latest.buy_quote.is_stale is True
        assert latest.buy_quote.freshness == "stale"

    with postgres_sessions() as session:
        # Now add a fresh quote
        with session.begin():
            fresh_quote = create_quote(
                session,
                plan_id,
                QuoteCreate(
                    side="BUY_USDT",
                    bob_amount=Decimal("76.00"),
                    usdt_amount=Decimal("10.00"),
                    observed_at=now,
                ),
            )

        latest_after = get_latest_quotes(session, plan_id, max_age_hours=24)
        assert latest_after.has_quote is True
        assert latest_after.has_fresh_quote is True
        assert latest_after.is_stale is False
        assert latest_after.buy_quote is not None
        assert latest_after.buy_quote.rate == Decimal("7.60000000")
        assert latest_after.buy_quote.is_stale is False
        assert latest_after.buy_quote.freshness == "fresh"


def test_explicit_conversion_calculation(postgres_sessions: sessionmaker[Session]):
    """Explicit multi-currency conversion with rate provenance."""
    with postgres_sessions() as session:
        with session.begin():
            plan_id = _create_test_plan(session)
            create_quote(
                session,
                plan_id,
                QuoteCreate(
                    side="BUY_USDT",
                    bob_amount=Decimal("75.50"),
                    usdt_amount=Decimal("10.00"),
                ),
            )
            create_quote(
                session,
                plan_id,
                QuoteCreate(
                    side="SELL_USDT",
                    bob_amount=Decimal("74.50"),
                    usdt_amount=Decimal("10.00"),
                ),
            )

        # BOB -> USDT (100 BOB / 7.55 = 13.245033 USDT)
        conv_usdt = convert_currency(
            session,
            plan_id,
            ConvertRequest(
                from_currency="BOB",
                to_currency="USDT",
                amount=Decimal("100.00"),
            ),
        )
        assert conv_usdt.from_amount == Decimal("100.00")
        assert conv_usdt.to_amount == Decimal("13.245033")
        assert conv_usdt.rate_used == Decimal("7.55000000")
        assert conv_usdt.rate_source == "latest_buy_quote"
        assert conv_usdt.formula == "USDT = BOB / rate (rate = BOB paid / USDT received)"
        assert conv_usdt.provenance["side"] == "BUY_USDT"

        # USDT -> BOB (10 USDT * 7.45 = 74.50 BOB)
        conv_bob = convert_currency(
            session,
            plan_id,
            ConvertRequest(
                from_currency="USDT",
                to_currency="BOB",
                amount=Decimal("10.00"),
            ),
        )
        assert conv_bob.from_amount == Decimal("10.00")
        assert conv_bob.to_amount == Decimal("74.50")
        assert conv_bob.rate_used == Decimal("7.45000000")
        assert conv_bob.rate_source == "latest_sell_quote"
        assert conv_bob.formula == "BOB = USDT * rate (rate = BOB received / USDT sold)"
        assert conv_bob.provenance["side"] == "SELL_USDT"

        # Custom rate override
        conv_custom = convert_currency(
            session,
            plan_id,
            ConvertRequest(
                from_currency="BOB",
                to_currency="USDT",
                amount=Decimal("100.00"),
                custom_rate=Decimal("8.00"),
            ),
        )
        assert conv_custom.to_amount == Decimal("12.500000")
        assert conv_custom.rate_used == Decimal("8.00")
        assert conv_custom.rate_source == "custom_rate"


def test_provider_statuses_and_adapters():
    """Manual is available/primary, BCB is reference_only, Binance P2P is unverified_optional."""
    providers = list_providers()
    provider_map = {p.id: p for p in providers}

    assert "manual" in provider_map
    assert provider_map["manual"].status == "available"
    assert provider_map["manual"].is_primary is True

    assert "bcb_official" in provider_map
    assert provider_map["bcb_official"].status == "reference_only"
    assert provider_map["bcb_official"].is_primary is False
    assert "6.96" in provider_map["bcb_official"].description

    assert "binance_p2p" in provider_map
    assert provider_map["binance_p2p"].status == "unverified_optional"
    assert provider_map["binance_p2p"].is_primary is False


def test_fx_rest_api_endpoints(
    client: TestClient, postgres_sessions: sessionmaker[Session]
):
    """End-to-end REST API verification for FX endpoints."""
    with postgres_sessions() as session:
        with session.begin():
            plan_id = _create_test_plan(session)

    # 1. List providers
    resp = client.get(f"/plans/{plan_id}/fx/providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) == 3
    assert any(p["id"] == "manual" and p["is_primary"] is True for p in providers)
    assert any(p["id"] == "bcb_official" and p["status"] == "reference_only" for p in providers)

    # 2. Get latest quotes before creating any
    resp = client.get(f"/plans/{plan_id}/fx/quotes/latest")
    assert resp.status_code == 200
    assert resp.json()["has_quote"] is False

    # 3. Create BUY_USDT quote
    quote_payload = {
        "side": "BUY_USDT",
        "bob_amount": "75.50",
        "usdt_amount": "10.00",
        "payment_method": "QR Interbancario",
        "source": "manual",
    }
    resp = client.post(f"/plans/{plan_id}/fx/quotes", json=quote_payload)
    assert resp.status_code == 201
    quote_data = resp.json()
    assert quote_data["rate"] == "7.55000000"
    assert quote_data["side"] == "BUY_USDT"
    quote_id = quote_data["id"]

    # 4. Create SELL_USDT quote
    sell_payload = {
        "side": "SELL_USDT",
        "bob_amount": "74.50",
        "usdt_amount": "10.00",
        "payment_method": "Bank Transfer",
        "source": "manual",
    }
    resp = client.post(f"/plans/{plan_id}/fx/quotes", json=sell_payload)
    assert resp.status_code == 201
    assert resp.json()["rate"] == "7.45000000"

    # 5. List quotes
    resp = client.get(f"/plans/{plan_id}/fx/quotes")
    assert resp.status_code == 200
    quotes_list = resp.json()
    assert len(quotes_list) == 2

    # 6. Get latest quotes
    resp = client.get(f"/plans/{plan_id}/fx/quotes/latest")
    assert resp.status_code == 200
    latest_data = resp.json()
    assert latest_data["has_quote"] is True
    assert latest_data["has_fresh_quote"] is True
    assert latest_data["buy_quote"]["rate"] == "7.55000000"
    assert latest_data["sell_quote"]["rate"] == "7.45000000"

    # 7. Convert BOB -> USDT
    resp = client.post(
        f"/plans/{plan_id}/fx/convert",
        json={
            "from_currency": "BOB",
            "to_currency": "USDT",
            "amount": "151.00",
        },
    )
    assert resp.status_code == 200
    conv_data = resp.json()
    assert conv_data["to_amount"] == "20.000000"
    assert conv_data["rate_used"] == "7.55000000"

    # 8. Convert USDT -> BOB
    resp = client.post(
        f"/plans/{plan_id}/fx/convert",
        json={
            "from_currency": "USDT",
            "to_currency": "BOB",
            "amount": "20.00",
        },
    )
    assert resp.status_code == 200
    conv_data_sell = resp.json()
    assert conv_data_sell["to_amount"] == "149.00"
    assert conv_data_sell["rate_used"] == "7.45000000"

    # 9. 404 for unknown plan
    fake_plan = uuid4()
    resp = client.get(f"/plans/{fake_plan}/fx/quotes")
    assert resp.status_code == 404
