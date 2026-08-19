from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
import json
import unicodedata
from typing import Any, Generic, Iterable, TypeVar
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.accounts.models import Account, Currency, Plan
from app.accounts.service import (
    CreationConflict,
    ResourceNotFound,
    UnknownCurrency,
    require_currency,
)
from app.ledger.models import (
    Category,
    CategoryGroup,
    MonthlyBudgetAssignment,
    PostedAccountMovement,
    Tag,
    Transaction,
    TransactionCorrection,
    TransactionTag,
    Transfer,
    TransferLeg,
)
from app.ledger.schemas import (
    AssignmentCreate,
    AssignmentResponse,
    CategoryCreate,
    CategoryGroupCreate,
    CategoryGroupPatch,
    CategoryPatch,
    TagCreate,
    TagPatch,
    TransactionCorrectionCreate,
    TransactionCreate,
    TransferCreate,
    TransferReversalCreate,
)


class LedgerValidationError(ValueError):
    """The request violates an exact-money or ledger invariant."""


class ArchivedResource(LedgerValidationError):
    """An archived resource cannot be used for a new operation."""


class ProtectedResource(LedgerValidationError):
    """A protected Pendientes resource cannot be mutated."""


class GroupHasActiveCategories(LedgerValidationError):
    """An active Category prevents its Group from being archived."""


Resource = TypeVar("Resource")


@dataclass(frozen=True)
class CreationResult(Generic[Resource]):
    resource: Resource
    created: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def parse_exact_decimal(value: str, *, field_name: str = "amount") -> Decimal:
    if not isinstance(value, str):
        raise LedgerValidationError(f"{field_name} must be a decimal string")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise LedgerValidationError(f"{field_name} must be a valid decimal string") from exc
    if not amount.is_finite():
        raise LedgerValidationError(f"{field_name} must be finite")
    return amount


def quantize_at_scale(amount: Decimal, decimal_places: int, *, positive: bool) -> Decimal:
    if positive and amount <= 0:
        raise LedgerValidationError("amount must be positive")
    quantum = Decimal(1).scaleb(-decimal_places)
    try:
        # The NUMERIC(38,18) domain exceeds Python's default Decimal context.
        # Quantization validates representability; it must never round input.
        with localcontext() as context:
            context.prec = 160
            quantized = amount.quantize(quantum)
    except InvalidOperation as exc:
        raise LedgerValidationError("amount has an invalid scale") from exc
    if quantized != amount:
        raise LedgerValidationError("amount has more decimal places than its currency")
    return quantized


def amount_for_currency(
    session: Session,
    value: str,
    currency_code: str,
    *,
    positive: bool,
) -> Decimal:
    currency = require_currency(session, currency_code)
    amount = parse_exact_decimal(value)
    return quantize_at_scale(amount, currency.decimal_places, positive=positive)


def fixed_amount(amount: Decimal, currency: Currency) -> str:
    return format(amount.quantize(Decimal(1).scaleb(-currency.decimal_places)), "f")


def require_aware_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LedgerValidationError("event_at must include a timezone offset")
    return value


def canonical_transfer_text(value: str | None, *, field: str, required: bool, maximum: int) -> str | None:
    """The API half of the UTF8 SQL canonical-transfer-text contract."""
    if value is None:
        if required:
            raise LedgerValidationError(f"{field} is required")
        return None
    result = unicodedata.normalize("NFC", value).strip(" ")
    if any(0 <= ord(char) <= 31 or ord(char) == 127 or 128 <= ord(char) <= 159 for char in result):
        raise LedgerValidationError(f"{field} contains a forbidden control character")
    if not result:
        if required:
            raise LedgerValidationError(f"{field} must not be empty")
        return None
    if len(result) > maximum:
        raise LedgerValidationError(f"{field} is too long")
    return result


TRANSFER_MIN = Decimal("0.000000000000000001")
TRANSFER_MAX = Decimal("99999999999999999999.999999999999999999")
TRANSFER_RATE_QUANTUM = Decimal("1e-38")


def transfer_amount(value: str, *, field: str) -> Decimal:
    amount = parse_exact_decimal(value, field_name=field)
    exponent = amount.as_tuple().exponent
    if amount < TRANSFER_MIN or amount > TRANSFER_MAX or not isinstance(exponent, int) or exponent < -18:
        raise LedgerValidationError(f"{field} is outside NUMERIC(38,18)")
    with localcontext() as context:
        context.prec = 160
        return amount.quantize(Decimal("1e-18"))


def transfer_amount_for_account(session: Session, value: str, account: Account, *, field: str) -> Decimal:
    amount = transfer_amount(value, field=field)
    try:
        return quantize_at_scale(amount, require_currency(session, account.currency_code).decimal_places, positive=True)
    except LedgerValidationError as exc:
        raise LedgerValidationError(f"{field} has more decimal places than its Account currency") from exc


def transfer_rate(outbound: Decimal, inbound: Decimal) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = 160
            rate = (outbound / inbound).quantize(TRANSFER_RATE_QUANTUM, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError) as exc:
        raise LedgerValidationError("transfer rate is invalid") from exc
    if not rate.is_finite() or rate <= 0 or rate > Decimal("99999999999999999999999999999999999999.99999999999999999999999999999999999999"):
        raise LedgerValidationError("transfer rate is outside NUMERIC(76,38)")
    return rate


def _get_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound("Plan not found")
    return plan


def _get_group(session: Session, plan_id: UUID, group_id: UUID) -> CategoryGroup:
    group = session.scalar(
        select(CategoryGroup).where(
            CategoryGroup.plan_id == plan_id, CategoryGroup.id == group_id
        )
    )
    if group is None:
        raise ResourceNotFound("Category Group not found")
    return group


def _get_category(session: Session, plan_id: UUID, category_id: UUID) -> Category:
    category = session.scalar(
        select(Category).where(
            Category.plan_id == plan_id, Category.id == category_id
        )
    )
    if category is None:
        raise ResourceNotFound("Category not found")
    return category


def _get_tag(session: Session, plan_id: UUID, tag_id: UUID) -> Tag:
    tag = session.scalar(
        select(Tag).where(Tag.plan_id == plan_id, Tag.id == tag_id)
    )
    if tag is None:
        raise ResourceNotFound("Tag not found")
    return tag


def _require_active_category(
    session: Session, plan_id: UUID, category_id: UUID
) -> Category:
    category = _get_category(session, plan_id, category_id)
    if category.status != "active":
        raise ArchivedResource("archived Categories cannot be selected")
    return category


def _pending_category(session: Session, plan_id: UUID) -> Category:
    category = session.scalar(
        select(Category).where(
            Category.plan_id == plan_id,
            Category.is_pending.is_(True),
            Category.status == "active",
        )
    )
    if category is None:
        raise RuntimeError("Plan has no protected Pendientes Category")
    return category


