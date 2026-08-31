from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.accounts.schemas import BalanceResponse
from app.accounts.service import CreationConflict, ResourceNotFound
from app.db import session_scope
from app.ledger.service import LedgerValidationError
from app.reconciliation.models import ReconciliationSession
from app.reconciliation.schemas import (
    ReconciliationComparisonResponse,
    ReconciliationConfirmRequest,
    ReconciliationPreviewRequest,
    ReconciliationSessionResponse,
)
from app.reconciliation.service import (
    Comparison,
    Policy,
    ReconciliationPolicyError,
    adjustment_ids,
    confirm_reconciliation,
    format_at_scale,
    list_reconciliations,
    preview_reconciliation,
)


router = APIRouter(tags=["reconciliation"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _money(amount: Decimal, comparison: Comparison) -> BalanceResponse:
    return BalanceResponse(
        amount=format_at_scale(amount, comparison.currency),
        currency=comparison.currency.code,
    )


def _comparison_response(comparison: Comparison) -> ReconciliationComparisonResponse:
    return ReconciliationComparisonResponse(
        id=comparison.id,
        plan_id=comparison.plan_id,
        account_id=comparison.account_id,
        statement_balance=_money(comparison.statement_balance, comparison),
        statement_at=comparison.statement_at,
        derived_balance=_money(comparison.derived_balance, comparison),
        discrepancy=_money(comparison.discrepancy, comparison),
        policy=comparison.policy,
        tolerance=_money(comparison.tolerance, comparison),
        requires_warning_acceptance=comparison.requires_warning_acceptance,
        blocked=comparison.blocked,
    )


def _session_response(
    session: Session, reconciliation: ReconciliationSession
) -> ReconciliationSessionResponse:
    from app.accounts.service import require_currency

    currency = require_currency(session, reconciliation.currency_code)
    comparison = Comparison(
        id=reconciliation.id,
        plan_id=reconciliation.plan_id,
        account_id=reconciliation.account_id,
        currency=currency,
        statement_balance=Decimal(reconciliation.statement_balance),
        statement_at=reconciliation.statement_at,
        derived_balance=Decimal(reconciliation.derived_balance),
        discrepancy=Decimal(reconciliation.discrepancy),
        policy=cast(Policy, reconciliation.policy),
        tolerance=Decimal(reconciliation.tolerance),
    )
    transaction_id, movement_id = adjustment_ids(session, reconciliation)
    return ReconciliationSessionResponse(
        **_comparison_response(comparison).model_dump(),
        warning_accepted=reconciliation.warning_accepted,
        confirmed_at=reconciliation.confirmed_at,
        adjustment_transaction_id=transaction_id,
        adjustment_movement_id=movement_id,
    )


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _invalid(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
    )


@router.post(
    "/plans/{plan_id}/accounts/{account_id}/reconciliations/{reconciliation_id}/preview",
    response_model=ReconciliationComparisonResponse,
)
def post_reconciliation_preview(
    plan_id: UUID,
    account_id: UUID,
    reconciliation_id: UUID,
    payload: ReconciliationPreviewRequest,
    request: Request,
    session: Session = Depends(get_database_session),
) -> ReconciliationComparisonResponse:
    settings = request.app.state.settings
    try:
        return _comparison_response(
            preview_reconciliation(
                session,
                plan_id=plan_id,
                account_id=account_id,
                reconciliation_id=reconciliation_id,
                payload=payload,
                policy=settings.reconciliation_policy,
                tolerance_atoms=settings.reconciliation_tolerance_atoms,
            )
        )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc


@router.put(
    "/plans/{plan_id}/accounts/{account_id}/reconciliations/{reconciliation_id}",
    response_model=ReconciliationSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_reconciliation(
    plan_id: UUID,
    account_id: UUID,
    reconciliation_id: UUID,
    payload: ReconciliationConfirmRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_database_session),
) -> ReconciliationSessionResponse:
    settings = request.app.state.settings
    try:
        with session.begin():
            result = confirm_reconciliation(
                session,
                plan_id=plan_id,
                account_id=account_id,
                reconciliation_id=reconciliation_id,
                payload=payload,
                policy=settings.reconciliation_policy,
                tolerance_atoms=settings.reconciliation_tolerance_atoms,
            )
            body = _session_response(session, result.resource)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except (CreationConflict, ReconciliationPolicyError) as exc:
        raise _conflict(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return body


@router.get(
    "/plans/{plan_id}/accounts/{account_id}/reconciliations",
    response_model=list[ReconciliationSessionResponse],
)
def get_reconciliation_history(
    plan_id: UUID,
    account_id: UUID,
    session: Session = Depends(get_database_session),
) -> list[ReconciliationSessionResponse]:
    try:
        return [
            _session_response(session, item)
            for item in list_reconciliations(
                session, plan_id=plan_id, account_id=account_id
            )
        ]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
