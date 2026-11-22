from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.service import get_plan, ResourceNotFound
from app.db import session_scope
from app.gmail.client import (
    CALLBACK_PATH,
    GmailClient,
    GmailConfigurationError,
    require_configuration,
    require_sender_configuration,
)
from app.gmail.models import GmailMessage, GmailSource
from app.gmail.service import digest, disconnect, finish_oauth, source_for, start_oauth

router = APIRouter(tags=["gmail"])


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def get_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def get_client(request: Request) -> Iterator[GmailClient]:
    client = GmailClient(request.app.state.settings)
    try:
        yield client
    finally:
        client.close()


def source_response(session: Session, source: GmailSource) -> dict:
    counts = dict(
        session.execute(
            select(GmailMessage.status, func.count())
            .where(GmailMessage.source_id == source.id)
            .group_by(GmailMessage.status)
        ).all()
    )
    return {
        "id": source.id,
        "plan_id": source.plan_id,
        "email": source.email,
        "status": source.status,
        "sync_mode": source.sync_mode,
        "allowed_senders": source.allowed_senders,
        "last_synced_at": source.last_synced_at,
        "last_error": source.last_error,
        "message_count": sum(counts.values()),
        "review_count": counts.get("review", 0) + counts.get("unavailable", 0),
    }


def cookie_name(state: str) -> str:
    return "numa_gmail_" + digest(state)[:24]


@router.get("/plans/{plan_id}/gmail")
def get_sources(
    plan_id: UUID, request: Request, session: Session = Depends(get_session)
) -> dict:
    try:
        get_plan(session, plan_id)
    except ResourceNotFound:
        raise HTTPException(404, "Plan not found.") from None
    try:
        require_configuration(request.app.state.settings)
        require_sender_configuration(request.app.state.settings)
        configured = True
    except GmailConfigurationError:
        configured = False
    sources = session.scalars(
        select(GmailSource)
        .where(GmailSource.plan_id == plan_id)
        .order_by(GmailSource.created_at)
    ).all()
    return {
        "configured": configured,
        "configured_senders": request.app.state.settings.gmail_allowed_senders,
        "sources": [source_response(session, item) for item in sources],
    }


@router.post("/plans/{plan_id}/gmail/{source_id}/oauth")
def post_oauth(
    plan_id: UUID,
    source_id: UUID,
    payload: EmptyRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    try:
        url, state, browser = start_oauth(
            session, request.app.state.settings, plan_id, source_id
        )
    except ResourceNotFound:
        raise HTTPException(404, "Plan or connection not found.") from None
    response.set_cookie(
        cookie_name(state),
        browser,
        max_age=600,
        httponly=True,
        secure=(request.app.state.settings.gmail_redirect_uri or "").startswith(
            "https://"
        ),
        samesite="lax",
        path=CALLBACK_PATH,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authorization_url": url}


@router.get(CALLBACK_PATH)
def oauth_callback(
    request: Request,
    state: str = Query(min_length=1, max_length=256),
    code: str | None = Query(default=None, max_length=4096),
    error: str | None = None,
    session: Session = Depends(get_session),
    client: GmailClient = Depends(get_client),
) -> Response:
    source = finish_oauth(
        session,
        request.app.state.settings,
        client,
        state,
        request.cookies.get(cookie_name(state), ""),
        code,
        error is not None,
    )
    response = RedirectResponse(f"/plans/{source.plan_id}/gmail", status_code=303)
    response.delete_cookie(cookie_name(state), path=CALLBACK_PATH)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/plans/{plan_id}/gmail/{source_id}/disconnect")
def post_disconnect(
    plan_id: UUID,
    source_id: UUID,
    payload: EmptyRequest,
    session: Session = Depends(get_session),
) -> dict:
    try:
        source = disconnect(session, plan_id, source_id)
    except ResourceNotFound:
        raise HTTPException(404, "Connection not found.") from None
    return source_response(session, source)


@router.get("/plans/{plan_id}/gmail/{source_id}/messages")
def get_messages(
    plan_id: UUID,
    source_id: UUID,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    try:
        source_for(session, plan_id, source_id)
    except ResourceNotFound:
        raise HTTPException(404, "Connection not found.") from None
    rows = session.scalars(
        select(GmailMessage)
        .where(GmailMessage.source_id == source_id, GmailMessage.id > after)
        .order_by(GmailMessage.id)
        .limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "gmail_id": row.gmail_id,
                "status": row.status,
                "ingested_at": row.ingested_at,
                "decoded": row.decoded,
            }
            for row in rows[:limit]
        ],
        "next_after": rows[limit - 1].id if len(rows) > limit else None,
    }