def create_category_group(
    session: Session,
    *,
    plan_id: UUID,
    group_id: UUID,
    payload: CategoryGroupCreate,
) -> CreationResult[CategoryGroup]:
    _get_plan(session, plan_id)
    request_fingerprint = fingerprint(
        {"plan_id": plan_id, "name": payload.name}
    )
    inserted_id = session.scalar(
        insert(CategoryGroup)
        .values(
            id=group_id,
            plan_id=plan_id,
            name=payload.name,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing()
        .returning(CategoryGroup.id)
    )
    group = session.scalar(
        select(CategoryGroup)
        .where(CategoryGroup.id == group_id)
        .execution_options(populate_existing=True)
    )
    if group is None:
        duplicate = session.scalar(
            select(CategoryGroup).where(
                CategoryGroup.plan_id == plan_id,
                CategoryGroup.name == payload.name,
            )
        )
        if duplicate is not None:
            raise CreationConflict("Category Group name already exists in this Plan")
        raise RuntimeError("Category Group creation result could not be loaded")
    if group.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Category Group UUID has a different creation payload")
    if group.plan_id != plan_id:
        raise CreationConflict("Category Group UUID belongs to another Plan")
    return CreationResult(group, inserted_id is not None)


def list_category_groups(session: Session, plan_id: UUID) -> list[CategoryGroup]:
    _get_plan(session, plan_id)
    return list(
        session.scalars(
            select(CategoryGroup)
            .where(CategoryGroup.plan_id == plan_id)
            .order_by(CategoryGroup.created_at, CategoryGroup.id)
        )
    )


def patch_category_group(
    session: Session, *, plan_id: UUID, group_id: UUID, payload: CategoryGroupPatch
) -> CategoryGroup:
    group = _get_group(session, plan_id, group_id)
    if group.status != "active":
        raise ArchivedResource("archived Category Groups cannot be renamed")
    group.name = payload.name
    group.updated_at = utc_now()
    session.flush()
    return group


def archive_category_group(
    session: Session, *, plan_id: UUID, group_id: UUID
) -> CategoryGroup:
    group = _get_group(session, plan_id, group_id)
    if group.status == "archived":
        return group
    active_category = session.scalar(
        select(Category.id).where(
            Category.plan_id == plan_id,
            Category.group_id == group_id,
            Category.status == "active",
        )
    )
    if active_category is not None:
        raise GroupHasActiveCategories("Category Group has active Categories")
    group.status = "archived"
    group.updated_at = utc_now()
    session.flush()
    return group


def create_category(
    session: Session,
    *,
    plan_id: UUID,
    category_id: UUID,
    payload: CategoryCreate,
) -> CreationResult[Category]:
    plan = _get_plan(session, plan_id)
    if payload.name == "Pendientes":
        raise ProtectedResource("Pendientes is protected")
    if payload.group_id is not None:
        group = _get_group(session, plan_id, payload.group_id)
        if group.status != "active":
            raise ArchivedResource("archived Category Groups cannot be selected")
    goal_target = (
        amount_for_currency(session, payload.goal_target, plan.reporting_currency_code, positive=True)
        if payload.goal_target is not None
        else None
    )
    reporting_currency = require_currency(session, plan.reporting_currency_code)
    request_fingerprint = fingerprint(
        {"plan_id": plan_id, "name": payload.name, "group_id": payload.group_id,
         "goal_type": payload.goal_type,
         "goal_target": fixed_amount(goal_target, reporting_currency) if goal_target is not None else None,
         "goal_due_month": payload.goal_due_month}
    )
    inserted_id = session.scalar(
        insert(Category)
        .values(
            id=category_id,
            plan_id=plan_id,
            group_id=payload.group_id,
            name=payload.name,
            goal_type=payload.goal_type,
            goal_target=goal_target,
            goal_due_month=payload.goal_due_month,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing()
        .returning(Category.id)
    )
    category = session.scalar(
        select(Category)
        .where(Category.id == category_id)
        .execution_options(populate_existing=True)
    )
    if category is None:
        duplicate = session.scalar(
            select(Category).where(
                Category.plan_id == plan_id,
                Category.name == payload.name,
            )
        )
        if duplicate is not None:
            raise CreationConflict("Category name already exists in this Plan")
        raise RuntimeError("Category creation result could not be loaded")
    if category.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Category UUID has a different creation payload")
    if category.plan_id != plan_id:
        raise CreationConflict("Category UUID belongs to another Plan")
    return CreationResult(category, inserted_id is not None)


def list_categories(session: Session, plan_id: UUID) -> list[Category]:
    _get_plan(session, plan_id)
    return list(
        session.scalars(
            select(Category)
            .where(Category.plan_id == plan_id)
            .order_by(Category.is_pending.desc(), Category.created_at, Category.id)
        )
    )


def patch_category(
    session: Session, *, plan_id: UUID, category_id: UUID, payload: CategoryPatch
) -> Category:
    category = _get_category(session, plan_id, category_id)
    if category.is_pending:
        raise ProtectedResource("Pendientes is protected")
    if category.status != "active":
        raise ArchivedResource("archived Categories cannot be mutated")
    if payload.name is not None:
        if payload.name == "Pendientes":
            raise ProtectedResource("Pendientes is protected")
        category.name = payload.name
    goal_fields = {"goal_type", "goal_target", "goal_due_month"}
    if payload.model_fields_set & goal_fields:
        if category.is_pending:
            raise ProtectedResource("Pendientes is protected")
        if payload.goal_target is None:
            category.goal_type = None
            category.goal_target = None
            category.goal_due_month = None
        else:
            plan = _get_plan(session, plan_id)
            category.goal_type = payload.goal_type
            category.goal_target = amount_for_currency(
                session, payload.goal_target, plan.reporting_currency_code, positive=True
            )
            category.goal_due_month = payload.goal_due_month
    if "group_id" in payload.model_fields_set:
        if payload.group_id is None:
            category.group_id = None
        else:
            group = _get_group(session, plan_id, payload.group_id)
            if group.status != "active":
                raise ArchivedResource("archived Category Groups cannot be selected")
            category.group_id = payload.group_id
    category.updated_at = utc_now()
    session.flush()
    return category


def archive_category(
    session: Session, *, plan_id: UUID, category_id: UUID
) -> Category:
    category = _get_category(session, plan_id, category_id)
    if category.is_pending:
        raise ProtectedResource("Pendientes is protected")
    if category.status == "active":
        category.status = "archived"
        category.updated_at = utc_now()
        session.flush()
    return category


def create_tag(
    session: Session,
    *,
    plan_id: UUID,
    tag_id: UUID,
    payload: TagCreate,
) -> CreationResult[Tag]:
    _get_plan(session, plan_id)
    request_fingerprint = fingerprint({"plan_id": plan_id, "name": payload.name})
    inserted_id = session.scalar(
        insert(Tag)
        .values(
            id=tag_id,
            plan_id=plan_id,
            name=payload.name,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing()
        .returning(Tag.id)
    )
    tag = session.scalar(
        select(Tag)
        .where(Tag.id == tag_id)
        .execution_options(populate_existing=True)
    )
    if tag is None:
        duplicate = session.scalar(
            select(Tag).where(Tag.plan_id == plan_id, Tag.name == payload.name)
        )
        if duplicate is not None:
            raise CreationConflict("Tag name already exists in this Plan")
        raise RuntimeError("Tag creation result could not be loaded")
    if tag.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Tag UUID has a different creation payload")
    if tag.plan_id != plan_id:
        raise CreationConflict("Tag UUID belongs to another Plan")
    return CreationResult(tag, inserted_id is not None)


def list_tags(session: Session, plan_id: UUID) -> list[Tag]:
    _get_plan(session, plan_id)
    return list(
        session.scalars(
            select(Tag).where(Tag.plan_id == plan_id).order_by(Tag.created_at, Tag.id)
        )
    )


def patch_tag(session: Session, *, plan_id: UUID, tag_id: UUID, payload: TagPatch) -> Tag:
    tag = _get_tag(session, plan_id, tag_id)
    if tag.status != "active":
        raise ArchivedResource("archived Tags cannot be renamed")
    tag.name = payload.name
    tag.updated_at = utc_now()
    session.flush()
    return tag


def archive_tag(session: Session, *, plan_id: UUID, tag_id: UUID) -> Tag:
    tag = _get_tag(session, plan_id, tag_id)
    if tag.status == "active":
        tag.status = "archived"
        tag.updated_at = utc_now()
        session.flush()
    return tag


def _validate_tag_ids(
    session: Session, plan_id: UUID, tag_ids: Iterable[UUID]
) -> list[UUID]:
    normalized = list(tag_ids)
    if len(set(normalized)) != len(normalized):
        raise LedgerValidationError("tags must not contain duplicates")
    for tag_id in normalized:
        tag = _get_tag(session, plan_id, tag_id)
        if tag.status != "active":
            raise ArchivedResource("archived Tags cannot be selected")
    return normalized


def _tag_state(session: Session, plan_id: UUID, transaction_id: UUID) -> list[UUID]:
    links = list(
        session.scalars(
            select(TransactionTag)
            .where(
                TransactionTag.plan_id == plan_id,
                TransactionTag.transaction_id == transaction_id,
            )
            .order_by(TransactionTag.created_at, TransactionTag.id)
        )
    )
    states: dict[UUID, str] = {}
    for link in links:
        states[link.tag_id] = link.action
    return sorted(tag_id for tag_id, action in states.items() if action == "attached")


def transaction_snapshot(
    session: Session, transaction: Transaction, *, tags: list[UUID] | None = None
) -> dict[str, Any]:
    currency = require_currency(session, transaction.currency_code)
    return {
        "id": str(transaction.id),
        "plan_id": str(transaction.plan_id),
        "account_id": str(transaction.account_id),
        "type": transaction.type,
        "amount": fixed_amount(Decimal(transaction.amount), currency),
        "currency_code": transaction.currency_code,
        "event_at": transaction.event_at.isoformat(),
        "category_id": str(transaction.category_id) if transaction.category_id is not None else None,
        "merchant": transaction.merchant,
        "memo": transaction.memo,
        "photo_reference": transaction.photo_reference,
        "location": transaction.location,
        "tags": [str(tag_id) for tag_id in (tags if tags is not None else _tag_state(session, transaction.plan_id, transaction.id))],
        "source": transaction.source,
        "source_metadata": transaction.source_metadata,
        "provenance": transaction.provenance,
    }


def create_transaction(
    session: Session,
    *,
    plan_id: UUID,
    transaction_id: UUID,
    payload: TransactionCreate,
) -> CreationResult[Transaction]:
    plan = _get_plan(session, plan_id)
    account = session.scalar(
        select(Account).where(Account.plan_id == plan_id, Account.id == payload.account_id)
    )
    if account is None:
        raise ResourceNotFound("Account not found")
    if account.status != "active":
        raise ArchivedResource("archived Accounts reject new postings")
    if payload.currency_code != account.currency_code:
        raise LedgerValidationError("Transaction currency must match Account currency")
    amount = amount_for_currency(
        session, payload.amount, account.currency_code, positive=True
    )
    event_at = require_aware_timestamp(payload.event_at)
    category = (
        _pending_category(session, plan_id)
        if payload.category_id is None
        else _require_active_category(session, plan_id, payload.category_id)
    )
    tags = _validate_tag_ids(session, plan_id, payload.tags)
    if payload.type not in {"income", "expense"}:
        raise LedgerValidationError("only income and expense are public transaction types")
    canonical = {
        "plan_id": plan_id,
        "type": payload.type,
        "account_id": account.id,
        "amount": amount,
        "currency_code": account.currency_code,
        "event_at": event_at,
        "category_id": category.id,
        "merchant": payload.merchant,
        "memo": payload.memo,
        "photo_reference": payload.photo_reference,
        "location": payload.location,
        "tags": sorted(tags),
        "source": "manual",
        "source_metadata": payload.source_metadata,
        "provenance": payload.provenance,
    }
    request_fingerprint = fingerprint(canonical)
    inserted_id = session.scalar(
        insert(Transaction)
        .values(
            id=transaction_id,
            plan_id=plan_id,
            account_id=account.id,
            type=payload.type,
            amount=amount,
            currency_code=account.currency_code,
            event_at=event_at,
            category_id=category.id,
            merchant=payload.merchant,
            memo=payload.memo,
            photo_reference=payload.photo_reference,
            location=payload.location,
            source="manual",
            source_metadata=payload.source_metadata,
            provenance=payload.provenance,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing()
        .returning(Transaction.id)
    )
    transaction = session.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .execution_options(populate_existing=True)
    )
    if transaction is None:
        raise RuntimeError("created Transaction could not be loaded")
    if transaction.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Transaction UUID has a different creation payload")
    if transaction.plan_id != plan_id:
        raise CreationConflict("Transaction UUID belongs to another Plan")
    if inserted_id is None:
        return CreationResult(transaction, False)

    signed_amount = amount if payload.type == "income" else -amount
    session.add(
        PostedAccountMovement(
            id=uuid4(),
            plan_id=plan_id,
            account_id=account.id,
            transaction_id=transaction.id,
            currency_code=account.currency_code,
            signed_amount=signed_amount,
            transaction_type=payload.type,
            effective_at=event_at,
            category_id=category.id,
            merchant=payload.merchant,
            memo=payload.memo,
            photo_reference=payload.photo_reference,
            location=payload.location,
            source="manual",
            source_metadata=payload.source_metadata,
            provenance=payload.provenance,
            movement_kind="original",
            correction_sequence=0,
            posted_at=utc_now(),
        )
    )
    for tag_id in tags:
        session.add(
            TransactionTag(
                id=uuid4(),
                plan_id=plan_id,
                transaction_id=transaction.id,
                tag_id=tag_id,
                action="attached",
            )
        )
    session.flush()
    return CreationResult(transaction, True)


def _transfer_accounts(session: Session, plan_id: UUID, source_id: UUID, destination_id: UUID) -> tuple[Account, Account]:
    if source_id == destination_id:
        raise LedgerValidationError("source and destination Accounts must differ")
    source = session.scalar(select(Account).where(Account.plan_id == plan_id, Account.id == source_id))
    destination = session.scalar(select(Account).where(Account.plan_id == plan_id, Account.id == destination_id))
    if source is None or destination is None:
        raise ResourceNotFound("Account not found")
    if source.status != "active" or destination.status != "active":
        raise ArchivedResource("archived Accounts reject new postings")
    return source, destination


def _transfer_fingerprint(*, plan_id: UUID, transfer_id: UUID, source: Account, destination: Account,
                          outbound: Decimal, inbound: Decimal, event_at: datetime, memo: str | None,
                          reason: str | None, rate_source: str | None, provenance: dict[str, Any],
                          reverses: UUID | None) -> str:
    return fingerprint({"plan_id": plan_id, "transfer_id": transfer_id, "source_account_id": source.id,
        "destination_account_id": destination.id, "outbound_amount": outbound,
        "outbound_currency_code": source.currency_code, "inbound_amount": inbound,
        "inbound_currency_code": destination.currency_code, "event_at": event_at, "memo": memo,
        "reversal_reason": reason, "rate_source": rate_source, "provenance": provenance,
        "reverses_transfer_id": reverses, "legs": ["outbound", "inbound"]})


def _post_transfer(session: Session, *, plan_id: UUID, transfer_id: UUID, source: Account,
                   destination: Account, outbound: Decimal, inbound: Decimal, event_at: datetime,
                   memo: str | None, reversal_reason: str | None, rate_source: str | None,
                   provenance: dict[str, Any], reverses_transfer_id: UUID | None) -> CreationResult[Transfer]:
    if source.currency_code == destination.currency_code:
        with localcontext() as context:
            context.prec = 160
            rate = Decimal(1).quantize(TRANSFER_RATE_QUANTUM)
    else:
        rate = transfer_rate(outbound, inbound)
    if source.currency_code == destination.currency_code:
        if outbound != inbound:
            raise LedgerValidationError("same-currency transfer amounts must match")
        if rate_source is not None:
            raise LedgerValidationError("same-currency transfer must not include rate_source")
    elif rate_source is None:
        raise LedgerValidationError("cross-currency transfer requires rate_source")
    request_fingerprint = _transfer_fingerprint(plan_id=plan_id, transfer_id=transfer_id, source=source,
        destination=destination, outbound=outbound, inbound=inbound, event_at=event_at, memo=memo,
        reason=reversal_reason, rate_source=rate_source, provenance=provenance, reverses=reverses_transfer_id)
    inserted = session.scalar(insert(Transfer).values(id=transfer_id, plan_id=plan_id,
        source_account_id=source.id, destination_account_id=destination.id, outbound_amount=outbound,
        outbound_currency_code=source.currency_code, inbound_amount=inbound,
        inbound_currency_code=destination.currency_code, event_at=event_at, rate=rate,
        rate_source=rate_source, memo=memo, reversal_reason=reversal_reason, provenance=provenance,
        creation_fingerprint=request_fingerprint, reverses_transfer_id=reverses_transfer_id)
        .on_conflict_do_nothing().returning(Transfer.id))
    # Do not disclose that a client UUID belongs to another Plan.  This query
    # also handles the post-ON-CONFLICT race after a same-Plan winner commits.
    transfer = session.scalar(select(Transfer).where(Transfer.plan_id == plan_id, Transfer.id == transfer_id).execution_options(populate_existing=True))
    if transfer is None:
        raise ResourceNotFound("Transfer not found")
    if transfer.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Transfer UUID has a different creation payload")
    if inserted is None:
        return CreationResult(transfer, False)
    outbound_transaction, inbound_transaction = uuid4(), uuid4()
    session.add_all([
        Transaction(id=outbound_transaction, plan_id=plan_id, account_id=source.id, type="transfer", amount=outbound,
            currency_code=source.currency_code, event_at=event_at, category_id=None, source="transfer",
            source_metadata={}, provenance=provenance, creation_fingerprint=fingerprint({"transfer": transfer_id, "role": "outbound"})),
        Transaction(id=inbound_transaction, plan_id=plan_id, account_id=destination.id, type="transfer", amount=inbound,
            currency_code=destination.currency_code, event_at=event_at, category_id=None, source="transfer",
            source_metadata={}, provenance=provenance, creation_fingerprint=fingerprint({"transfer": transfer_id, "role": "inbound"})),
    ])
    session.flush()
    session.add_all([
        TransferLeg(id=uuid4(), plan_id=plan_id, transfer_id=transfer_id, transaction_id=outbound_transaction, role="outbound"),
        TransferLeg(id=uuid4(), plan_id=plan_id, transfer_id=transfer_id, transaction_id=inbound_transaction, role="inbound"),
    ])
    session.flush()
    session.add_all([
        PostedAccountMovement(id=uuid4(), plan_id=plan_id, account_id=source.id, transaction_id=outbound_transaction,
            correction_id=None, correction_sequence=0, currency_code=source.currency_code, signed_amount=-outbound,
            transaction_type="transfer", effective_at=event_at, category_id=None, source="transfer", source_metadata={},
            provenance=provenance, movement_kind="original", posted_at=utc_now()),
        PostedAccountMovement(id=uuid4(), plan_id=plan_id, account_id=destination.id, transaction_id=inbound_transaction,
            correction_id=None, correction_sequence=0, currency_code=destination.currency_code, signed_amount=inbound,
            transaction_type="transfer", effective_at=event_at, category_id=None, source="transfer", source_metadata={},
            provenance=provenance, movement_kind="original", posted_at=utc_now()),
    ])
    session.flush()
    return CreationResult(transfer, True)


def create_transfer(session: Session, *, plan_id: UUID, transfer_id: UUID, payload: TransferCreate) -> CreationResult[Transfer]:
    _get_plan(session, plan_id)
    durable = session.scalar(select(Transfer).where(Transfer.plan_id == plan_id, Transfer.id == transfer_id))
    if durable is not None:
        source = session.scalar(select(Account).where(Account.plan_id == plan_id, Account.id == durable.source_account_id))
        destination = session.scalar(select(Account).where(Account.plan_id == plan_id, Account.id == durable.destination_account_id))
        if source is None or destination is None:
            raise ResourceNotFound("Transfer Account not found")
        outbound = transfer_amount_for_account(session, payload.outbound_amount, source, field="outbound_amount")
        inbound = transfer_amount_for_account(session, payload.inbound_amount, destination, field="inbound_amount")
        memo = canonical_transfer_text(payload.memo, field="memo", required=False, maximum=2000)
        if source.currency_code == destination.currency_code and "rate_source" in payload.model_fields_set:
            raise LedgerValidationError("same-currency transfer must not include rate_source")
        rate_source = canonical_transfer_text(payload.rate_source, field="rate_source", required=source.currency_code != destination.currency_code, maximum=128)
        request_fingerprint = _transfer_fingerprint(plan_id=plan_id, transfer_id=transfer_id, source=source, destination=destination,
            outbound=outbound, inbound=inbound, event_at=require_aware_timestamp(payload.event_at), memo=memo,
            reason=None, rate_source=rate_source, provenance=payload.provenance, reverses=None)
        if payload.source_account_id != source.id or payload.destination_account_id != destination.id or durable.creation_fingerprint != request_fingerprint:
            raise CreationConflict("Transfer UUID has a different creation payload")
        return CreationResult(durable, False)
    source, destination = _transfer_accounts(session, plan_id, payload.source_account_id, payload.destination_account_id)
    outbound = transfer_amount_for_account(session, payload.outbound_amount, source, field="outbound_amount")
    inbound = transfer_amount_for_account(session, payload.inbound_amount, destination, field="inbound_amount")
    event_at = require_aware_timestamp(payload.event_at)
    memo = canonical_transfer_text(payload.memo, field="memo", required=False, maximum=2000)
    if source.currency_code == destination.currency_code and "rate_source" in payload.model_fields_set:
        raise LedgerValidationError("same-currency transfer must not include rate_source")
    rate_source = canonical_transfer_text(payload.rate_source, field="rate_source", required=source.currency_code != destination.currency_code, maximum=128)
    return _post_transfer(session, plan_id=plan_id, transfer_id=transfer_id, source=source, destination=destination,
        outbound=outbound, inbound=inbound, event_at=event_at, memo=memo, reversal_reason=None,
        rate_source=rate_source, provenance=payload.provenance, reverses_transfer_id=None)


def get_transfer(session: Session, plan_id: UUID, transfer_id: UUID, *, for_update: bool = False) -> Transfer:
    query = select(Transfer).where(Transfer.plan_id == plan_id, Transfer.id == transfer_id)
    if for_update:
        query = query.with_for_update(of=Transfer)
    transfer = session.scalar(query)
    if transfer is None:
        raise ResourceNotFound("Transfer not found")
    return transfer


def list_transfers(session: Session, plan_id: UUID) -> list[Transfer]:
    _get_plan(session, plan_id)
    return list(session.scalars(select(Transfer).where(Transfer.plan_id == plan_id).order_by(Transfer.event_at.desc(), Transfer.id)))


def reverse_transfer(session: Session, *, plan_id: UUID, transfer_id: UUID, reversal_id: UUID,
                     payload: TransferReversalCreate) -> CreationResult[Transfer]:
    parent = get_transfer(session, plan_id, transfer_id, for_update=True)
    existing = session.scalar(select(Transfer).where(Transfer.plan_id == plan_id, Transfer.reverses_transfer_id == parent.id))
    if existing is not None and existing.id != reversal_id:
        raise CreationConflict("Transfer already has a reversal")
    if existing is not None:
        source = session.scalar(select(Account).where(Account.plan_id == plan_id, Account.id == parent.destination_account_id))
        destination = session.scalar(select(Account).where(Account.plan_id == plan_id, Account.id == parent.source_account_id))
        if source is None or destination is None:
            raise ResourceNotFound("Transfer Account not found")
        memo = canonical_transfer_text(payload.memo, field="memo", required=False, maximum=2000)
        reason = canonical_transfer_text(payload.reversal_reason, field="reversal_reason", required=True, maximum=500)
        request_fingerprint = _transfer_fingerprint(plan_id=plan_id, transfer_id=reversal_id, source=source, destination=destination,
            outbound=Decimal(parent.inbound_amount), inbound=Decimal(parent.outbound_amount), event_at=require_aware_timestamp(payload.event_at),
            memo=memo, reason=reason, rate_source="reversal" if source.currency_code != destination.currency_code else None,
            provenance=payload.provenance, reverses=parent.id)
        if existing.creation_fingerprint != request_fingerprint:
            raise CreationConflict("Transfer UUID has a different creation payload")
        return CreationResult(existing, False)
    source, destination = _transfer_accounts(session, plan_id, parent.destination_account_id, parent.source_account_id)
    memo = canonical_transfer_text(payload.memo, field="memo", required=False, maximum=2000)
    reason = canonical_transfer_text(payload.reversal_reason, field="reversal_reason", required=True, maximum=500)
    return _post_transfer(session, plan_id=plan_id, transfer_id=reversal_id, source=source, destination=destination,
        outbound=Decimal(parent.inbound_amount), inbound=Decimal(parent.outbound_amount), event_at=require_aware_timestamp(payload.event_at),
        memo=memo, reversal_reason=reason, rate_source="reversal" if source.currency_code != destination.currency_code else None,
        provenance=payload.provenance, reverses_transfer_id=parent.id)


def list_transactions(session: Session, plan_id: UUID) -> list[Transaction | Transfer]:
    _get_plan(session, plan_id)
    ordinary = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.plan_id == plan_id, Transaction.type != "transfer")
            .order_by(Transaction.event_at.desc(), Transaction.id)
        )
    )
    roots = list(session.scalars(select(Transfer).where(Transfer.plan_id == plan_id)))
    return sorted([*ordinary, *roots], key=lambda item: (item.event_at, item.id), reverse=True)


