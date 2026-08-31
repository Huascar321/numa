from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.db import session_scope
from app.watchers.gmail_client import GmailApiError, GmailNotConfiguredError
from app.watchers.schemas import (
    ConnectGmailRequest,
    CreateAccountMappingRequest,
    GmailAuthUrlResponse,
    IgnoreCandidateRequest,
    ProcessCandidatesResponse,
    ResolveCandidateRequest,
    SyncResultResponse,
    WatcherAccountMappingResponse,
    WatcherCandidateResponse,
    WatcherRawMessageResponse,
    WatcherSourceResponse,
)
from app.watchers.service import (
    connect_gmail,
    create_watcher_account_mapping,
    delete_watcher_account_mapping,
    disconnect_watcher_source,
    get_gmail_auth_url,
    get_watcher_candidate,
    get_watcher_raw_message,
    get_watcher_source,
    ignore_candidate,
    list_watcher_account_mappings,
    list_watcher_candidates,
    list_watcher_raw_messages,
    list_watcher_sources,
    process_plan_binance_card_messages,
    resolve_candidate,
    sync_watcher_source,
)


router = APIRouter(tags=["watchers"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


@router.get(
    "/plans/{plan_id}/watchers/gmail/auth-url",
    response_model=GmailAuthUrlResponse,
)
def read_gmail_auth_url(
    plan_id: UUID,
    request: Request,
    redirect_uri: str = Query(...),
    session: Session = Depends(get_database_session),
) -> GmailAuthUrlResponse:
    try:
        url = get_gmail_auth_url(
            session=session,
            settings=request.app.state.settings,
            plan_id=plan_id,
            redirect_uri=redirect_uri,
        )
        return GmailAuthUrlResponse(auth_url=url)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/watchers/gmail/connect",
    response_model=WatcherSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_connect_gmail(
    plan_id: UUID,
    payload: ConnectGmailRequest,
    request: Request,
    session: Session = Depends(get_database_session),
) -> WatcherSourceResponse:
    try:
        with session.begin():
            source = connect_gmail(
                session=session,
                settings=request.app.state.settings,
                plan_id=plan_id,
                payload=payload,
            )
            return WatcherSourceResponse.model_validate(source)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GmailApiError as exc:
        raise _unprocessable(str(exc)) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.get(
    "/plans/{plan_id}/watchers/sources",
    response_model=list[WatcherSourceResponse],
)
def read_watcher_sources(
    plan_id: UUID,
    session: Session = Depends(get_database_session),
) -> list[WatcherSourceResponse]:
    try:
        sources = list_watcher_sources(session, plan_id)
        return [WatcherSourceResponse.model_validate(s) for s in sources]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/watchers/sources/{source_id}",
    response_model=WatcherSourceResponse,
)
def read_watcher_source(
    plan_id: UUID,
    source_id: UUID,
    session: Session = Depends(get_database_session),
) -> WatcherSourceResponse:
    try:
        source = get_watcher_source(session, plan_id, source_id)
        return WatcherSourceResponse.model_validate(source)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/watchers/sources/{source_id}/disconnect",
    response_model=WatcherSourceResponse,
)
def post_disconnect_watcher_source(
    plan_id: UUID,
    source_id: UUID,
    session: Session = Depends(get_database_session),
) -> WatcherSourceResponse:
    try:
        with session.begin():
            source = disconnect_watcher_source(session, plan_id, source_id)
            return WatcherSourceResponse.model_validate(source)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/watchers/sources/{source_id}/sync",
    response_model=SyncResultResponse,
)
def post_sync_watcher_source(
    plan_id: UUID,
    source_id: UUID,
    request: Request,
    session: Session = Depends(get_database_session),
) -> SyncResultResponse:
    try:
        with session.begin():
            result = sync_watcher_source(
                session=session,
                settings=request.app.state.settings,
                plan_id=plan_id,
                source_id=source_id,
            )
            return result
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GmailApiError as exc:
        raise _unprocessable(str(exc)) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.get(
    "/plans/{plan_id}/watchers/messages",
    response_model=list[WatcherRawMessageResponse],
)
def read_watcher_messages(
    plan_id: UUID,
    source_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_database_session),
) -> list[WatcherRawMessageResponse]:
    try:
        messages = list_watcher_raw_messages(
            session=session,
            plan_id=plan_id,
            source_id=source_id,
            status=status_filter,
            limit=limit,
        )
        return [WatcherRawMessageResponse.model_validate(m) for m in messages]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/watchers/messages/{message_id}",
    response_model=WatcherRawMessageResponse,
)
def read_watcher_message(
    plan_id: UUID,
    message_id: UUID,
    session: Session = Depends(get_database_session),
) -> WatcherRawMessageResponse:
    try:
        msg = get_watcher_raw_message(session, plan_id, message_id)
        return WatcherRawMessageResponse.model_validate(msg)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


