from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.db import session_scope
from app.matching.schemas import (
    MatchAcceptRequest,
    MatchEvaluationRequest,
    MatchEvaluationResponse,
    MatchRejectRequest,
    MatchUnlinkRequest,
    TransactionMatchResponse,
)
from app.matching.service import (
    accept_match,
    evaluate_plan_matches,
    get_match,
    list_matches,
    reject_match,
    unlink_match,
)


router = APIRouter(tags=["matching"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


@router.post(
    "/plans/{plan_id}/matching/evaluate",
    response_model=MatchEvaluationResponse,
)
def post_evaluate_matches(
    plan_id: UUID,
    payload: MatchEvaluationRequest | None = None,
    session: Session = Depends(get_database_session),
) -> MatchEvaluationResponse:
    try:
        with session.begin():
            return evaluate_plan_matches(session, plan_id, payload=payload)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.get(
    "/plans/{plan_id}/matching/matches",
    response_model=list[TransactionMatchResponse],
)
def read_matches(
    plan_id: UUID,
    status: str | None = Query(None),
    classification: str | None = Query(None),
    session: Session = Depends(get_database_session),
) -> list[TransactionMatchResponse]:
    try:
        return list_matches(
            session, plan_id, status=status, classification=classification
        )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/matching/matches/{match_id}",
    response_model=TransactionMatchResponse,
)
def read_match_detail(
    plan_id: UUID,
    match_id: UUID,
    session: Session = Depends(get_database_session),
) -> TransactionMatchResponse:
    try:
        return get_match(session, plan_id, match_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/matching/matches/{match_id}/accept",
    response_model=TransactionMatchResponse,
)
def post_accept_match(
    plan_id: UUID,
    match_id: UUID,
    payload: MatchAcceptRequest | None = None,
    session: Session = Depends(get_database_session),
) -> TransactionMatchResponse:
    try:
        with session.begin():
            return accept_match(session, plan_id, match_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/matching/matches/{match_id}/reject",
    response_model=TransactionMatchResponse,
)
def post_reject_match(
    plan_id: UUID,
    match_id: UUID,
    payload: MatchRejectRequest | None = None,
    session: Session = Depends(get_database_session),
) -> TransactionMatchResponse:
    try:
        with session.begin():
            reason = payload.reason if payload else None
            return reject_match(session, plan_id, match_id, reason=reason)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/matching/matches/{match_id}/unlink",
    response_model=TransactionMatchResponse,
)
def post_unlink_match(
    plan_id: UUID,
    match_id: UUID,
    payload: MatchUnlinkRequest | None = None,
    session: Session = Depends(get_database_session),
) -> TransactionMatchResponse:
    try:
        with session.begin():
            reason = payload.reason if payload else None
            return unlink_match(session, plan_id, match_id, reason=reason)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc
