from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.accounts.models import Account, Plan
from app.accounts.service import (
    CreationConflict,
    ResourceNotFound,
)
from app.ledger.models import Category, PostedAccountMovement, Transaction
from app.ledger.service import (
    ArchivedResource,
    LedgerValidationError,
    fingerprint,
    utc_now,
)
from app.statements.ganadero_csv import parse_banco_ganadero_csv
from app.statements.models import StatementImport, StatementRow
from app.statements.schemas import (
    StatementCommitRequest,
    StatementDryRunRequest,
    StatementDryRunResponse,
    StatementRowResponse,
)


def _get_account(session: Session, plan_id: UUID, account_id: UUID) -> Account:
    account = session.scalar(
        select(Account).where(Account.plan_id == plan_id, Account.id == account_id)
    )
    if account is None:
        raise ResourceNotFound("Account not found")
    if account.status != "active":
        raise ArchivedResource("archived Accounts reject statement operations")
    return account


def _get_pending_category(session: Session, plan_id: UUID) -> Category:
    category = session.scalar(
        select(Category).where(
            Category.plan_id == plan_id,
            Category.is_pending.is_(True),
        )
    )
    if category is None:
        raise RuntimeError("Pending category not found for plan")
    return category


def dry_run_statement(
    session: Session,
    plan_id: UUID,
    payload: StatementDryRunRequest,
) -> StatementDryRunResponse:
    account = _get_account(session, plan_id, payload.account_id)
    parsed = parse_banco_ganadero_csv(payload.csv_content)

    # Check for existing compound identities in transactions
    existing_transactions = session.scalars(
        select(Transaction).where(
            Transaction.plan_id == plan_id,
            Transaction.account_id == account.id,
        )
    ).all()

    existing_identities = {
        t.source_metadata.get("compound_identity"): t.id
        for t in existing_transactions
        if t.source_metadata and "compound_identity" in t.source_metadata
    }

    row_responses: list[StatementRowResponse] = []
    for r in parsed.rows:
        matched_txn_id = existing_identities.get(r.compound_identity)
        match_status = "duplicate" if matched_txn_id else "unmatched"
        row_responses.append(
            StatementRowResponse(
                id=None,
                source_row_index=r.source_row_index,
                event_at=r.event_at,
                transaction_number=r.transaction_number,
                channel=r.channel,
                description=r.description,
                type=r.type,
                amount=format(r.amount, "f"),
                signed_amount=format(r.signed_amount, "f"),
                running_balance=format(r.running_balance, "f"),
                compound_identity=r.compound_identity,
                transaction_id=matched_txn_id,
                match_status=match_status,
                card_suffix=r.card_suffix,
                metadata=r.metadata,
            )
        )

    warnings = list(parsed.warnings)
    if parsed.currency_code != account.currency_code:
        warnings.append(
            f"Statement currency {parsed.currency_code} does not match account currency {account.currency_code}"
        )

    return StatementDryRunResponse(
        account_id=account.id,
        currency_code=account.currency_code,
        opening_balance=format(parsed.opening_balance, "f") if parsed.opening_balance is not None else None,
        closing_balance=format(parsed.closing_balance, "f") if parsed.closing_balance is not None else None,
        current_balance=format(parsed.current_balance, "f") if parsed.current_balance is not None else None,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        exported_at=parsed.exported_at,
        debit_count=parsed.debit_count,
        credit_count=parsed.credit_count,
        debit_sum=format(parsed.debit_sum, "f"),
        credit_sum=format(parsed.credit_sum, "f"),
        warnings=warnings,
        rows=row_responses,
    )


