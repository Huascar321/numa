from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts import Account, Plan
from app.ledger import (
    Category,
    CategoryGroup,
    MonthlyBudgetAssignment,
    PostedAccountMovement,
    Tag,
    Transaction,
    TransactionCorrection,
    TransactionTag,
)
from app.accounts.schemas import AccountCreate
from app.accounts.service import (
    CreationConflict,
    ResourceNotFound,
    account_balance,
    account_response,
    archive_account,
    create_account,
    create_plan,
    get_account,
    list_accounts,
    rename_account,
)
from app.accounts.schemas import PlanCreate


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_accounts(postgres_sessions: sessionmaker[Session]):
    with postgres_sessions.begin() as session:
        session.execute(text(
            "TRUNCATE transaction_tags, posted_account_movements, "
            "transaction_corrections, monthly_budget_assignments, transactions, "
            "tags, categories, category_groups, accounts, plans CASCADE"
        ))
    yield
    with postgres_sessions.begin() as session:
        session.execute(text(
            "TRUNCATE transaction_tags, posted_account_movements, "
            "transaction_corrections, monthly_budget_assignments, transactions, "
            "tags, categories, category_groups, accounts, plans CASCADE"
        ))


def _create_plan(
    postgres_sessions: sessionmaker[Session],
    *,
    plan_id=None,
) -> Plan:
    with postgres_sessions.begin() as session:
        return create_plan(
            session,
            plan_id=plan_id or uuid4(),
            payload=PlanCreate(
                name="Plan",
                reporting_currency_code="BOB",
                budget_timezone="America/La_Paz",
            ),
        ).resource


@pytest.mark.parametrize(
    ("account_type", "currency_code", "expected_amount"),
    [
        ("Bank", "BOB", "0.00"),
        ("Cash", "BOB", "0.00"),
        ("Wallet", "BOB", "0.00"),
        ("Credit Card", "BOB", "0.00"),
        ("Crypto", "USDT", "0.000000"),
        ("Other", "USDT", "0.000000"),
    ],
)
def test_create_account_accepts_all_six_types_and_exact_zero_balance(
    postgres_sessions: sessionmaker[Session],
    account_type: str,
    currency_code: str,
    expected_amount: str,
) -> None:
    plan = _create_plan(postgres_sessions)
    account_id = uuid4()
    with postgres_sessions.begin() as session:
        result = create_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
            payload=AccountCreate.model_validate(
                {
                    "name": f"{account_type} account",
                    "account_type": account_type,
                    "currency_code": currency_code,
                }
            ),
        )
        response = account_response(session, result.resource)

    assert result.created is True
    assert response.status == "active"
    assert response.account_type == account_type
    assert response.currency_code == currency_code
    assert response.balance.amount == expected_amount
    assert response.balance.currency == currency_code
    assert isinstance(Decimal(response.balance.amount), Decimal)


def test_account_replay_after_rename_returns_current_account_and_conflict_is_safe(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan = _create_plan(postgres_sessions)
    account_id = uuid4()
    payload = AccountCreate(
        name="Original account",
        account_type="Bank",
        currency_code="BOB",
    )
    with postgres_sessions.begin() as session:
        first = create_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
            payload=payload,
        )

    with postgres_sessions.begin() as session:
        renamed = rename_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
            name="Renamed account",
        )
        original_state = (
            renamed.name,
            renamed.account_type,
            renamed.currency_code,
            renamed.status,
            renamed.creation_fingerprint,
        )

    with postgres_sessions.begin() as session:
        replay = create_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
            payload=payload,
        )
        assert replay.created is False
        assert replay.resource.name == "Renamed account"

    with pytest.raises(CreationConflict):
        with postgres_sessions.begin() as session:
            create_account(
                session,
                plan_id=plan.id,
                account_id=account_id,
                payload=AccountCreate(
                    name="Different",
                    account_type="Cash",
                    currency_code="USDT",
                ),
            )

    with postgres_sessions() as session:
        unchanged = get_account(session, plan.id, account_id)
        assert (
            unchanged.name,
            unchanged.account_type,
            unchanged.currency_code,
            unchanged.status,
            unchanged.creation_fingerprint,
        ) == original_state
        assert session.scalar(select(func.count()).select_from(Account)) == 1


def test_account_archive_is_one_way_non_destructive_and_repeat_is_idempotent(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan = _create_plan(postgres_sessions)
    account_id = uuid4()
    with postgres_sessions.begin() as session:
        create_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
            payload=AccountCreate(
                name="Archive me",
                account_type="Cash",
                currency_code="BOB",
            ),
        )

    with postgres_sessions.begin() as session:
        archived = archive_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
        )
        archived_state = (
            archived.id,
            archived.name,
            archived.account_type,
            archived.currency_code,
            archived.status,
            archived.updated_at,
        )

    with postgres_sessions.begin() as session:
        repeated = archive_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
        )
        assert (
            repeated.id,
            repeated.name,
            repeated.account_type,
            repeated.currency_code,
            repeated.status,
            repeated.updated_at,
        ) == archived_state

    with pytest.raises(CreationConflict, match="cannot be renamed"):
        with postgres_sessions.begin() as session:
            rename_account(
                session,
                plan_id=plan.id,
                account_id=account_id,
                name="Must fail",
            )

    with postgres_sessions() as session:
        assert len(list_accounts(session, plan.id)) == 1
        readable = get_account(session, plan.id, account_id)
        assert readable.status == "archived"


def test_account_identity_is_not_mutable_through_service(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan = _create_plan(postgres_sessions)
    other_plan = _create_plan(postgres_sessions)
    account_id = uuid4()
    payload = AccountCreate(name="Immutable", account_type="Wallet", currency_code="BOB")
    with postgres_sessions.begin() as session:
        create_account(
            session,
            plan_id=plan.id,
            account_id=account_id,
            payload=payload,
        )

    with pytest.raises(ResourceNotFound):
        with postgres_sessions.begin() as session:
            rename_account(
                session,
                plan_id=other_plan.id,
                account_id=account_id,
                name="Cross-plan rename",
            )
    with pytest.raises(ResourceNotFound):
        with postgres_sessions.begin() as session:
            archive_account(
                session,
                plan_id=other_plan.id,
                account_id=account_id,
            )

    with postgres_sessions.begin() as session:
        with pytest.raises(CreationConflict):
            create_account(
                session,
                plan_id=other_plan.id,
                account_id=account_id,
                payload=payload,
            )

    with postgres_sessions() as session:
        unchanged = get_account(session, plan.id, account_id)
        assert unchanged.plan_id == plan.id
        assert unchanged.account_type == "Wallet"
        assert unchanged.currency_code == "BOB"
        assert unchanged.status == "active"


def test_balance_projection_never_accepts_float_or_stores_an_accumulator(
    postgres_sessions: sessionmaker[Session],
) -> None:
    plan = _create_plan(postgres_sessions)
    with postgres_sessions.begin() as session:
        account = create_account(
            session,
            plan_id=plan.id,
            account_id=uuid4(),
            payload=AccountCreate(
                name="Exact balance",
                account_type="Other",
                currency_code="USDT",
            ),
        ).resource
        balance = account_balance(session, account)
        response = account_response(session, account)

    assert balance.amount == "0.000000"
    assert response.balance.amount == "0.000000"
    assert not isinstance(response.balance.amount, float)
    assert not {"balance", "opening_balance"} & set(Account.__table__.columns.keys())
