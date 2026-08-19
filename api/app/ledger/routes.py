from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.accounts.models import Account
from app.accounts.schemas import BalanceResponse
from app.accounts.service import account_balance, get_account, get_plan
from app.db import session_scope
from app.ledger.models import Category, CategoryGroup, MonthlyBudgetAssignment, Tag, Transaction, TransactionCorrection, Transfer, TransferLeg, PostedAccountMovement
from app.ledger.schemas import (
    AssignmentCreate,
    AssignmentResponse,
    CategoryCreate,
    CategoryEnvelopeResponse,
    CategoryGroupCreate,
    CategoryGroupPatch,
    CategoryGroupResponse,
    CategoryPatch,
    CategoryResponse,
    MonthlySummaryResponse,
    TagCreate,
    TagPatch,
    TagResponse,
    TransactionCorrectionCreate,
    TransactionCorrectionResponse,
    TransactionCreate,
    TransactionResponse,
    TransferCreate,
    TransferReversalCreate,
    TransferResponse,
)
from app.ledger.service import (
    ArchivedResource,
    CreationResult,
    GroupHasActiveCategories,
    LedgerValidationError,
    ProtectedResource,
    archive_category,
    archive_category_group,
    archive_tag,
    assignment_response,
    category_envelope,
    correct_transaction,
    create_assignment,
    create_category,
    create_category_group,
    create_tag,
    create_transaction,
    get_transaction,
    list_categories,
    list_category_groups,
    list_corrections,
    list_tags,
    list_transactions,
    monthly_summary,
    patch_category,
    patch_category_group,
    patch_tag,
    transaction_snapshot,
    create_transfer,
    get_transfer,
    list_transfers,
    reverse_transfer,
)
from app.accounts.service import CreationConflict, ResourceNotFound, require_currency
from app.ledger.service import fixed_amount