def commit_statement(
    session: Session,
    plan_id: UUID,
    import_id: UUID,
    payload: StatementCommitRequest,
) -> StatementImport:
    account = _get_account(session, plan_id, payload.account_id)

    canonical_payload = {
        "plan_id": str(plan_id),
        "account_id": str(payload.account_id),
        "csv_content": payload.csv_content,
        "filename": payload.filename,
    }
    request_fingerprint = fingerprint(canonical_payload)

    # Check for existing import with this ID (Idempotency)
    existing_import = session.scalar(
        select(StatementImport)
        .options(selectinload(StatementImport.rows))
        .where(StatementImport.id == import_id)
    )
    if existing_import is not None:
        if existing_import.plan_id != plan_id:
            raise CreationConflict("Statement import belongs to another Plan")
        if existing_import.creation_fingerprint != request_fingerprint:
            raise CreationConflict("Statement import UUID has a different creation payload")
        return existing_import

    parsed = parse_banco_ganadero_csv(payload.csv_content)
    pending_category = _get_pending_category(session, plan_id)

    # Check existing transactions for deduplication
    existing_transactions = session.scalars(
        select(Transaction).where(
            Transaction.plan_id == plan_id,
            Transaction.account_id == account.id,
        )
    ).all()
    existing_identities = {
        t.source_metadata.get("compound_identity"): t
        for t in existing_transactions
        if t.source_metadata and "compound_identity" in t.source_metadata
    }

    statement_import = StatementImport(
        id=import_id,
        plan_id=plan_id,
        account_id=account.id,
        filename=payload.filename,
        source_format="banco_ganadero_csv",
        status="committed",
        opening_balance=parsed.opening_balance,
        closing_balance=parsed.closing_balance,
        current_balance=parsed.current_balance,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        exported_at=parsed.exported_at,
        debit_count=parsed.debit_count,
        credit_count=parsed.credit_count,
        debit_sum=parsed.debit_sum,
        credit_sum=parsed.credit_sum,
        currency_code=account.currency_code,
        warnings=parsed.warnings,
        import_metadata=parsed.metadata,
        creation_fingerprint=request_fingerprint,
    )
    session.add(statement_import)

    now = utc_now()
    for r in parsed.rows:
        existing_txn = existing_identities.get(r.compound_identity)
        if existing_txn is not None:
            txn_id = existing_txn.id
            match_status = "duplicate"
        else:
            txn_id = uuid4()
            txn_type = "expense" if r.type == "debit" else "income"
            source_metadata = {
                "source_format": "banco_ganadero_csv",
                "transaction_number": r.transaction_number,
                "channel": r.channel,
                "compound_identity": r.compound_identity,
                "card_suffix": r.card_suffix,
                "raw_description": r.description,
            }
            if r.metadata.get("card_country"):
                source_metadata["card_country"] = r.metadata["card_country"]

            provenance = {
                "import_id": str(import_id),
                "source_row_index": r.source_row_index,
                "compound_identity": r.compound_identity,
            }
            txn_canonical = {
                "plan_id": str(plan_id),
                "account_id": str(account.id),
                "type": txn_type,
                "amount": format(r.amount, "f"),
                "currency_code": account.currency_code,
                "event_at": r.event_at.isoformat(),
                "category_id": str(pending_category.id),
                "merchant": None,
                "memo": r.description,
                "source": "statement",
                "source_metadata": source_metadata,
                "provenance": provenance,
            }
            txn_fingerprint = fingerprint(txn_canonical)

            transaction = Transaction(
                id=txn_id,
                plan_id=plan_id,
                account_id=account.id,
                type=txn_type,
                amount=r.amount,
                currency_code=account.currency_code,
                event_at=r.event_at,
                category_id=pending_category.id,
                merchant=None,
                memo=r.description,
                source="statement",
                source_metadata=source_metadata,
                provenance=provenance,
                creation_fingerprint=txn_fingerprint,
                created_at=now,
                updated_at=now,
            )
            session.add(transaction)
            session.flush()

            movement = PostedAccountMovement(
                id=uuid4(),
                plan_id=plan_id,
                account_id=account.id,
                transaction_id=txn_id,
                currency_code=account.currency_code,
                signed_amount=r.signed_amount,
                transaction_type=txn_type,
                effective_at=r.event_at,
                category_id=pending_category.id,
                merchant=None,
                memo=r.description,
                source="statement",
                source_metadata=source_metadata,
                provenance=provenance,
                movement_kind="original",
                correction_sequence=0,
                posted_at=now,
            )
            session.add(movement)
            existing_identities[r.compound_identity] = transaction
            match_status = "created"

        statement_row = StatementRow(
            id=uuid4(),
            plan_id=plan_id,
            import_id=import_id,
            account_id=account.id,
            source_row_index=r.source_row_index,
            event_at=r.event_at,
            transaction_number=r.transaction_number,
            channel=r.channel,
            description=r.description,
            type=r.type,
            amount=r.amount,
            signed_amount=r.signed_amount,
            running_balance=r.running_balance,
            compound_identity=r.compound_identity,
            transaction_id=txn_id,
            match_status=match_status,
            card_suffix=r.card_suffix,
            row_metadata=r.metadata,
            created_at=now,
        )
        session.add(statement_row)

    session.commit()

    loaded_import = session.scalar(
        select(StatementImport)
        .options(selectinload(StatementImport.rows))
        .where(StatementImport.id == import_id)
    )
    if loaded_import is None:
        raise RuntimeError("Failed to load committed statement import")
    return loaded_import


def list_statement_imports(
    session: Session,
    plan_id: UUID,
    account_id: UUID | None = None,
) -> list[StatementImport]:
    query = select(StatementImport).where(StatementImport.plan_id == plan_id)
    if account_id is not None:
        query = query.where(StatementImport.account_id == account_id)
    query = query.order_by(StatementImport.created_at.desc())
    return list(session.scalars(query).all())


def get_statement_import(
    session: Session,
    plan_id: UUID,
    import_id: UUID,
) -> StatementImport:
    statement_import = session.scalar(
        select(StatementImport)
        .options(selectinload(StatementImport.rows))
        .where(
            StatementImport.plan_id == plan_id,
            StatementImport.id == import_id,
        )
    )
    if statement_import is None:
        raise ResourceNotFound("Statement import not found")
    return statement_import
