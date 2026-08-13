from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Generic, TypeVar, cast
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.accounts.models import Account, Currency, Plan
from app.ledger.models import Category, PostedAccountMovement
from app.accounts.schemas import (
    AccountCreate,
    AccountStatus,
    AccountResponse,
    AccountType,
    BalanceResponse,
    PlanCreate,
)


class UnknownCurrency(Exception):
    """The requested currency is not present in the internal registry."""


class CreationConflict(Exception):
    """A resource UUID is already bound to a different creation request."""


class ResourceNotFound(Exception):
    """The requested Plan-scoped resource does not exist."""


Resource = TypeVar("Resource")


@dataclass(frozen=True)
class CreationResult(Generic[Resource]):
    resource: Resource
    created: bool


def list_currencies(session: Session) -> list[Currency]:
    return list(session.scalars(select(Currency).order_by(Currency.code)))


def require_currency(session: Session, code: str) -> Currency:
    currency = session.get(Currency, code)
    if currency is None:
        raise UnknownCurrency(f"unknown currency: {code}")
    return currency


def _creation_fingerprint(payload: dict[str, object]) -> str:
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical_payload.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_plan(
    session: Session,
    *,
    plan_id: UUID,
    payload: PlanCreate,
) -> CreationResult[Plan]:
    persisted_timezone = payload.budget_timezone
    fingerprint = _creation_fingerprint(
        {
            "name": payload.name,
            "reporting_currency_code": payload.reporting_currency_code,
            "budget_timezone": persisted_timezone,
        }
    )
    existing = session.get(Plan, plan_id)
    if existing is not None:
        legacy_fingerprint = _creation_fingerprint(
            {
                "name": payload.name,
                "reporting_currency_code": payload.reporting_currency_code,
            }
        )
        if existing.creation_fingerprint not in {fingerprint, legacy_fingerprint}:
            raise CreationConflict("Plan UUID has a different creation payload")
        if existing.creation_fingerprint == legacy_fingerprint:
            # This is the unmodified 002_accounts identity. It must continue
            # to replay after 003 adds the immutable timezone column.
            if payload.budget_timezone is not None and existing.budget_timezone != payload.budget_timezone:
                raise CreationConflict(
                    "legacy Plan identity cannot change its persisted budget timezone"
                )
            return CreationResult(resource=existing, created=False)
        if payload.budget_timezone is None:
            raise CreationConflict("budget_timezone is required for this Plan identity")
        return CreationResult(resource=existing, created=False)

    if persisted_timezone is None:
        raise ValueError("budget_timezone is required when creating a Plan")
    require_currency(session, payload.reporting_currency_code)
    inserted_id = session.scalar(
        insert(Plan)
        .values(
            id=plan_id,
            name=payload.name,
            reporting_currency_code=payload.reporting_currency_code,
            budget_timezone=persisted_timezone,
            creation_fingerprint=fingerprint,
        )
        .on_conflict_do_nothing(index_elements=(Plan.id,))
        .returning(Plan.id)
    )
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise RuntimeError("created Plan could not be loaded")
    if plan.creation_fingerprint != fingerprint:
        raise CreationConflict("Plan UUID has a different creation payload")
    pending = session.scalar(
        select(Category).where(
            Category.plan_id == plan_id,
            Category.is_pending.is_(True),
        )
    )
    if pending is None:
        session.add(
            Category(
                id=uuid5(plan_id, "Pendientes"),
                plan_id=plan_id,
                name="Pendientes",
                is_pending=True,
                status="active",
                creation_fingerprint=_creation_fingerprint(
                    {"plan_id": str(plan_id), "name": "Pendientes", "system": True}
                ),
            )
        )
        session.flush()
    return CreationResult(resource=plan, created=inserted_id is not None)


def list_plans(session: Session) -> list[Plan]:
    return list(session.scalars(select(Plan).order_by(Plan.created_at, Plan.id)))