def get_transaction(session: Session, plan_id: UUID, transaction_id: UUID) -> Transaction:
    transaction = session.scalar(
        select(Transaction).where(
            Transaction.plan_id == plan_id, Transaction.id == transaction_id
        )
    )
    if transaction is None:
        raise ResourceNotFound("Transaction not found")
    return transaction


def _get_transaction_for_update(
    session: Session, plan_id: UUID, transaction_id: UUID
) -> Transaction:
    transaction = session.scalar(
        select(Transaction)
        .where(
            Transaction.plan_id == plan_id,
            Transaction.id == transaction_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Transaction)
    )
    if transaction is None:
        raise ResourceNotFound("Transaction not found")
    return transaction


def _current_movement(
    session: Session,
    plan_id: UUID,
    transaction_id: UUID,
) -> PostedAccountMovement:
    movement_query = select(PostedAccountMovement).where(
        PostedAccountMovement.plan_id == plan_id,
        PostedAccountMovement.transaction_id == transaction_id,
    )
    latest_sequence = session.scalar(
        select(func.coalesce(func.max(TransactionCorrection.correction_sequence), 0)).where(
            TransactionCorrection.plan_id == plan_id,
            TransactionCorrection.transaction_id == transaction_id,
        )
    ) or 0
    if latest_sequence:
        movement_query = movement_query.where(
            PostedAccountMovement.movement_kind == "replacement",
            PostedAccountMovement.correction_sequence == latest_sequence,
        )
    else:
        movement_query = movement_query.where(
            PostedAccountMovement.movement_kind == "original",
            PostedAccountMovement.correction_sequence == 0,
        )
    movement = session.scalar(
        movement_query
        .where(
            PostedAccountMovement.transaction_id == transaction_id,
        )
        .limit(1)
    )
    if movement is None:
        raise RuntimeError("Transaction has no effective movement")
    return movement


