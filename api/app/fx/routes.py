from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.db import session_scope
from app.fx.schemas import (
    ConvertRequest,
    ConvertResponse,
    LatestQuoteResponse,
    ProviderStatus,
    QuoteCreate,
    QuoteResponse,
)
from app.fx.service import (
    InvalidFXConversion,
    NoQuoteAvailable,
    create_quote,
    convert_currency,
    format_quote_response,
    get_latest_quotes,
    list_providers,
    list_quotes,
)


router = APIRouter(tags=["fx"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
    )


@router.post(
    "/plans/{plan_id}/fx/quotes",
    response_model=QuoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plan_fx_quote(
    plan_id: UUID,
    payload: QuoteCreate,
    session: Session = Depends(get_database_session),
) -> QuoteResponse:
    try:
        with session.begin():
            quote = create_quote(session, plan_id, payload)
            return format_quote_response(quote)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.get(
    "/plans/{plan_id}/fx/quotes",
    response_model=list[QuoteResponse],
)
def list_plan_fx_quotes(
    plan_id: UUID,
    side: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_database_session),
) -> list[QuoteResponse]:
    try:
        return list_quotes(
            session, plan_id, side=side, source=source, limit=limit
        )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/fx/quotes/latest",
    response_model=LatestQuoteResponse,
)
def get_plan_latest_fx_quotes(
    plan_id: UUID,
    max_age_hours: int = Query(24, ge=1, le=720),
    session: Session = Depends(get_database_session),
) -> LatestQuoteResponse:
    try:
        return get_latest_quotes(session, plan_id, max_age_hours=max_age_hours)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/fx/convert",
    response_model=ConvertResponse,
)
def convert_plan_currency(
    plan_id: UUID,
    payload: ConvertRequest,
    session: Session = Depends(get_database_session),
) -> ConvertResponse:
    try:
        return convert_currency(session, plan_id, payload)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except (NoQuoteAvailable, InvalidFXConversion, ValueError) as exc:
        raise _unprocessable(exc) from exc


@router.get(
    "/plans/{plan_id}/fx/providers",
    response_model=list[ProviderStatus],
)
def list_plan_fx_providers(
    plan_id: UUID,
    session: Session = Depends(get_database_session),
) -> list[ProviderStatus]:
    # Plan validation if required
    return list_providers()
