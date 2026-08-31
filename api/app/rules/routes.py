from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.db import session_scope
from app.rules.schemas import (
    ReplayRulesResponse,
    RuleCreate,
    RuleResponse,
    RuleUpdate,
)
from app.rules.service import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    replay_plan_rules,
    update_rule,
)


router = APIRouter(tags=["rules"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


class ReplayRulesRequest(BaseModel):
    candidate_ids: list[UUID] | None = None


@router.get(
    "/plans/{plan_id}/rules",
    response_model=list[RuleResponse],
)
def read_rules(
    plan_id: UUID,
    stage: str | None = Query(None),
    enabled: bool | None = Query(None),
    session: Session = Depends(get_database_session),
) -> list[RuleResponse]:
    try:
        rules = list_rules(session, plan_id, stage=stage, enabled=enabled)
        return [RuleResponse.model_validate(r) for r in rules]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_create_rule(
    plan_id: UUID,
    payload: RuleCreate,
    session: Session = Depends(get_database_session),
) -> RuleResponse:
    try:
        with session.begin():
            rule = create_rule(session, plan_id, payload)
            return RuleResponse.model_validate(rule)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.get(
    "/plans/{plan_id}/rules/{rule_id}",
    response_model=RuleResponse,
)
def read_rule(
    plan_id: UUID,
    rule_id: UUID,
    session: Session = Depends(get_database_session),
) -> RuleResponse:
    try:
        rule = get_rule(session, plan_id, rule_id)
        return RuleResponse.model_validate(rule)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch(
    "/plans/{plan_id}/rules/{rule_id}",
    response_model=RuleResponse,
)
def patch_update_rule(
    plan_id: UUID,
    rule_id: UUID,
    payload: RuleUpdate,
    session: Session = Depends(get_database_session),
) -> RuleResponse:
    try:
        with session.begin():
            rule = update_rule(session, plan_id, rule_id, payload)
            return RuleResponse.model_validate(rule)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/rules/{rule_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
)
def post_delete_rule_endpoint(
    plan_id: UUID,
    rule_id: UUID,
    session: Session = Depends(get_database_session),
) -> None:
    try:
        with session.begin():
            delete_rule(session, plan_id, rule_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/rules/replay",
    response_model=ReplayRulesResponse,
)
def post_replay_rules(
    plan_id: UUID,
    payload: ReplayRulesRequest | None = None,
    session: Session = Depends(get_database_session),
) -> ReplayRulesResponse:
    try:
        with session.begin():
            candidate_ids = payload.candidate_ids if payload else None
            return replay_plan_rules(session, plan_id, candidate_ids=candidate_ids)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