def _snapshot_from_values(
    session: Session,
    *,
    transaction: Transaction,
    account_id: UUID,
    amount: Decimal,
    currency_code: str,
    event_at: datetime,
    category_id: UUID,
    merchant: str | None,
    memo: str | None,
    photo_reference: str | None,
    location: dict[str, Any] | None,
    tags: list[UUID],
    source_metadata: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    currency = require_currency(session, currency_code)
    return {
        "id": str(transaction.id),
        "plan_id": str(transaction.plan_id),
        "account_id": str(account_id),
        "type": transaction.type,
        "amount": fixed_amount(amount, currency),
        "currency_code": currency_code,
        "event_at": event_at.isoformat(),
        "category_id": str(category_id),
        "merchant": merchant,
        "memo": memo,
        "photo_reference": photo_reference,
        "location": location,
        "tags": [str(tag_id) for tag_id in tags],
        "source": transaction.source,
        "source_metadata": source_metadata,
        "provenance": provenance,
    }


def _correction_payload_matches(
    session: Session,
    payload: TransactionCorrectionCreate,
    after_snapshot: dict[str, Any],
) -> bool:
    fields = payload.model_fields_set
    if "amount" in fields:
        if payload.amount is None:
            return False
        amount = amount_for_currency(
            session,
            payload.amount,
            str(after_snapshot["currency_code"]),
            positive=True,
        )
        if fixed_amount(amount, require_currency(session, str(after_snapshot["currency_code"]))) != after_snapshot["amount"]:
            return False
    if "account_id" in fields and str(payload.account_id) != after_snapshot["account_id"]:
        return False
    if "category_id" in fields and str(payload.category_id) != after_snapshot["category_id"]:
        return False
    if "event_at" in fields:
        if payload.event_at is None:
            return False
        if require_aware_timestamp(payload.event_at).astimezone(timezone.utc) != datetime.fromisoformat(str(after_snapshot["event_at"])).astimezone(timezone.utc):
            return False
    for field_name in (
        "merchant",
        "memo",
        "photo_reference",
        "location",
    ):
        if field_name in fields and getattr(payload, field_name) != after_snapshot[field_name]:
            return False
    if "tags" in fields:
        requested_tags = sorted(str(tag_id) for tag_id in (payload.tags or []))
        if requested_tags != sorted(str(tag_id) for tag_id in after_snapshot["tags"]):
            return False
    for field_name in ("source_metadata", "provenance"):
        if field_name in fields and getattr(payload, field_name) is not None and getattr(payload, field_name) != after_snapshot[field_name]:
            return False
    return True


def correct_transaction(
    session: Session,
    *,
    plan_id: UUID,
    transaction_id: UUID,
    correction_id: UUID,
    payload: TransactionCorrectionCreate,
) -> CreationResult[TransactionCorrection]:
    # This lock is the correction serialization boundary. It deliberately
    # precedes every snapshot, Tag-state, and effective-movement read.
    transaction = _get_transaction_for_update(session, plan_id, transaction_id)
    if transaction.type == "transfer":
        raise CreationConflict("transfer Transactions may only be reversed as a paired Transfer")
    existing_correction = session.scalar(
        select(TransactionCorrection).where(TransactionCorrection.id == correction_id)
    )
    if existing_correction is not None:
        if existing_correction.transaction_id != transaction_id:
            raise CreationConflict("Correction UUID belongs to another Transaction")
        if _correction_payload_matches(
            session, payload, existing_correction.after_snapshot
        ):
            return CreationResult(existing_correction, False)
        raise CreationConflict("Correction UUID has a different creation payload")

    before_tags = _tag_state(session, plan_id, transaction_id)
    before = transaction_snapshot(session, transaction, tags=before_tags)
    old_movement = _current_movement(session, plan_id, transaction_id)
    latest_sequence = session.scalar(
        select(func.coalesce(func.max(TransactionCorrection.correction_sequence), 0)).where(
            TransactionCorrection.plan_id == plan_id,
            TransactionCorrection.transaction_id == transaction_id,
        )
    ) or 0
    correction_sequence = int(latest_sequence) + 1
    fields = payload.model_fields_set
    current_account = session.scalar(
        select(Account).where(
            Account.plan_id == plan_id, Account.id == transaction.account_id
        )
    )
    if current_account is None:
        raise RuntimeError("Transaction Account could not be loaded")
    if "account_id" in fields and payload.account_id is None:
        raise LedgerValidationError("correction account_id cannot be null")
    target_account_id = (
        payload.account_id if "account_id" in fields else transaction.account_id
    )
    assert target_account_id is not None
    target_account = session.scalar(
        select(Account).where(Account.plan_id == plan_id, Account.id == target_account_id)
    )
    if target_account is None:
        raise ResourceNotFound("Account not found")
    if target_account.status != "active":
        raise ArchivedResource("archived Accounts reject correction destinations")
    target_currency = target_account.currency_code
    if target_currency != transaction.currency_code:
        raise LedgerValidationError(
            "correction Account currency must match the Transaction currency"
        )
    if "amount" in fields:
        if payload.amount is None:
            raise LedgerValidationError("correction amount cannot be null")
        target_amount = amount_for_currency(
            session, payload.amount, target_currency, positive=True
        )
    else:
        target_amount = Decimal(transaction.amount)
    if "category_id" in fields and payload.category_id is None:
        raise LedgerValidationError("correction category_id cannot be null")
    target_event_at = (
        require_aware_timestamp(payload.event_at)
        if "event_at" in fields and payload.event_at is not None
        else transaction.event_at
    )
    target_category_id = payload.category_id if "category_id" in fields else transaction.category_id
    assert target_category_id is not None
    target_category = _get_category(session, plan_id, target_category_id)
    if target_category.status != "active":
        raise ArchivedResource("archived Categories reject correction destinations")
    target_merchant = payload.merchant if "merchant" in fields else transaction.merchant
    target_memo = payload.memo if "memo" in fields else transaction.memo
    target_photo = (
        payload.photo_reference
        if "photo_reference" in fields
        else transaction.photo_reference
    )
    target_location = payload.location if "location" in fields else transaction.location
    target_tags = (
        _validate_tag_ids(session, plan_id, payload.tags or [])
        if "tags" in fields
        else before_tags
    )
    target_source_metadata = (
        payload.source_metadata
        if "source_metadata" in fields and payload.source_metadata is not None
        else transaction.source_metadata
    )
    target_provenance = (
        payload.provenance
        if "provenance" in fields and payload.provenance is not None
        else transaction.provenance
    )
    canonical = {
        "plan_id": plan_id,
        "transaction_id": transaction_id,
        "amount": target_amount,
        "account_id": target_account_id,
        "currency_code": target_currency,
        "category_id": target_category.id,
        "event_at": target_event_at,
        "merchant": target_merchant,
        "memo": target_memo,
        "photo_reference": target_photo,
        "location": target_location,
        "tags": sorted(target_tags),
        "source_metadata": target_source_metadata,
        "provenance": target_provenance,
    }
    request_fingerprint = fingerprint(canonical)
    after = _snapshot_from_values(
        session,
        transaction=transaction,
        account_id=target_account_id,
        amount=target_amount,
        currency_code=target_currency,
        event_at=target_event_at,
        category_id=target_category.id,
        merchant=target_merchant,
        memo=target_memo,
        photo_reference=target_photo,
        location=target_location,
        tags=target_tags,
        source_metadata=target_source_metadata,
        provenance=target_provenance,
    )
    inserted_id = session.scalar(
        insert(TransactionCorrection)
        .values(
            id=correction_id,
            plan_id=plan_id,
            transaction_id=transaction_id,
            correction_sequence=correction_sequence,
            before_snapshot=before,
            after_snapshot=after,
            provenance=target_provenance,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing(index_elements=(TransactionCorrection.id,))
        .returning(TransactionCorrection.id)
    )
    if inserted_id is None:
        existing_correction = session.scalar(
            select(TransactionCorrection)
            .where(TransactionCorrection.id == correction_id)
            .execution_options(populate_existing=True)
        )
        if existing_correction is None:
            raise RuntimeError("correction creation result could not be loaded")
        if existing_correction.transaction_id != transaction_id:
            raise CreationConflict("Correction UUID belongs to another Transaction")
        if _correction_payload_matches(
            session, payload, existing_correction.after_snapshot
        ):
            return CreationResult(existing_correction, False)
        raise CreationConflict("Correction UUID has a different creation payload")

    compensation = PostedAccountMovement(
        id=uuid4(),
        plan_id=plan_id,
        account_id=old_movement.account_id,
        transaction_id=transaction_id,
        correction_id=correction_id,
        currency_code=old_movement.currency_code,
        signed_amount=-Decimal(old_movement.signed_amount),
        transaction_type=old_movement.transaction_type,
        effective_at=old_movement.effective_at,
        category_id=old_movement.category_id,
        merchant=old_movement.merchant,
        memo=old_movement.memo,
        photo_reference=old_movement.photo_reference,
        location=old_movement.location,
        source=old_movement.source,
        source_metadata=old_movement.source_metadata,
        provenance=old_movement.provenance,
        movement_kind="compensation",
        correction_sequence=correction_sequence,
        posted_at=utc_now(),
    )
    new_signed_amount = target_amount if transaction.type == "income" else -target_amount
    replacement = PostedAccountMovement(
        id=uuid4(),
        plan_id=plan_id,
        account_id=target_account_id,
        transaction_id=transaction_id,
        correction_id=correction_id,
        currency_code=target_currency,
        signed_amount=new_signed_amount,
        transaction_type=transaction.type,
        effective_at=target_event_at,
        category_id=target_category.id,
        merchant=target_merchant,
        memo=target_memo,
        photo_reference=target_photo,
        location=target_location,
        source=transaction.source,
        source_metadata=target_source_metadata,
        provenance=target_provenance,
        movement_kind="replacement",
        correction_sequence=correction_sequence,
        posted_at=utc_now(),
    )
    session.add_all([compensation, replacement])
    transaction.account_id = target_account_id
    transaction.amount = target_amount
    transaction.currency_code = target_currency
    transaction.event_at = target_event_at
    transaction.category_id = target_category.id
    transaction.merchant = target_merchant
    transaction.memo = target_memo
    transaction.photo_reference = target_photo
    transaction.location = target_location
    transaction.source_metadata = target_source_metadata
    transaction.provenance = target_provenance
    transaction.updated_at = utc_now()
    for tag_id in sorted(set(before_tags) - set(target_tags)):
        session.add(
            TransactionTag(
                id=uuid4(),
                plan_id=plan_id,
                transaction_id=transaction_id,
                tag_id=tag_id,
                action="detached",
                correction_id=correction_id,
            )
        )
    for tag_id in sorted(set(target_tags) - set(before_tags)):
        session.add(
            TransactionTag(
                id=uuid4(),
                plan_id=plan_id,
                transaction_id=transaction_id,
                tag_id=tag_id,
                action="attached",
                correction_id=correction_id,
            )
        )
    session.flush()
    correction = session.scalar(
        select(TransactionCorrection)
        .where(TransactionCorrection.id == correction_id)
        .execution_options(populate_existing=True)
    )
    if correction is None:
        raise RuntimeError("created correction could not be loaded")
    return CreationResult(correction, True)


def list_corrections(
    session: Session, plan_id: UUID, transaction_id: UUID
) -> list[TransactionCorrection]:
    get_transaction(session, plan_id, transaction_id)
    return list(
        session.scalars(
            select(TransactionCorrection)
            .where(
                TransactionCorrection.plan_id == plan_id,
                TransactionCorrection.transaction_id == transaction_id,
            )
            .order_by(
                TransactionCorrection.correction_sequence,
                TransactionCorrection.id,
            )
        )
    )


def create_assignment(
    session: Session,
    *,
    plan_id: UUID,
    assignment_id: UUID,
    payload: AssignmentCreate,
) -> CreationResult[MonthlyBudgetAssignment]:
    plan = _get_plan(session, plan_id)
    category = _require_active_category(session, plan_id, payload.category_id)
    month_key = payload.month_key or payload.month
    if month_key is None:
        raise LedgerValidationError("month is required")
    currency_code = payload.currency_code or plan.reporting_currency_code
    if currency_code != plan.reporting_currency_code:
        raise LedgerValidationError("assignment currency must match Plan budget currency")
    amount = amount_for_currency(session, payload.amount, currency_code, positive=False)
    request_fingerprint = fingerprint(
        {
            "plan_id": plan_id,
            "category_id": category.id,
            "month_key": month_key,
            "amount": amount,
            "currency_code": currency_code,
            "source": "manual",
            "provenance": payload.provenance,
        }
    )
    inserted_id = session.scalar(
        insert(MonthlyBudgetAssignment)
        .values(
            id=assignment_id,
            plan_id=plan_id,
            category_id=category.id,
            month_key=month_key,
            amount=amount,
            currency_code=currency_code,
            source="manual",
            provenance=payload.provenance,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing(index_elements=(MonthlyBudgetAssignment.id,))
        .returning(MonthlyBudgetAssignment.id)
    )
    assignment = session.scalar(
        select(MonthlyBudgetAssignment)
        .where(MonthlyBudgetAssignment.id == assignment_id)
        .execution_options(populate_existing=True)
    )
    if assignment is None:
        raise RuntimeError("assignment creation result could not be loaded")
    if assignment.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Assignment UUID has a different creation payload")
    if assignment.plan_id != plan_id:
        raise CreationConflict("Assignment UUID belongs to another Plan")
    return CreationResult(assignment, inserted_id is not None)


def assignment_response(
    session: Session, assignment: MonthlyBudgetAssignment
) -> AssignmentResponse:
    currency = require_currency(session, assignment.currency_code)
    return AssignmentResponse.model_validate(
        {
            "id": assignment.id,
            "plan_id": assignment.plan_id,
            "category_id": assignment.category_id,
            "month_key": assignment.month_key,
            "amount": fixed_amount(Decimal(assignment.amount), currency),
            "currency_code": assignment.currency_code,
            "source": assignment.source,
            "provenance": assignment.provenance,
            "created_at": assignment.created_at,
        }
    )


def _month_bounds(plan: Plan, month_key: str) -> tuple[datetime, datetime]:
    try:
        year = int(month_key[:4])
        month = int(month_key[5:])
    except (TypeError, ValueError) as exc:
        raise LedgerValidationError("month must use YYYY-MM") from exc
    if len(month_key) != 7 or month_key[4] != "-" or month not in range(1, 13):
        raise LedgerValidationError("month must use YYYY-MM")
    zone = ZoneInfo(plan.budget_timezone)
    start = datetime(year, month, 1, tzinfo=zone)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        end = datetime(year, month + 1, 1, tzinfo=zone)
    return start, end


def _budget_movements(
    session: Session, plan: Plan, month_key: str
) -> list[PostedAccountMovement]:
    start, end = _month_bounds(plan, month_key)
    return list(
        session.scalars(
            select(PostedAccountMovement)
            .where(
                PostedAccountMovement.plan_id == plan.id,
                PostedAccountMovement.effective_at >= start,
                PostedAccountMovement.effective_at < end,
            )
            .order_by(PostedAccountMovement.effective_at, PostedAccountMovement.id)
        )
    )


def _assignment_total(
    session: Session, plan_id: UUID, month_key: str
) -> Decimal:
    result = session.scalar(
        select(func.coalesce(func.sum(MonthlyBudgetAssignment.amount), 0)).where(
            MonthlyBudgetAssignment.plan_id == plan_id,
            MonthlyBudgetAssignment.month_key == month_key,
        )
    )
    return Decimal(result or 0)


def _unconverted_summary(
    session: Session,
    plan: Plan,
    movements: Iterable[PostedAccountMovement],
    *,
    category_id: UUID | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for movement in movements:
        if movement.transaction_type not in {"income", "expense"}:
            continue
        if movement.currency_code == plan.reporting_currency_code:
            continue
        if category_id is not None and movement.category_id != category_id:
            continue
        if category_id is not None and movement.transaction_type != "expense":
            continue
        entry = grouped.setdefault(
            movement.currency_code,
            {
                "currency": movement.currency_code,
                "income": Decimal(0),
                "expense": Decimal(0),
                "amount": Decimal(0),
                "movement_ids": [],
                "transaction_ids": [],
            },
        )
        signed = Decimal(movement.signed_amount)
        entry["amount"] += signed
        if movement.transaction_type == "income":
            entry["income"] += signed
        elif movement.transaction_type == "expense":
            entry["expense"] += signed
        entry["movement_ids"].append(movement.id)
        if movement.transaction_id not in entry["transaction_ids"]:
            entry["transaction_ids"].append(movement.transaction_id)
    result: list[dict[str, Any]] = []
    for currency_code, entry in sorted(grouped.items()):
        currency = require_currency(session, currency_code)
        result.append(
            {
                "currency": currency_code,
                "income": fixed_amount(entry["income"], currency),
                "expense": fixed_amount(entry["expense"], currency),
                "amount": fixed_amount(entry["amount"], currency),
                "movement_ids": entry["movement_ids"],
                "transaction_ids": entry["transaction_ids"],
            }
        )
    return result


def _previous_month(month_key: str) -> str:
    year, month = int(month_key[:4]), int(month_key[5:])
    return f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"


def _category_first_month(
    session: Session, plan: Plan, category_id: UUID, through_month: str
) -> str | None:
    assigned = session.scalars(
        select(MonthlyBudgetAssignment.month_key).where(
            MonthlyBudgetAssignment.plan_id == plan.id,
            MonthlyBudgetAssignment.category_id == category_id,
            MonthlyBudgetAssignment.month_key <= through_month,
        )
    )
    months = list(assigned)
    _, end = _month_bounds(plan, through_month)
    movements = session.scalars(
        select(PostedAccountMovement.effective_at).where(
            PostedAccountMovement.plan_id == plan.id,
            PostedAccountMovement.category_id == category_id,
            PostedAccountMovement.currency_code == plan.reporting_currency_code,
            PostedAccountMovement.transaction_type == "expense",
            PostedAccountMovement.effective_at < end,
        )
    )
    zone = ZoneInfo(plan.budget_timezone)
    months.extend(item.astimezone(zone).strftime("%Y-%m") for item in movements)
    return min(months) if months else None


def _category_budget_values(
    session: Session, plan: Plan, category: Category, month_key: str
) -> dict[str, Decimal]:
    first_month = _category_first_month(session, plan, category.id, month_key)
    if first_month is None or month_key < first_month:
        return {"rollover": Decimal(0), "assigned": Decimal(0), "activity": Decimal(0),
                "available": Decimal(0), "cash_overspending": Decimal(0),
                "credit_card_overspending": Decimal(0)}
    account_types: dict[UUID, str] = {
        account_id: account_type
        for account_id, account_type in session.execute(
            select(Account.id, Account.account_type).where(Account.plan_id == plan.id)
        ).tuples()
    }
    values = {"rollover": Decimal(0), "assigned": Decimal(0), "activity": Decimal(0),
              "available": Decimal(0), "cash_overspending": Decimal(0),
              "credit_card_overspending": Decimal(0)}
    current = first_month
    prior_available = Decimal(0)
    while current <= month_key:
        assigned = Decimal(session.scalar(
            select(func.coalesce(func.sum(MonthlyBudgetAssignment.amount), 0)).where(
                MonthlyBudgetAssignment.plan_id == plan.id,
                MonthlyBudgetAssignment.category_id == category.id,
                MonthlyBudgetAssignment.month_key == current,
            )
        ) or 0)
        movements = [
            item for item in _budget_movements(session, plan, current)
            if item.category_id == category.id
            and item.currency_code == plan.reporting_currency_code
            and item.transaction_type == "expense"
        ]
        replacement_sequences = {
            transaction_id: sequence
            for transaction_id, sequence in session.execute(
                select(
                    PostedAccountMovement.transaction_id,
                    func.max(PostedAccountMovement.correction_sequence),
                )
                .where(
                    PostedAccountMovement.plan_id == plan.id,
                    PostedAccountMovement.transaction_id.in_(
                        [item.transaction_id for item in movements]
                    ),
                    PostedAccountMovement.movement_kind == "replacement",
                )
                .group_by(PostedAccountMovement.transaction_id)
            ).tuples()
        } if movements else {}
        movements = [
            item for item in movements
            if (
                item.movement_kind == "original"
                and item.transaction_id not in replacement_sequences
            )
            or (
                item.movement_kind == "replacement"
                and item.correction_sequence == replacement_sequences[item.transaction_id]
            )
        ]
        # Effective time and transaction UUID are the financing order. Movement
        # UUID only disambiguates append-only correction rows for one transaction.
        movements.sort(key=lambda item: (item.effective_at, item.transaction_id, item.id))
        rollover = max(prior_available, Decimal(0))
        funded = rollover + assigned
        activity = Decimal(0)
        cash_excess = Decimal(0)
        card_excess = Decimal(0)
        for movement in movements:
            amount = -Decimal(movement.signed_amount)
            activity -= amount
            financed = min(max(funded, Decimal(0)), amount)
            excess = amount - financed
            funded -= amount
            if excess > 0:
                if account_types.get(movement.account_id) == "Credit Card":
                    card_excess += excess
                else:
                    cash_excess += excess
        available = max(funded, Decimal(0))
        values = {"rollover": rollover, "assigned": assigned, "activity": activity,
                  "available": available, "cash_overspending": cash_excess,
                  "credit_card_overspending": card_excess}
        prior_available = available
        current = _next_month(current)
    return values


def _next_month(month_key: str) -> str:
    year, month = int(month_key[:4]), int(month_key[5:])
    return f"{year + 1:04d}-01" if month == 12 else f"{year:04d}-{month + 1:02d}"


def _goal_response(category: Category, values: dict[str, Decimal], currency: Currency, month_key: str) -> dict[str, Any] | None:
    if category.goal_type is None or category.goal_target is None:
        return None
    target = Decimal(category.goal_target)
    assigned, available = values["assigned"], values["available"]
    if category.goal_type == "target_balance":
        completed = available >= target
        return {"type": "target_balance", "target": fixed_amount(target, currency),
                "required_contribution": fixed_amount(max(target - available, Decimal(0)), currency),
                "status": "completed" if completed else "underfunded"}
    if category.goal_type == "monthly_funding":
        funded = assigned >= target
        return {"type": "monthly_funding", "target": fixed_amount(target, currency),
                "required_contribution": fixed_amount(target, currency),
                "status": "funded" if funded else "underfunded"}
    assert category.goal_due_month is not None
    shortfall = max(target - available, Decimal(0))
    if category.goal_due_month <= month_key:
        required = shortfall
    else:
        year, month = int(month_key[:4]), int(month_key[5:])
        due_year, due_month = int(category.goal_due_month[:4]), int(category.goal_due_month[5:])
        remaining = (due_year - year) * 12 + due_month - month + 1
        required = shortfall / Decimal(remaining)
    required = required.quantize(Decimal(1).scaleb(-currency.decimal_places))
    status = "completed" if shortfall == 0 else ("on_track" if assigned >= required else "underfunded")
    return {"type": "due_date", "target": fixed_amount(target, currency),
            "due_month": category.goal_due_month,
            "required_contribution": fixed_amount(required, currency), "status": status}


def category_envelope(
    session: Session, *, plan_id: UUID, month_key: str, category_id: UUID
) -> dict[str, Any]:
    plan = _get_plan(session, plan_id)
    category = _get_category(session, plan_id, category_id)
    currency = require_currency(session, plan.reporting_currency_code)
    movements = _budget_movements(session, plan, month_key)
    values = _category_budget_values(session, plan, category, month_key)
    assigned, activity, available = values["assigned"], values["activity"], values["available"]
    unconverted = _unconverted_summary(
        session, plan, movements, category_id=category_id
    )
    return {
        "plan_id": plan_id,
        "category_id": category.id,
        "month": month_key,
        "currency": currency.code,
        "assigned": fixed_amount(assigned, currency),
        "activity": fixed_amount(activity, currency),
        "available": fixed_amount(available, currency),
        "assigned_money": {"amount": fixed_amount(assigned, currency), "currency": currency.code},
        "activity_money": {"amount": fixed_amount(activity, currency), "currency": currency.code},
        "available_money": {"amount": fixed_amount(available, currency), "currency": currency.code},
        "rollover": fixed_amount(values["rollover"], currency),
        "cash_overspending": fixed_amount(values["cash_overspending"], currency),
        "credit_card_overspending": fixed_amount(values["credit_card_overspending"], currency),
        "goal": _goal_response(category, values, currency, month_key),
        "unconverted_by_currency": unconverted,
    }


def monthly_summary(
    session: Session, *, plan_id: UUID, month_key: str
) -> dict[str, Any]:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    movements = _budget_movements(session, plan, month_key)
    income = sum(
        (
            Decimal(movement.signed_amount)
            for movement in movements
            if movement.currency_code == plan.reporting_currency_code
            and movement.transaction_type == "income"
        ),
        Decimal(0),
    )
    assigned_total = _assignment_total(session, plan_id, month_key)
    activity_total = sum(
        (
            Decimal(movement.signed_amount)
            for movement in movements
            if movement.currency_code == plan.reporting_currency_code
            and movement.transaction_type == "expense"
        ),
        Decimal(0),
    )
    categories = list_categories(session, plan_id)
    envelopes = [
        category_envelope(
            session, plan_id=plan_id, month_key=month_key, category_id=category.id
        )
        for category in categories
    ]
    previous_values = [
        _category_budget_values(session, plan, category, _previous_month(month_key))
        for category in categories
    ]
    cash_overspending = sum(
        (item["cash_overspending"] for item in previous_values), Decimal(0)
    )
    ready = income - assigned_total - cash_overspending
    available_total = sum(
        (Decimal(envelope["available"]) for envelope in envelopes), Decimal(0)
    )
    return {
        "plan_id": plan_id,
        "month": month_key,
        "currency": currency.code,
        "ready_to_assign": fixed_amount(ready, currency),
        "ready_to_assign_money": {"amount": fixed_amount(ready, currency), "currency": currency.code},
        "assigned_total": fixed_amount(assigned_total, currency),
        "activity_total": fixed_amount(activity_total, currency),
        "available_total": fixed_amount(available_total, currency),
        "unconverted_by_currency": _unconverted_summary(session, plan, movements),
        "categories": envelopes,
    }
