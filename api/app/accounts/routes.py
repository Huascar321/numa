from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.accounts.models import Currency, Plan
from app.accounts.schemas import (
    AccountCreate,
    AccountResponse,
    AccountRename,
    CurrencyResponse,
    PlanCreate,
    PlanRename,
    PlanResponse,
)
from app.accounts.service import (
    CreationConflict,
    ResourceNotFound,
    UnknownCurrency,
    account_response,
    archive_account,
    create_account,
    create_plan,
    get_account,
    get_plan,
    list_accounts,
    list_currencies,
    list_plans,
    rename_account,
    rename_plan,
)
from app.db import session_scope


router = APIRouter(tags=["accounts"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: CreationConflict) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _unknown_currency(exc: UnknownCurrency) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


@router.get("/currencies", response_model=list[CurrencyResponse])
def read_currencies(
    session: Session = Depends(get_database_session),
) -> list[Currency]:
    return list_currencies(session)


@router.put(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_plan(
    plan_id: UUID,
    payload: PlanCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> object:
    try:
        with session.begin():
            result = create_plan(session, plan_id=plan_id, payload=payload)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except UnknownCurrency as exc:
        raise _unknown_currency(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.resource


@router.get("/plans", response_model=list[PlanResponse])
def read_plans(session: Session = Depends(get_database_session)) -> list[Plan]:
    return list_plans(session)


@router.get("/plans/{plan_id}", response_model=PlanResponse)
def read_plan(
    plan_id: UUID,
    session: Session = Depends(get_database_session),
) -> object:
    try:
        return get_plan(session, plan_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
def patch_plan(
    plan_id: UUID,
    payload: PlanRename,
    session: Session = Depends(get_database_session),
) -> object:
    try:
        with session.begin():
            return rename_plan(session, plan_id, payload.name)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.put(
    "/plans/{plan_id}/accounts/{account_id}",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_account(
    plan_id: UUID,
    account_id: UUID,
    payload: AccountCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> AccountResponse:
    try:
        with session.begin():
            result = create_account(
                session,
                plan_id=plan_id,
                account_id=account_id,
                payload=payload,
            )
            account = account_response(session, result.resource)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except UnknownCurrency as exc:
        raise _unknown_currency(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return account


@router.get(
    "/plans/{plan_id}/accounts",
    response_model=list[AccountResponse],
)
def read_accounts(
    plan_id: UUID,
    session: Session = Depends(get_database_session),
) -> list[AccountResponse]:
    try:
        accounts = list_accounts(session, plan_id)
        return [account_response(session, account) for account in accounts]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/accounts/{account_id}",
    response_model=AccountResponse,
)
def read_account(
    plan_id: UUID,
    account_id: UUID,
    session: Session = Depends(get_database_session),
) -> AccountResponse:
    try:
        return account_response(session, get_account(session, plan_id, account_id))
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except UnknownCurrency as exc:
        raise _unknown_currency(exc) from exc


@router.patch(
    "/plans/{plan_id}/accounts/{account_id}",
    response_model=AccountResponse,
)
def patch_account(
    plan_id: UUID,
    account_id: UUID,
    payload: AccountRename,
    session: Session = Depends(get_database_session),
) -> AccountResponse:
    try:
        with session.begin():
            account = rename_account(
                session,
                plan_id=plan_id,
                account_id=account_id,
                name=payload.name,
            )
            return account_response(session, account)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except UnknownCurrency as exc:
        raise _unknown_currency(exc) from exc


@router.post(
    "/plans/{plan_id}/accounts/{account_id}/archive",
    response_model=AccountResponse,
)
def post_archive_account(
    plan_id: UUID,
    account_id: UUID,
    session: Session = Depends(get_database_session),
) -> AccountResponse:
    try:
        with session.begin():
            account = archive_account(
                session,
                plan_id=plan_id,
                account_id=account_id,
            )
            return account_response(session, account)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except UnknownCurrency as exc:
        raise _unknown_currency(exc) from exc