router = APIRouter(tags=["ledger"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _invalid(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
    )


def _category_group_response(group: CategoryGroup) -> CategoryGroupResponse:
    return CategoryGroupResponse.model_validate(group)


def _category_response(session: Session, category: Category) -> CategoryResponse:
    currency = require_currency(session, get_plan(session, category.plan_id).reporting_currency_code)
    return CategoryResponse.model_validate(
        {
            "id": category.id, "plan_id": category.plan_id, "group_id": category.group_id,
            "name": category.name, "is_pending": category.is_pending, "status": category.status,
            "goal_type": category.goal_type,
            "goal_target": fixed_amount(Decimal(category.goal_target), currency) if category.goal_target is not None else None,
            "goal_due_month": category.goal_due_month, "created_at": category.created_at,
            "updated_at": category.updated_at,
        }
    )


def _tag_response(tag: Tag) -> TagResponse:
    return TagResponse.model_validate(tag)


def _transaction_response(session: Session, transaction: Transaction) -> TransactionResponse:
    snapshot = transaction_snapshot(session, transaction)
    leg = session.scalar(select(TransferLeg).where(TransferLeg.plan_id == transaction.plan_id, TransferLeg.transaction_id == transaction.id))
    return TransactionResponse.model_validate(
        {
            **snapshot,
            "amount": snapshot["amount"],
            "currency_code": transaction.currency_code,
            "created_at": transaction.created_at,
            "updated_at": transaction.updated_at,
            "transfer_id": leg.transfer_id if leg else None,
            "transfer_role": leg.role if leg else None,
        }
    )


def _correction_response(correction: TransactionCorrection) -> TransactionCorrectionResponse:
    return TransactionCorrectionResponse.model_validate(
        {
            "id": correction.id,
            "plan_id": correction.plan_id,
            "transaction_id": correction.transaction_id,
            "correction_sequence": correction.correction_sequence,
            "before_snapshot": correction.before_snapshot,
            "after_snapshot": correction.after_snapshot,
            "provenance": correction.provenance,
            "created_at": correction.created_at,
        }
    )


def _transfer_response(session: Session, transfer: Transfer) -> TransferResponse:
    legs: list[dict[str, object]] = []
    for leg in session.scalars(select(TransferLeg).where(TransferLeg.plan_id == transfer.plan_id, TransferLeg.transfer_id == transfer.id).order_by((TransferLeg.role == "outbound").desc())):
        movement = session.scalar(select(PostedAccountMovement).where(PostedAccountMovement.plan_id == transfer.plan_id, PostedAccountMovement.transaction_id == leg.transaction_id, PostedAccountMovement.movement_kind == "original"))
        if movement is None:
            raise RuntimeError("Transfer leg has no movement")
        legs.append({"id": leg.id, "role": leg.role, "transaction_id": leg.transaction_id, "movement_id": movement.id})
    outbound_currency = require_currency(session, transfer.outbound_currency_code)
    inbound_currency = require_currency(session, transfer.inbound_currency_code)
    result: dict[str, object] = {"id": transfer.id, "plan_id": transfer.plan_id, "source_account_id": transfer.source_account_id,
        "destination_account_id": transfer.destination_account_id, "outbound_amount": fixed_amount(Decimal(transfer.outbound_amount), outbound_currency),
        "outbound_currency_code": transfer.outbound_currency_code, "inbound_amount": fixed_amount(Decimal(transfer.inbound_amount), inbound_currency),
        "inbound_currency_code": transfer.inbound_currency_code, "event_at": transfer.event_at, "rate": format(Decimal(transfer.rate), "f"),
        "memo": transfer.memo, "reversal_reason": transfer.reversal_reason, "provenance": transfer.provenance,
        "reverses_transfer_id": transfer.reverses_transfer_id, "created_at": transfer.created_at, "legs": legs}
    if transfer.outbound_currency_code != transfer.inbound_currency_code:
        result["rate_source"] = transfer.rate_source
    return TransferResponse.model_validate(result)


@router.get(
    "/plans/{plan_id}/accounts/{account_id}/balance",
    response_model=BalanceResponse,
)
def get_account_balance(
    plan_id: UUID,
    account_id: UUID,
    session: Session = Depends(get_database_session),
) -> BalanceResponse:
    try:
        account = get_account(session, plan_id, account_id)
        return account_balance(session, account)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.put("/plans/{plan_id}/transfers/{transfer_id}", response_model=TransferResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
def put_transfer(plan_id: UUID, transfer_id: UUID, payload: TransferCreate, response: Response,
                 session: Session = Depends(get_database_session)) -> TransferResponse:
    try:
        with session.begin():
            result = create_transfer(session, plan_id=plan_id, transfer_id=transfer_id, payload=payload)
            body = _transfer_response(session, result.resource)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return body


@router.get("/plans/{plan_id}/transfers", response_model=list[TransferResponse], response_model_exclude_none=True)
def get_transfers(plan_id: UUID, session: Session = Depends(get_database_session)) -> list[TransferResponse]:
    try:
        return [_transfer_response(session, item) for item in list_transfers(session, plan_id)]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get("/plans/{plan_id}/transfers/{transfer_id}", response_model=TransferResponse, response_model_exclude_none=True)
def get_transfer_route(plan_id: UUID, transfer_id: UUID, session: Session = Depends(get_database_session)) -> TransferResponse:
    try:
        return _transfer_response(session, get_transfer(session, plan_id, transfer_id))
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.put("/plans/{plan_id}/transfers/{transfer_id}/reversals/{reversal_id}", response_model=TransferResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
def put_transfer_reversal(plan_id: UUID, transfer_id: UUID, reversal_id: UUID, payload: TransferReversalCreate,
                          response: Response, session: Session = Depends(get_database_session)) -> TransferResponse:
    try:
        with session.begin():
            result = reverse_transfer(session, plan_id=plan_id, transfer_id=transfer_id, reversal_id=reversal_id, payload=payload)
            body = _transfer_response(session, result.resource)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return body


@router.put(
    "/plans/{plan_id}/category-groups/{group_id}",
    response_model=CategoryGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_category_group(
    plan_id: UUID,
    group_id: UUID,
    payload: CategoryGroupCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> CategoryGroupResponse:
    try:
        with session.begin():
            result = create_category_group(
                session, plan_id=plan_id, group_id=group_id, payload=payload
            )
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except (ResourceNotFound, LedgerValidationError) as exc:
        raise _not_found(exc) if isinstance(exc, ResourceNotFound) else _invalid(exc)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _category_group_response(result.resource)


@router.get(
    "/plans/{plan_id}/category-groups",
    response_model=list[CategoryGroupResponse],
)
def get_category_groups(
    plan_id: UUID, session: Session = Depends(get_database_session)
) -> list[CategoryGroupResponse]:
    try:
        return [_category_group_response(item) for item in list_category_groups(session, plan_id)]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/category-groups/{group_id}",
    response_model=CategoryGroupResponse,
)
def get_category_group(
    plan_id: UUID, group_id: UUID, session: Session = Depends(get_database_session)
) -> CategoryGroupResponse:
    try:
        groups = [item for item in list_category_groups(session, plan_id) if item.id == group_id]
        if not groups:
            raise ResourceNotFound("Category Group not found")
        return _category_group_response(groups[0])
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch(
    "/plans/{plan_id}/category-groups/{group_id}",
    response_model=CategoryGroupResponse,
)
def patch_group(
    plan_id: UUID,
    group_id: UUID,
    payload: CategoryGroupPatch,
    session: Session = Depends(get_database_session),
) -> CategoryGroupResponse:
    try:
        with session.begin():
            group = patch_category_group(
                session, plan_id=plan_id, group_id=group_id, payload=payload
            )
        return _category_group_response(group)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _conflict(exc) from exc


@router.post(
    "/plans/{plan_id}/category-groups/{group_id}/archive",
    response_model=CategoryGroupResponse,
)
def post_archive_group(
    plan_id: UUID, group_id: UUID, session: Session = Depends(get_database_session)
) -> CategoryGroupResponse:
    try:
        with session.begin():
            group = archive_category_group(session, plan_id=plan_id, group_id=group_id)
        return _category_group_response(group)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _conflict(exc) from exc


@router.put(
    "/plans/{plan_id}/categories/{category_id}",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_category(
    plan_id: UUID,
    category_id: UUID,
    payload: CategoryCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> CategoryResponse:
    try:
        with session.begin():
            result = create_category(
                session, plan_id=plan_id, category_id=category_id, payload=payload
            )
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _conflict(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _category_response(session, result.resource)


@router.get("/plans/{plan_id}/categories", response_model=list[CategoryResponse])
def get_categories(
    plan_id: UUID, session: Session = Depends(get_database_session)
) -> list[CategoryResponse]:
    try:
        return [_category_response(session, item) for item in list_categories(session, plan_id)]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/categories/{category_id}", response_model=CategoryResponse
)
def get_category(
    plan_id: UUID, category_id: UUID, session: Session = Depends(get_database_session)
) -> CategoryResponse:
    try:
        items = [item for item in list_categories(session, plan_id) if item.id == category_id]
        if not items:
            raise ResourceNotFound("Category not found")
        return _category_response(session, items[0])
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch(
    "/plans/{plan_id}/categories/{category_id}", response_model=CategoryResponse
)
def patch_category_route(
    plan_id: UUID,
    category_id: UUID,
    payload: CategoryPatch,
    session: Session = Depends(get_database_session),
) -> CategoryResponse:
    try:
        with session.begin():
            category = patch_category(
                session, plan_id=plan_id, category_id=category_id, payload=payload
            )
        return _category_response(session, category)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _conflict(exc) from exc


@router.post(
    "/plans/{plan_id}/categories/{category_id}/archive",
    response_model=CategoryResponse,
)
def post_archive_category(
    plan_id: UUID, category_id: UUID, session: Session = Depends(get_database_session)
) -> CategoryResponse:
    try:
        with session.begin():
            category = archive_category(session, plan_id=plan_id, category_id=category_id)
        return _category_response(session, category)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _conflict(exc) from exc


@router.put(
    "/plans/{plan_id}/tags/{tag_id}", response_model=TagResponse, status_code=status.HTTP_201_CREATED
)
def put_tag(
    plan_id: UUID,
    tag_id: UUID,
    payload: TagCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> TagResponse:
    try:
        with session.begin():
            result = create_tag(session, plan_id=plan_id, tag_id=tag_id, payload=payload)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _tag_response(result.resource)


@router.get("/plans/{plan_id}/tags", response_model=list[TagResponse])
def get_tags(
    plan_id: UUID, session: Session = Depends(get_database_session)
) -> list[TagResponse]:
    try:
        return [_tag_response(item) for item in list_tags(session, plan_id)]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get("/plans/{plan_id}/tags/{tag_id}", response_model=TagResponse)
def get_tag(
    plan_id: UUID, tag_id: UUID, session: Session = Depends(get_database_session)
) -> TagResponse:
    try:
        items = [item for item in list_tags(session, plan_id) if item.id == tag_id]
        if not items:
            raise ResourceNotFound("Tag not found")
        return _tag_response(items[0])
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.patch("/plans/{plan_id}/tags/{tag_id}", response_model=TagResponse)
def patch_tag_route(
    plan_id: UUID,
    tag_id: UUID,
    payload: TagPatch,
    session: Session = Depends(get_database_session),
) -> TagResponse:
    try:
        with session.begin():
            tag = patch_tag(session, plan_id=plan_id, tag_id=tag_id, payload=payload)
        return _tag_response(tag)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _conflict(exc) from exc


@router.post("/plans/{plan_id}/tags/{tag_id}/archive", response_model=TagResponse)
def post_archive_tag(
    plan_id: UUID, tag_id: UUID, session: Session = Depends(get_database_session)
) -> TagResponse:
    try:
        with session.begin():
            tag = archive_tag(session, plan_id=plan_id, tag_id=tag_id)
        return _tag_response(tag)
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.put(
    "/plans/{plan_id}/transactions/{transaction_id}",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_transaction(
    plan_id: UUID,
    transaction_id: UUID,
    payload: TransactionCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> TransactionResponse:
    try:
        with session.begin():
            result = create_transaction(
                session,
                plan_id=plan_id,
                transaction_id=transaction_id,
                payload=payload,
            )
            transaction = result.resource
            transaction_response = _transaction_response(session, transaction)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return transaction_response


@router.get("/plans/{plan_id}/transactions", response_model=list[TransactionResponse | TransferResponse], response_model_exclude_none=True)
def get_transactions(
    plan_id: UUID, session: Session = Depends(get_database_session)
) -> list[TransactionResponse | TransferResponse]:
    try:
        return [_transfer_response(session, item) if isinstance(item, Transfer) else _transaction_response(session, item) for item in list_transactions(session, plan_id)]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/transactions/{transaction_id}", response_model=TransactionResponse
)
def get_transaction_route(
    plan_id: UUID, transaction_id: UUID, session: Session = Depends(get_database_session)
) -> TransactionResponse:
    try:
        return _transaction_response(session, get_transaction(session, plan_id, transaction_id))
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/plans/{plan_id}/transactions/{transaction_id}/corrections",
    response_model=list[TransactionCorrectionResponse],
)
def get_transaction_corrections(
    plan_id: UUID, transaction_id: UUID, session: Session = Depends(get_database_session)
) -> list[TransactionCorrectionResponse]:
    try:
        return [_correction_response(item) for item in list_corrections(session, plan_id, transaction_id)]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.put(
    "/plans/{plan_id}/transactions/{transaction_id}/corrections/{correction_id}",
    response_model=TransactionCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_correction(
    plan_id: UUID,
    transaction_id: UUID,
    correction_id: UUID,
    payload: TransactionCorrectionCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> TransactionCorrectionResponse:
    try:
        with session.begin():
            result = correct_transaction(
                session,
                plan_id=plan_id,
                transaction_id=transaction_id,
                correction_id=correction_id,
                payload=payload,
            )
            correction_response = _correction_response(result.resource)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return correction_response


@router.put(
    "/plans/{plan_id}/budget-assignments/{assignment_id}",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def put_assignment(
    plan_id: UUID,
    assignment_id: UUID,
    payload: AssignmentCreate,
    response: Response,
    session: Session = Depends(get_database_session),
) -> AssignmentResponse:
    try:
        with session.begin():
            result = create_assignment(
                session,
                plan_id=plan_id,
                assignment_id=assignment_id,
                payload=payload,
            )
            assignment_result = assignment_response(session, result.resource)
    except CreationConflict as exc:
        raise _conflict(exc) from exc
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return assignment_result


@router.get(
    "/plans/{plan_id}/budget/months/{month}", response_model=MonthlySummaryResponse
)
def get_month_summary(
    plan_id: UUID, month: str, session: Session = Depends(get_database_session)
) -> MonthlySummaryResponse:
    try:
        return MonthlySummaryResponse.model_validate(
            monthly_summary(session, plan_id=plan_id, month_key=month)
        )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc


@router.get(
    "/plans/{plan_id}/budget/months/{month}/categories",
    response_model=list[CategoryEnvelopeResponse],
)
def get_month_categories(
    plan_id: UUID, month: str, session: Session = Depends(get_database_session)
) -> list[CategoryEnvelopeResponse]:
    try:
        categories = list_categories(session, plan_id)
        return [
            CategoryEnvelopeResponse.model_validate(
                category_envelope(
                    session,
                    plan_id=plan_id,
                    month_key=month,
                    category_id=category.id,
                )
            )
            for category in categories
        ]
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc


@router.get(
    "/plans/{plan_id}/budget/months/{month}/categories/{category_id}",
    response_model=CategoryEnvelopeResponse,
)
def get_month_category(
    plan_id: UUID,
    month: str,
    category_id: UUID,
    session: Session = Depends(get_database_session),
) -> CategoryEnvelopeResponse:
    try:
        return CategoryEnvelopeResponse.model_validate(
            category_envelope(
                session,
                plan_id=plan_id,
                month_key=month,
                category_id=category_id,
            )
        )
    except ResourceNotFound as exc:
        raise _not_found(exc) from exc
    except LedgerValidationError as exc:
        raise _invalid(exc) from exc