# ---------------------------------------------------------------------------
# Watcher Candidates Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/plans/{plan_id}/watchers/candidates",
    response_model=list[WatcherCandidateResponse],
)
def read_watcher_candidates(
    plan_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    candidate_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_database_session),
) -> list[WatcherCandidateResponse]:
    try:
        candidates = list_watcher_candidates(
            session=session,
            plan_id=plan_id,
            status=status_filter,
            candidate_type=candidate_type,
            limit=limit,
        )
        return [WatcherCandidateResponse.model_validate(c) for c in candidates]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/watchers/candidates/process",
    response_model=ProcessCandidatesResponse,
)
def post_process_watcher_candidates(
    plan_id: UUID,
    session: Session = Depends(get_database_session),
) -> ProcessCandidatesResponse:
    try:
        with session.begin():
            return process_plan_binance_card_messages(session, plan_id)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/watchers/candidates/{candidate_id}",
    response_model=WatcherCandidateResponse,
)
def read_watcher_candidate(
    plan_id: UUID,
    candidate_id: UUID,
    session: Session = Depends(get_database_session),
) -> WatcherCandidateResponse:
    try:
        candidate = get_watcher_candidate(session, plan_id, candidate_id)
        return WatcherCandidateResponse.model_validate(candidate)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/watchers/candidates/{candidate_id}/resolve",
    response_model=WatcherCandidateResponse,
)
def post_resolve_watcher_candidate(
    plan_id: UUID,
    candidate_id: UUID,
    payload: ResolveCandidateRequest,
    session: Session = Depends(get_database_session),
) -> WatcherCandidateResponse:
    try:
        with session.begin():
            candidate = resolve_candidate(
                session=session,
                plan_id=plan_id,
                candidate_id=candidate_id,
                payload=payload,
            )
            return WatcherCandidateResponse.model_validate(candidate)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/watchers/candidates/{candidate_id}/ignore",
    response_model=WatcherCandidateResponse,
)
def post_ignore_watcher_candidate(
    plan_id: UUID,
    candidate_id: UUID,
    payload: IgnoreCandidateRequest | None = None,
    session: Session = Depends(get_database_session),
) -> WatcherCandidateResponse:
    try:
        with session.begin():
            reason = payload.reason if payload else None
            candidate = ignore_candidate(
                session=session,
                plan_id=plan_id,
                candidate_id=candidate_id,
                reason=reason,
            )
            return WatcherCandidateResponse.model_validate(candidate)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


# ---------------------------------------------------------------------------
# Account Mappings Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/plans/{plan_id}/watchers/mappings",
    response_model=list[WatcherAccountMappingResponse],
)
def read_watcher_account_mappings(
    plan_id: UUID,
    source_type: str | None = Query(None),
    session: Session = Depends(get_database_session),
) -> list[WatcherAccountMappingResponse]:
    try:
        mappings = list_watcher_account_mappings(
            session=session,
            plan_id=plan_id,
            source_type=source_type,
        )
        return [WatcherAccountMappingResponse.model_validate(m) for m in mappings]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post(
    "/plans/{plan_id}/watchers/mappings",
    response_model=WatcherAccountMappingResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_create_watcher_account_mapping(
    plan_id: UUID,
    payload: CreateAccountMappingRequest,
    session: Session = Depends(get_database_session),
) -> WatcherAccountMappingResponse:
    try:
        with session.begin():
            mapping = create_watcher_account_mapping(
                session=session,
                plan_id=plan_id,
                payload=payload,
            )
            return WatcherAccountMappingResponse.model_validate(mapping)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc


@router.post(
    "/plans/{plan_id}/watchers/mappings/{mapping_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_watcher_account_mapping_endpoint(
    plan_id: UUID,
    mapping_id: UUID,
    session: Session = Depends(get_database_session),
) -> None:
    try:
        with session.begin():
            delete_watcher_account_mapping(
                session=session,
                plan_id=plan_id,
                mapping_id=mapping_id,
            )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
