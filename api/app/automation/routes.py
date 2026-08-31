from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.automation.schemas import (
    AutomationSuggestionAcceptRequest,
    AutomationSuggestionRejectRequest,
    AutomationSuggestionResponse,
    DiscoverAutomationSuggestionsResponse,
)
from app.automation.service import (
    accept_suggestion,
    dismiss_suggestion,
    discover_suggestions,
    get_suggestion,
    list_suggestions,
    reject_suggestion,
)
from app.db import session_scope


router = APIRouter(tags=["automation"])


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
    "/plans/{plan_id}/automation/suggestions/discover",
    response_model=DiscoverAutomationSuggestionsResponse,
)
def discover_plan_automation_suggestions(
    plan_id: UUID,
    session: Session = Depends(get_database_session),
) -> DiscoverAutomationSuggestionsResponse:
    try:
        discovered_count, created_count, suggestions = discover_suggestions(
            session, plan_id
        )
        session.commit()
        return DiscoverAutomationSuggestionsResponse(
            discovered_count=discovered_count,
            created_count=created_count,
            suggestions=[
                AutomationSuggestionResponse.model_validate(s) for s in suggestions
            ],
        )
    except ResourceNotFound as exc:
        session.rollback()
        raise _not_found(exc)
    except Exception as exc:
        session.rollback()
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/automation/suggestions",
    response_model=list[AutomationSuggestionResponse],
)
def list_plan_automation_suggestions(
    plan_id: UUID,
    status: str | None = Query(None),
    source: str | None = Query(None),
    session: Session = Depends(get_database_session),
) -> list[AutomationSuggestionResponse]:
    try:
        suggestions = list_suggestions(
            session, plan_id, status=status, source=source
        )
        return [
            AutomationSuggestionResponse.model_validate(s) for s in suggestions
        ]
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except Exception as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/automation/suggestions/{suggestion_id}",
    response_model=AutomationSuggestionResponse,
)
def get_plan_automation_suggestion(
    plan_id: UUID,
    suggestion_id: UUID,
    session: Session = Depends(get_database_session),
) -> AutomationSuggestionResponse:
    try:
        suggestion = get_suggestion(session, plan_id, suggestion_id)
        return AutomationSuggestionResponse.model_validate(suggestion)
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except Exception as exc:
        raise _unprocessable(str(exc))


@router.post(
    "/plans/{plan_id}/automation/suggestions/{suggestion_id}/accept",
    response_model=AutomationSuggestionResponse,
)
def accept_plan_automation_suggestion(
    plan_id: UUID,
    suggestion_id: UUID,
    payload: AutomationSuggestionAcceptRequest | None = None,
    session: Session = Depends(get_database_session),
) -> AutomationSuggestionResponse:
    try:
        suggestion, _ = accept_suggestion(
            session, plan_id, suggestion_id, payload=payload
        )
        session.commit()
        return AutomationSuggestionResponse.model_validate(suggestion)
    except ResourceNotFound as exc:
        session.rollback()
        raise _not_found(exc)
    except Exception as exc:
        session.rollback()
        raise _unprocessable(str(exc))


@router.post(
    "/plans/{plan_id}/automation/suggestions/{suggestion_id}/reject",
    response_model=AutomationSuggestionResponse,
)
def reject_plan_automation_suggestion(
    plan_id: UUID,
    suggestion_id: UUID,
    payload: AutomationSuggestionRejectRequest | None = None,
    session: Session = Depends(get_database_session),
) -> AutomationSuggestionResponse:
    try:
        reason = payload.reason if payload else None
        suggestion = reject_suggestion(session, plan_id, suggestion_id, reason=reason)
        session.commit()
        return AutomationSuggestionResponse.model_validate(suggestion)
    except ResourceNotFound as exc:
        session.rollback()
        raise _not_found(exc)
    except Exception as exc:
        session.rollback()
        raise _unprocessable(str(exc))


@router.post(
    "/plans/{plan_id}/automation/suggestions/{suggestion_id}/dismiss",
    response_model=AutomationSuggestionResponse,
)
def dismiss_plan_automation_suggestion(
    plan_id: UUID,
    suggestion_id: UUID,
    session: Session = Depends(get_database_session),
) -> AutomationSuggestionResponse:
    try:
        suggestion = dismiss_suggestion(session, plan_id, suggestion_id)
        session.commit()
        return AutomationSuggestionResponse.model_validate(suggestion)
    except ResourceNotFound as exc:
        session.rollback()
        raise _not_found(exc)
    except Exception as exc:
        session.rollback()
        raise _unprocessable(str(exc))