def get_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound("Plan not found")
    return plan


def rename_plan(session: Session, plan_id: UUID, name: str) -> Plan:
    plan = get_plan(session, plan_id)
    plan.name = name
    plan.updated_at = _utc_now()
    session.flush()
    return plan


def _account_creation_fingerprint(
    *,
    plan_id: UUID,
    payload: AccountCreate,
) -> str:
    return _creation_fingerprint(
        {
            "plan_id": str(plan_id),
            "name": payload.name,
            "account_type": payload.account_type,
            "currency_code": payload.currency_code,
        }
    )


def create_account(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
    payload: AccountCreate,
) -> CreationResult[Account]:
    fingerprint = _account_creation_fingerprint(plan_id=plan_id, payload=payload)
    existing = session.get(Account, account_id)
    if existing is not None:
        if existing.creation_fingerprint != fingerprint:
            raise CreationConflict("Account UUID has a different creation payload")
        return CreationResult(resource=existing, created=False)

    get_plan(session, plan_id)
    require_currency(session, payload.currency_code)
    inserted_id = session.scalar(
        insert(Account)
        .values(
            id=account_id,
            plan_id=plan_id,
            name=payload.name,
            account_type=payload.account_type,
            currency_code=payload.currency_code,
            creation_fingerprint=fingerprint,
        )
        .on_conflict_do_nothing(index_elements=(Account.id,))
        .returning(Account.id)
    )
    account = session.scalar(
        select(Account).where(
            Account.plan_id == plan_id,
            Account.id == account_id,
        )
    )
    if account is None:
        existing = session.get(Account, account_id)
        if existing is not None:
            raise CreationConflict("Account UUID has a different creation payload")
        raise RuntimeError("created Account could not be loaded")
    if account.creation_fingerprint != fingerprint:
        raise CreationConflict("Account UUID has a different creation payload")
    return CreationResult(resource=account, created=inserted_id is not None)


def list_accounts(session: Session, plan_id: UUID) -> list[Account]:
    get_plan(session, plan_id)
    return list(
        session.scalars(
            select(Account)
            .where(Account.plan_id == plan_id)
            .order_by(Account.created_at, Account.id)
        )
    )


def get_account(session: Session, plan_id: UUID, account_id: UUID) -> Account:
    account = session.scalar(
        select(Account).where(
            Account.plan_id == plan_id,
            Account.id == account_id,
        )
    )
    if account is None:
        raise ResourceNotFound("Account not found")
    return account


def rename_account(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
    name: str,
) -> Account:
    account = get_account(session, plan_id, account_id)
    if account.status != "active":
        raise CreationConflict("Archived Accounts cannot be renamed")
    account.name = name
    account.updated_at = _utc_now()
    session.flush()
    return account


def archive_account(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
) -> Account:
    account = get_account(session, plan_id, account_id)
    if account.status == "active":
        account.status = "archived"
        account.updated_at = _utc_now()
        session.flush()
    return account


def account_balance(session: Session, account: Account) -> BalanceResponse:
    currency = require_currency(session, account.currency_code)
    scale = Decimal(1).scaleb(-currency.decimal_places)
    amount = session.scalar(
        select(func.coalesce(func.sum(PostedAccountMovement.signed_amount), 0)).where(
            PostedAccountMovement.plan_id == account.plan_id,
            PostedAccountMovement.account_id == account.id,
            PostedAccountMovement.currency_code == account.currency_code,
        )
    ) or Decimal(0)
    amount = Decimal(amount).quantize(scale)
    return BalanceResponse(
        amount=format(amount, "f"),
        currency=currency.code,
    )


def account_response(session: Session, account: Account) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        plan_id=account.plan_id,
        name=account.name,
        account_type=cast(AccountType, account.account_type),
        currency_code=account.currency_code,
        status=cast(AccountStatus, account.status),
        balance=account_balance(session, account),
        created_at=account.created_at,
        updated_at=account.updated_at,
    )
