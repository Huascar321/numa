from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import CreationConflict, ResourceNotFound
from app.db import session_scope
from app.ledger.service import ArchivedResource, LedgerValidationError
from app.statements.schemas import (
    StatementCommitRequest,
    StatementDryRunRequest,
    StatementDryRunResponse,
    StatementImportDetail,
    StatementImportSummary,
)
from app.statements.service import (
    commit_statement,
    dry_run_statement,
    get_statement_import,
    list_statement_imports,
)


router = APIRouter(tags=["statements"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResourceNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CreationConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (ArchivedResource, LedgerValidationError, ValueError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
    )


@router.post(
    "/plans/{plan_id}/statements/dry-run",
    response_model=StatementDryRunResponse,
)
def preview_statement(
    plan_id: UUID,
    payload: StatementDryRunRequest,
    session: Session = Depends(get_database_session),
) -> StatementDryRunResponse:
    try:
        return dry_run_statement(session, plan_id, payload)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.put(
    "/plans/{plan_id}/statements/{import_id}/commit",
    response_model=StatementImportDetail,
)
def execute_commit_statement(
    plan_id: UUID,
    import_id: UUID,
    payload: StatementCommitRequest,
    session: Session = Depends(get_database_session),
) -> StatementImportDetail:
    try:
        statement_import = commit_statement(session, plan_id, import_id, payload)
        return StatementImportDetail.model_validate(statement_import)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.get(
    "/plans/{plan_id}/statements/imports",
    response_model=list[StatementImportSummary],
)
def read_statement_imports(
    plan_id: UUID,
    account_id: UUID | None = Query(None),
    session: Session = Depends(get_database_session),
) -> list[StatementImportSummary]:
    try:
        imports = list_statement_imports(session, plan_id, account_id=account_id)
        return [StatementImportSummary.model_validate(i) for i in imports]
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.get(
    "/plans/{plan_id}/statements/imports/{import_id}",
    response_model=StatementImportDetail,
)
def read_statement_import_detail(
    plan_id: UUID,
    import_id: UUID,
    session: Session = Depends(get_database_session),
) -> StatementImportDetail:
    try:
        statement_import = get_statement_import(session, plan_id, import_id)
        return StatementImportDetail.model_validate(statement_import)
    except Exception as exc:
        raise _handle_error(exc) from exc
