from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from uuid import uuid4

from app.accounts import Account, Currency, Plan
from app.accounts.schemas import PlanCreate
from app.accounts.service import (
    CreationConflict,
    ResourceNotFound,
    UnknownCurrency,
    create_plan,
    get_plan,
    list_currencies,
    list_plans,
    rename_plan,
    require_currency,
)


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


def test_currency_service_reads_seeded_scale_metadata(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions() as session:
        currencies = list_currencies(session)
        bob = require_currency(session, "BOB")
        usdt = require_currency(session, "USDT")

    assert [(currency.code, currency.decimal_places) for currency in currencies] == [
        ("BOB", 2),
        ("USDT", 6),
    ]
    assert bob.decimal_places == 2
    assert usdt.decimal_places == 6


def test_currency_service_rejects_unknown_currency_without_creating_it(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as session:
        with pytest.raises(UnknownCurrency, match="unknown currency"):
            require_currency(session, "USD")

    with postgres_sessions() as session:
        assert session.get(Currency, "USD") is None


def test_plan_create_replay_after_rename_returns_current_plan(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan_id = uuid4()
    original_payload = PlanCreate(
        name="Original Plan",
        reporting_currency_code="BOB",
    )
    with postgres_sessions.begin() as session:
        first = create_plan(session, plan_id=plan_id, payload=original_payload)
        assert first.created is True

    with postgres_sessions.begin() as session:
        renamed = rename_plan(session, plan_id, "Renamed Plan")
        original_fingerprint = renamed.creation_fingerprint

    with postgres_sessions.begin() as session:
        replay = create_plan(session, plan_id=plan_id, payload=original_payload)
        assert replay.created is False
        assert replay.resource.name == "Renamed Plan"
        assert replay.resource.creation_fingerprint == original_fingerprint

    with postgres_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Plan)) == 1
        assert [(plan.id, plan.name) for plan in list_plans(session)] == [
            (plan_id, "Renamed Plan")
        ]
        assert get_plan(session, plan_id).reporting_currency_code == "BOB"


def test_plan_conflicting_replay_leaves_original_unchanged(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan_id = uuid4()
    with postgres_sessions.begin() as session:
        created = create_plan(
            session,
            plan_id=plan_id,
            payload=PlanCreate(name="Original", reporting_currency_code="BOB"),
        ).resource
        original_state = (
            created.name,
            created.reporting_currency_code,
            created.creation_fingerprint,
            created.updated_at,
        )

    with pytest.raises(CreationConflict):
        with postgres_sessions.begin() as session:
            create_plan(
                session,
                plan_id=plan_id,
                payload=PlanCreate(name="Different", reporting_currency_code="USDT"),
            )

    with postgres_sessions() as session:
        unchanged = get_plan(session, plan_id)
        assert (
            unchanged.name,
            unchanged.reporting_currency_code,
            unchanged.creation_fingerprint,
            unchanged.updated_at,
        ) == original_state
        assert session.scalar(select(func.count()).select_from(Plan)) == 1


def test_plan_service_rejects_unknown_currency_and_unknown_plan(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan_id = uuid4()
    with pytest.raises(UnknownCurrency):
        with postgres_sessions.begin() as session:
            create_plan(
                session,
                plan_id=plan_id,
                payload=PlanCreate(name="Plan", reporting_currency_code="USD"),
            )

    with postgres_sessions() as session:
        assert session.get(Plan, plan_id) is None
        with pytest.raises(ResourceNotFound):
            get_plan(session, plan_id)
