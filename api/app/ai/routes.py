from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.ai.schemas import (
    AIConfigResponse,
    AIConfigUpdate,
    AIModelOption,
    AISuggestionActionRequest,
    AISuggestionResponse,
)
from app.ai.service import (
    accept_ai_suggestion,
    generate_candidate_suggestion,
    generate_transaction_suggestion,
    get_ai_config,
    get_ai_suggestion,
    get_recommended_models,
    list_ai_suggestions,
    reject_ai_suggestion,
    update_ai_config,
)
from app.db import session_scope


router = APIRouter(tags=["ai"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


@router.get(
    "/plans/{plan_id}/ai/config",
    response_model=AIConfigResponse,
)
def read_ai_config(
    plan_id: UUID,
    request: Request,
    session: Session = Depends(get_database_session),
) -> AIConfigResponse:
    try:
        return get_ai_config(session, plan_id, request.app.state.settings)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.put(
    "/plans/{plan_id}/ai/config",
    response_model=AIConfigResponse,
)
def save_ai_config(
    plan_id: UUID,
    payload: AIConfigUpdate,
    request: Request,
    session: Session = Depends(get_database_session),
) -> AIConfigResponse:
    try:
        with session.begin():
            return update_ai_config(session, plan_id, payload, request.app.state.settings)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.get(
    "/plans/{plan_id}/ai/models",
    response_model=list[AIModelOption],
)
def read_ai_models(
    plan_id: UUID,
    provider: str | None = Query(None),
) -> list[AIModelOption]:
    return get_recommended_models(provider=provider)


@router.post(
    "/plans/{plan_id}/ai/suggest/candidate/{candidate_id}",
    response_model=AISuggestionResponse,
)
def post_suggest_candidate(
    plan_id: UUID,
    candidate_id: UUID,
    request: Request,
    session: Session = Depends(get_database_session),
) -> AISuggestionResponse:
    try:
        with session.begin():
            return generate_candidate_suggestion(
                session, plan_id, candidate_id, request.app.state.settings
            )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/ai/suggest/transaction/{transaction_id}",
    response_model=AISuggestionResponse,
)
def post_suggest_transaction(
    plan_id: UUID,
    transaction_id: UUID,
    request: Request,
    session: Session = Depends(get_database_session),
) -> AISuggestionResponse:
    try:
        with session.begin():
            return generate_transaction_suggestion(
                session, plan_id, transaction_id, request.app.state.settings
            )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.get(
    "/plans/{plan_id}/ai/suggestions",
    response_model=list[AISuggestionResponse],
)
def read_suggestions(
    plan_id: UUID,
    status: str | None = Query(None),
    candidate_id: UUID | None = Query(None),
    transaction_id: UUID | None = Query(None),
    session: Session = Depends(get_database_session),
) -> list[AISuggestionResponse]:
    try:
        return list_ai_suggestions(
            session,
            plan_id,
            status=status,
            candidate_id=candidate_id,
            transaction_id=transaction_id,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/ai/suggestions/{suggestion_id}",
    response_model=AISuggestionResponse,
)
def read_suggestion_detail(
    plan_id: UUID,
    suggestion_id: UUID,
    session: Session = Depends(get_database_session),
) -> AISuggestionResponse:
    try:
        return get_ai_suggestion(session, plan_id, suggestion_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/ai/suggestions/{suggestion_id}/accept",
    response_model=AISuggestionResponse,
)
def post_accept_suggestion(
    plan_id: UUID,
    suggestion_id: UUID,
    session: Session = Depends(get_database_session),
) -> AISuggestionResponse:
    try:
        with session.begin():
            return accept_ai_suggestion(session, plan_id, suggestion_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/ai/suggestions/{suggestion_id}/reject",
    response_model=AISuggestionResponse,
)
def post_reject_suggestion(
    plan_id: UUID,
    suggestion_id: UUID,
    payload: AISuggestionActionRequest | None = None,
    session: Session = Depends(get_database_session),
) -> AISuggestionResponse:
    try:
        with session.begin():
            reason = payload.reason if payload else None
            return reject_ai_suggestion(session, plan_id, suggestion_id, reason=reason)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc
