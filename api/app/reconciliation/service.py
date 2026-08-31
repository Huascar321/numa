from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.accounts.models import Account, Currency
from app.accounts.service import CreationConflict, ResourceNotFound, require_currency
from app.ledger.models import PostedAccountMovement, Transaction
from app.ledger.service import (
    LedgerValidationError,
    fingerprint,
    lock_movement_accounts,
    parse_exact_decimal,
    utc_now,
)
from app.reconciliation.models import ReconciliationSession
from app.reconciliation.schemas import (
    ReconciliationConfirmRequest,
    ReconciliationPreviewRequest,
    STATEMENT_BALANCE_PATTERN,
)


Policy = Literal["block", "warn"]
LEDGER_AMOUNT_MAX = Decimal("99999999999999999999.999999999999999999")


class ReconciliationPolicyError(Exception):
    """Confirmation is disallowed by the configured reconciliation policy."""


@dataclass(frozen=True)
class Comparison:
    id: UUID
    plan_id: UUID
    account_id: UUID
    currency: Currency
    statement_balance: Decimal
    statement_at: datetime
    derived_balance: Decimal
    discrepancy: Decimal
    policy: Policy
    tolerance: Decimal

    @property
    def requires_warning_acceptance(self) -> bool:
        return self.policy == "warn" and abs(self.discrepancy) > self.tolerance

    @property
    def blocked(self) -> bool:
        return self.policy == "block" and abs(self.discrepancy) > self.tolerance


@dataclass(frozen=True)
class ConfirmationResult:
    resource: ReconciliationSession
    created: bool


def _account(session: Session, plan_id: UUID, account_id: UUID) -> Account:
    account = session.scalar(
        select(Account).where(Account.plan_id == plan_id, Account.id == account_id)
    )
    if account is None:
        raise ResourceNotFound("Account not found")
    return account


def _amount_at_currency_scale(value: str, currency: Currency) -> Decimal:
    if len(value) > 40 or re.fullmatch(STATEMENT_BALANCE_PATTERN, value) is None:
        raise LedgerValidationError(
            "statement_balance must be a plain NUMERIC(38,18) decimal string"
        )
    amount = parse_exact_decimal(value, field_name="statement_balance")
    quantum = Decimal(1).scaleb(-currency.decimal_places)
    integer_digits = max(amount.adjusted() + 1, 1) if amount else 1
    precision = max(
        len(amount.as_tuple().digits),
        integer_digits + currency.decimal_places,
        currency.decimal_places + 1,
    )
    try:
        with localcontext() as context:
            context.prec = precision
            quantized = amount.quantize(quantum)
    except InvalidOperation as exc:
        raise LedgerValidationError("statement_balance has an invalid scale") from exc
    if quantized != amount:
        raise LedgerValidationError(
            "statement_balance has more decimal places than the Account currency"
        )
    return quantized


def format_at_scale(amount: Decimal, currency: Currency) -> str:
    quantum = Decimal(1).scaleb(-currency.decimal_places)
    integer_digits = max(amount.adjusted() + 1, 1) if amount else 1
    precision = max(
        len(amount.as_tuple().digits),
        integer_digits + currency.decimal_places,
        currency.decimal_places + 1,
    )
    with localcontext() as context:
        context.prec = precision
        return format(amount.quantize(quantum), "f")


def _tolerance(currency: Currency, tolerance_atoms: int) -> Decimal:
    return Decimal(tolerance_atoms).scaleb(-currency.decimal_places)


def _derived_balance(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
    currency_code: str,
    statement_at: datetime,
) -> Decimal:
    value = session.scalar(
        select(func.coalesce(func.sum(PostedAccountMovement.signed_amount), 0)).where(
            PostedAccountMovement.plan_id == plan_id,
            PostedAccountMovement.account_id == account_id,
            PostedAccountMovement.currency_code == currency_code,
            PostedAccountMovement.effective_at <= statement_at,
        )
    )
    return Decimal(value or 0)


def _statement_facts(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
    payload: ReconciliationPreviewRequest,
    account: Account | None = None,
) -> tuple[Account, Currency, Decimal, datetime]:
    account = account or _account(session, plan_id, account_id)
    if payload.currency_code != account.currency_code:
        raise LedgerValidationError("statement currency must match Account currency")
    currency = require_currency(session, account.currency_code)
    statement_balance = _amount_at_currency_scale(payload.statement_balance, currency)
    statement_at = payload.statement_at.astimezone(timezone.utc)
    return account, currency, statement_balance, statement_at


def _comparison_from_facts(
    session: Session,
    *,
    plan_id: UUID,
    reconciliation_id: UUID,
    account: Account,
    currency: Currency,
    statement_balance: Decimal,
    statement_at: datetime,
    policy: Policy,
    tolerance_atoms: int,
) -> Comparison:
    derived = _derived_balance(
        session,
        plan_id=plan_id,
        account_id=account.id,
        currency_code=currency.code,
        statement_at=statement_at,
    )
    tolerance = _tolerance(currency, tolerance_atoms)
    return Comparison(
        id=reconciliation_id,
        plan_id=plan_id,
        account_id=account.id,
        currency=currency,
        statement_balance=statement_balance,
        statement_at=statement_at,
        derived_balance=derived,
        discrepancy=statement_balance - derived,
        policy=policy,
        tolerance=tolerance,
    )


def preview_reconciliation(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
    reconciliation_id: UUID,
    payload: ReconciliationPreviewRequest,
    policy: Policy,
    tolerance_atoms: int,
) -> Comparison:
    account, currency, statement_balance, statement_at = _statement_facts(
        session, plan_id=plan_id, account_id=account_id, payload=payload
    )
    return _comparison_from_facts(
        session,
        plan_id=plan_id,
        reconciliation_id=reconciliation_id,
        account=account,
        currency=currency,
        statement_balance=statement_balance,
        statement_at=statement_at,
        policy=policy,
        tolerance_atoms=tolerance_atoms,
    )


def _request_fingerprint(
    *,
    plan_id: UUID,
    account_id: UUID,
    currency: Currency,
    statement_balance: Decimal,
    statement_at: datetime,
    warning_accepted: bool,
) -> str:
    return fingerprint(
        {
            "plan_id": plan_id,
            "account_id": account_id,
            "currency_code": currency.code,
            "statement_balance": format_at_scale(statement_balance, currency),
            "statement_at": statement_at.astimezone(timezone.utc),
            "warning_accepted": warning_accepted,
        }
    )


def _existing_session(
    session: Session, plan_id: UUID, account_id: UUID, reconciliation_id: UUID
) -> ReconciliationSession | None:
    return session.scalar(
        select(ReconciliationSession).where(
            ReconciliationSession.plan_id == plan_id,
            ReconciliationSession.account_id == account_id,
            ReconciliationSession.id == reconciliation_id,
        )
    )


def confirm_reconciliation(
    session: Session,
    *,
    plan_id: UUID,
    account_id: UUID,
    reconciliation_id: UUID,
    payload: ReconciliationConfirmRequest,
    policy: Policy,
    tolerance_atoms: int,
) -> ConfirmationResult:
    locked_account = lock_movement_accounts(session, plan_id, [account_id])[account_id]
    account, currency, statement_balance, statement_at = _statement_facts(
        session,
        plan_id=plan_id,
        account_id=account_id,
        payload=payload,
        account=locked_account,
    )
    request_fingerprint = _request_fingerprint(
        plan_id=plan_id,
        account_id=account.id,
        currency=currency,
        statement_balance=statement_balance,
        statement_at=statement_at,
        warning_accepted=payload.warning_accepted,
    )
    existing = _existing_session(session, plan_id, account.id, reconciliation_id)
    if existing is not None:
        if existing.creation_fingerprint != request_fingerprint:
            raise CreationConflict(
                "Reconciliation UUID has a different confirmation payload"
            )
        return ConfirmationResult(existing, False)

    comparison = _comparison_from_facts(
        session,
        plan_id=plan_id,
        reconciliation_id=reconciliation_id,
        account=account,
        currency=currency,
        statement_balance=statement_balance,
        statement_at=statement_at,
        policy=policy,
        tolerance_atoms=tolerance_atoms,
    )
    if comparison.blocked:
        raise ReconciliationPolicyError(
            "reconciliation discrepancy exceeds the configured block tolerance"
        )
    if comparison.requires_warning_acceptance and not payload.warning_accepted:
        raise ReconciliationPolicyError(
            "warning acceptance is required above the reconciliation tolerance"
        )
    if comparison.discrepancy != 0 and account.status != "active":
        raise ReconciliationPolicyError(
            "archived Accounts cannot receive reconciliation adjustments"
        )
    if comparison.discrepancy != 0 and abs(comparison.discrepancy) > LEDGER_AMOUNT_MAX:
        raise LedgerValidationError(
            "reconciliation adjustment is outside the ledger amount domain"
        )

    inserted_id = session.scalar(
        insert(ReconciliationSession)
        .values(
            id=reconciliation_id,
            plan_id=plan_id,
            account_id=account.id,
            currency_code=currency.code,
            statement_balance=comparison.statement_balance,
            statement_at=comparison.statement_at,
            derived_balance=comparison.derived_balance,
            discrepancy=comparison.discrepancy,
            policy=comparison.policy,
            tolerance=comparison.tolerance,
            warning_accepted=payload.warning_accepted,
            creation_fingerprint=request_fingerprint,
        )
        .on_conflict_do_nothing(index_elements=(ReconciliationSession.id,))
        .returning(ReconciliationSession.id)
    )
    persisted = _existing_session(session, plan_id, account.id, reconciliation_id)
    if persisted is None:
        raise ResourceNotFound("Reconciliation session not found")
    if persisted.creation_fingerprint != request_fingerprint:
        raise CreationConflict("Reconciliation UUID has a different confirmation payload")
    if inserted_id is None:
        return ConfirmationResult(persisted, False)

    if comparison.discrepancy != 0:
        transaction_id = uuid4()
        movement_id = uuid4()
        amount = abs(comparison.discrepancy)
        provenance = {"reconciliation_session_id": str(reconciliation_id)}
        session.add(
            Transaction(
                id=transaction_id,
                plan_id=plan_id,
                account_id=account.id,
                type="reconciliation_adjustment",
                amount=amount,
                currency_code=currency.code,
                event_at=comparison.statement_at,
                category_id=None,
                source="reconciliation",
                source_metadata={},
                provenance=provenance,
                creation_fingerprint=fingerprint(
                    {"reconciliation_session_id": reconciliation_id, "kind": "adjustment"}
                ),
                reconciliation_session_id=reconciliation_id,
            )
        )
        session.flush()
        session.add(
            PostedAccountMovement(
                id=movement_id,
                plan_id=plan_id,
                account_id=account.id,
                transaction_id=transaction_id,
                correction_id=None,
                correction_sequence=0,
                currency_code=currency.code,
                signed_amount=comparison.discrepancy,
                transaction_type="reconciliation_adjustment",
                effective_at=comparison.statement_at,
                category_id=None,
                source="reconciliation",
                source_metadata={},
                provenance=provenance,
                movement_kind="original",
                posted_at=utc_now(),
                reconciliation_session_id=reconciliation_id,
            )
        )
    session.flush()
    return ConfirmationResult(persisted, True)


def list_reconciliations(
    session: Session, *, plan_id: UUID, account_id: UUID
) -> list[ReconciliationSession]:
    _account(session, plan_id, account_id)
    return list(
        session.scalars(
            select(ReconciliationSession)
            .where(
                ReconciliationSession.plan_id == plan_id,
                ReconciliationSession.account_id == account_id,
            )
            .order_by(
                ReconciliationSession.confirmed_at.desc(),
                ReconciliationSession.id,
            )
        )
    )


def adjustment_ids(
    session: Session, reconciliation: ReconciliationSession
) -> tuple[UUID | None, UUID | None]:
    transaction = session.scalar(
        select(Transaction).where(
            Transaction.plan_id == reconciliation.plan_id,
            Transaction.reconciliation_session_id == reconciliation.id,
        )
    )
    movement = session.scalar(
        select(PostedAccountMovement).where(
            PostedAccountMovement.plan_id == reconciliation.plan_id,
            PostedAccountMovement.reconciliation_session_id == reconciliation.id,
        )
    )
    return (
        transaction.id if transaction is not None else None,
        movement.id if movement is not None else None,
    )
