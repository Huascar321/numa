from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Plan
from app.accounts.service import ResourceNotFound
from app.ledger.models import Category, PostedAccountMovement, Transaction
from app.ledger.service import _pending_category, fingerprint, utc_now
from app.matching.engine import evaluate_match_pair
from app.matching.models import TransactionMatch
from app.matching.schemas import (
    CandidateSummary,
    MatchEvaluationRequest,
    MatchEvaluationResponse,
    StatementRowSummary,
    TransactionMatchResponse,
    TransactionSummary,
)
from app.statements.models import StatementRow
from app.watchers.models import WatcherCandidate


def _require_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} does not exist.")
    return plan


def _build_candidate_summary(candidate: WatcherCandidate | None) -> CandidateSummary | None:
    if candidate is None:
        return None
    return CandidateSummary(
        id=candidate.id,
        candidate_type=candidate.candidate_type,
        reported_amount=format(candidate.reported_amount, "f"),
        reported_currency=candidate.reported_currency,
        settlement_amount=format(candidate.settlement_amount, "f") if candidate.settlement_amount is not None else None,
        settlement_currency=candidate.settlement_currency,
        merchant=candidate.merchant,
        subject=candidate.subject,
        glosa=candidate.glosa,
        account_suffix=candidate.account_suffix,
        direction=candidate.direction,
        event_at=candidate.event_at,
        notification_at=candidate.notification_at,
        status=candidate.status,
    )


def _build_statement_row_summary(row: StatementRow | None) -> StatementRowSummary | None:
    if row is None:
        return None
    return StatementRowSummary(
        id=row.id,
        import_id=row.import_id,
        account_id=row.account_id,
        source_row_index=row.source_row_index,
        event_at=row.event_at,
        transaction_number=row.transaction_number,
        channel=row.channel,
        description=row.description,
        type=row.type,
        amount=format(row.amount, "f"),
        signed_amount=format(row.signed_amount, "f"),
        match_status=row.match_status,
        card_suffix=row.card_suffix,
    )


def _build_transaction_summary(txn: Transaction | None) -> TransactionSummary | None:
    if txn is None:
        return None
    return TransactionSummary(
        id=txn.id,
        account_id=txn.account_id,
        type=txn.type,
        amount=format(txn.amount, "f"),
        currency_code=txn.currency_code,
        event_at=txn.event_at,
        category_id=txn.category_id,
        merchant=txn.merchant,
        memo=txn.memo,
        source=txn.source,
    )


def _build_match_response(
    session: Session, match: TransactionMatch
) -> TransactionMatchResponse:
    candidate = (
        session.get(WatcherCandidate, match.candidate_id)
        if match.candidate_id
        else None
    )
    statement_row = (
        session.get(StatementRow, match.statement_row_id)
        if match.statement_row_id
        else None
    )
    transaction = (
        session.get(Transaction, match.transaction_id)
        if match.transaction_id
        else None
    )

    return TransactionMatchResponse(
        id=match.id,
        plan_id=match.plan_id,
        candidate_id=match.candidate_id,
        statement_row_id=match.statement_row_id,
        transaction_id=match.transaction_id,
        classification=match.classification,
        status=match.status,
        confidence_score=format(match.confidence_score, ".4f"),
        signals=match.signals,
        provenance=match.provenance,
        created_at=match.created_at,
        updated_at=match.updated_at,
        candidate=_build_candidate_summary(candidate),
        statement_row=_build_statement_row_summary(statement_row),
        transaction=_build_transaction_summary(transaction),
    )


def evaluate_plan_matches(
    session: Session,
    plan_id: UUID,
    payload: MatchEvaluationRequest | None = None,
) -> MatchEvaluationResponse:
    _require_plan(session, plan_id)

    # 1. Fetch transactions
    transactions = list(
        session.scalars(
            select(Transaction).where(Transaction.plan_id == plan_id)
        ).all()
    )

    # 2. Fetch candidates to evaluate
    candidate_query = select(WatcherCandidate).where(
        WatcherCandidate.plan_id == plan_id
    )
    if payload and payload.candidate_id:
        candidate_query = candidate_query.where(
            WatcherCandidate.id == payload.candidate_id
        )
    else:
        # Default: evaluate unlinked / pending candidates
        candidate_query = candidate_query.where(
            WatcherCandidate.status.in_(["pending", "quarantined"])
        )
    candidates = list(session.scalars(candidate_query).all())

    # 3. Fetch statement rows to evaluate
    stmt_query = select(StatementRow).where(StatementRow.plan_id == plan_id)
    if payload and payload.statement_row_id:
        stmt_query = stmt_query.where(StatementRow.id == payload.statement_row_id)
    else:
        stmt_query = stmt_query.where(
            StatementRow.match_status.in_(["unmatched", "duplicate"])
        )
    statement_rows = list(session.scalars(stmt_query).all())

    evaluated_matches: list[TransactionMatch] = []
    now = utc_now()

    # Match Watcher Candidates against Transactions & Statement Rows
    for cand in candidates:
        best_eval: dict[str, Any] | None = None
        best_txn: Transaction | None = None
        best_score = Decimal("-1")

        for txn in transactions:
            eval_res = evaluate_match_pair(cand, txn)
            score = eval_res["confidence_score"]
            if score > best_score:
                best_score = score
                best_eval = eval_res
                best_txn = txn

        if best_eval and best_txn and best_eval["classification"] != "NEW_TRANSACTION":
            fingerprint_payload = {
                "plan_id": str(plan_id),
                "candidate_id": str(cand.id),
                "transaction_id": str(best_txn.id),
                "classification": best_eval["classification"],
            }
            fp = fingerprint(fingerprint_payload)

            existing_match = session.scalar(
                select(TransactionMatch).where(
                    TransactionMatch.plan_id == plan_id,
                    TransactionMatch.candidate_id == cand.id,
                    TransactionMatch.transaction_id == best_txn.id,
                )
            )

            if existing_match is None:
                match_rec = TransactionMatch(
                    id=uuid4(),
                    plan_id=plan_id,
                    candidate_id=cand.id,
                    statement_row_id=None,
                    transaction_id=best_txn.id,
                    classification=best_eval["classification"],
                    status="suggested",
                    confidence_score=best_eval["confidence_score"],
                    signals=best_eval["signals"],
                    provenance={"evaluated_at": now.isoformat()},
                    creation_fingerprint=fp,
                    created_at=now,
                    updated_at=now,
                )
                session.add(match_rec)
                evaluated_matches.append(match_rec)
            else:
                existing_match.classification = best_eval["classification"]
                existing_match.confidence_score = best_eval["confidence_score"]
                existing_match.signals = best_eval["signals"]
                existing_match.updated_at = now
                evaluated_matches.append(existing_match)
        else:
            # Classification as NEW_TRANSACTION
            eval_res = (
                best_eval
                if best_eval
                else {
                    "classification": "NEW_TRANSACTION",
                    "confidence_score": Decimal("0.0000"),
                    "signals": {"note": "no plausible transaction match found"},
                }
            )
            fp = fingerprint({"plan_id": str(plan_id), "candidate_id": str(cand.id), "classification": "NEW_TRANSACTION"})
            existing_match = session.scalar(
                select(TransactionMatch).where(
                    TransactionMatch.plan_id == plan_id,
                    TransactionMatch.candidate_id == cand.id,
                    TransactionMatch.transaction_id.is_(None),
                )
            )
            if existing_match is None:
                match_rec = TransactionMatch(
                    id=uuid4(),
                    plan_id=plan_id,
                    candidate_id=cand.id,
                    statement_row_id=None,
                    transaction_id=None,
                    classification="NEW_TRANSACTION",
                    status="suggested",
                    confidence_score=Decimal("0.0000"),
                    signals=eval_res["signals"],
                    provenance={"evaluated_at": now.isoformat()},
                    creation_fingerprint=fp,
                    created_at=now,
                    updated_at=now,
                )
                session.add(match_rec)
                evaluated_matches.append(match_rec)
            else:
                existing_match.classification = "NEW_TRANSACTION"
                existing_match.confidence_score = Decimal("0.0000")
                existing_match.signals = eval_res["signals"]
                existing_match.updated_at = now
                evaluated_matches.append(existing_match)

    # Match Statement Rows against Transactions
    for row in statement_rows:
        best_eval = None
        best_txn = None
        best_score = Decimal("-1")

        for txn in transactions:
            eval_res = evaluate_match_pair(row, txn)
            score = eval_res["confidence_score"]
            if score > best_score:
                best_score = score
                best_eval = eval_res
                best_txn = txn

        if best_eval and best_txn and best_eval["classification"] != "NEW_TRANSACTION":
            fingerprint_payload = {
                "plan_id": str(plan_id),
                "statement_row_id": str(row.id),
                "transaction_id": str(best_txn.id),
                "classification": best_eval["classification"],
            }
            fp = fingerprint(fingerprint_payload)

            existing_match = session.scalar(
                select(TransactionMatch).where(
                    TransactionMatch.plan_id == plan_id,
                    TransactionMatch.statement_row_id == row.id,
                    TransactionMatch.transaction_id == best_txn.id,
                )
            )

            if existing_match is None:
                match_rec = TransactionMatch(
                    id=uuid4(),
                    plan_id=plan_id,
                    candidate_id=None,
                    statement_row_id=row.id,
                    transaction_id=best_txn.id,
                    classification=best_eval["classification"],
                    status="suggested",
                    confidence_score=best_eval["confidence_score"],
                    signals=best_eval["signals"],
                    provenance={"evaluated_at": now.isoformat()},
                    creation_fingerprint=fp,
                    created_at=now,
                    updated_at=now,
                )
                session.add(match_rec)
                evaluated_matches.append(match_rec)
            else:
                existing_match.classification = best_eval["classification"]
                existing_match.confidence_score = best_eval["confidence_score"]
                existing_match.signals = best_eval["signals"]
                existing_match.updated_at = now
                evaluated_matches.append(existing_match)

    session.flush()

    # Handle auto_link_exact if requested (CRITICAL: POSSIBLE_MATCH is NEVER auto-linked)
    if payload and payload.auto_link_exact:
        for m in evaluated_matches:
            if m.status == "suggested" and m.classification == "EXACT_MATCH":
                accept_match(session, plan_id, m.id)

    response_items = [_build_match_response(session, m) for m in evaluated_matches]
    return MatchEvaluationResponse(
        evaluations=response_items,
        evaluated_candidates_count=len(candidates),
        evaluated_statement_rows_count=len(statement_rows),
        matches_created_count=len(evaluated_matches),
    )


def list_matches(
    session: Session,
    plan_id: UUID,
    status: str | None = None,
    classification: str | None = None,
) -> list[TransactionMatchResponse]:
    _require_plan(session, plan_id)

    query = select(TransactionMatch).where(TransactionMatch.plan_id == plan_id)
    if status:
        query = query.where(TransactionMatch.status == status)
    if classification:
        query = query.where(TransactionMatch.classification == classification)
    query = query.order_by(TransactionMatch.created_at.desc())

    matches = list(session.scalars(query).all())
    return [_build_match_response(session, m) for m in matches]


def get_match(session: Session, plan_id: UUID, match_id: UUID) -> TransactionMatchResponse:
    _require_plan(session, plan_id)

    match = session.scalar(
        select(TransactionMatch).where(
            TransactionMatch.plan_id == plan_id,
            TransactionMatch.id == match_id,
        )
    )
    if match is None:
        raise ResourceNotFound(f"Transaction match {match_id} not found.")

    return _build_match_response(session, match)


def accept_match(
    session: Session, plan_id: UUID, match_id: UUID
) -> TransactionMatchResponse:
    _require_plan(session, plan_id)

    match = session.scalar(
        select(TransactionMatch).where(
            TransactionMatch.plan_id == plan_id,
            TransactionMatch.id == match_id,
        )
    )
    if match is None:
        raise ResourceNotFound(f"Transaction match {match_id} not found.")

    if match.status == "accepted":
        return _build_match_response(session, match)

    candidate = (
        session.get(WatcherCandidate, match.candidate_id)
        if match.candidate_id
        else None
    )
    statement_row = (
        session.get(StatementRow, match.statement_row_id)
        if match.statement_row_id
        else None
    )
    transaction = (
        session.get(Transaction, match.transaction_id)
        if match.transaction_id
        else None
    )

    now = utc_now()

    # Perform non-destructive enrichment on Transaction
    if transaction is not None:
        updated_meta = dict(transaction.source_metadata or {})
        updated_prov = dict(transaction.provenance or {})

        # Enrich Candidate Details
        if candidate is not None:
            # Preserve user-provided fields (merchant, memo) if already set on transaction
            if not transaction.merchant and candidate.merchant:
                transaction.merchant = candidate.merchant

            if not transaction.memo:
                memo_candidate = candidate.glosa or candidate.subject
                if memo_candidate:
                    transaction.memo = memo_candidate

            # Merge provider IDs non-destructively
            raw_payload = candidate.raw_payload or {}
            cand_prov = candidate.provenance or {}
            if candidate.candidate_type == "bcp_qr":
                tx_id = (
                    raw_payload.get("transaction_id")
                    or raw_payload.get("id_transaccion")
                    or cand_prov.get("transaction_id")
                )
                rcpt_id = (
                    raw_payload.get("receipt_id")
                    or raw_payload.get("nro_comprobante")
                    or cand_prov.get("receipt_id")
                )
                if tx_id:
                    updated_meta["bcp_transaction_id"] = str(tx_id)
                if rcpt_id:
                    updated_meta["bcp_receipt_id"] = str(rcpt_id)
                if candidate.message_id_header:
                    updated_meta["message_id"] = candidate.message_id_header
            elif candidate.candidate_type == "binance_card":
                if candidate.message_id_header:
                    updated_meta["message_id"] = candidate.message_id_header
                if candidate.provider_uuid:
                    updated_prov["provider_uuid"] = candidate.provider_uuid
            elif candidate.candidate_type == "banco_ganadero":
                if candidate.message_id_header:
                    updated_meta["message_id"] = candidate.message_id_header
                if candidate.account_suffix:
                    updated_meta["account_suffix"] = candidate.account_suffix

            updated_prov["matched_candidate_id"] = str(candidate.id)
            updated_prov["candidate_type"] = candidate.candidate_type

            # Update candidate status and link
            candidate.status = "resolved"
            candidate.transaction_id = transaction.id
            candidate.updated_at = now

            # If Ganadero notice (had event_at None), record authoritative event time in provenance
            if candidate.candidate_type == "banco_ganadero" and candidate.event_at is None:
                cand_provenance = dict(candidate.provenance or {})
                cand_provenance["enriched_event_at"] = transaction.event_at.isoformat()
                cand_provenance["statement_enriched"] = True
                candidate.provenance = cand_provenance

        # Enrich Statement Row Details
        if statement_row is not None:
            if not transaction.memo and statement_row.description:
                transaction.memo = statement_row.description

            updated_meta["statement_transaction_number"] = statement_row.transaction_number
            updated_meta["compound_identity"] = statement_row.compound_identity
            if statement_row.channel:
                updated_meta["channel"] = statement_row.channel
            if statement_row.card_suffix:
                updated_meta["card_suffix"] = statement_row.card_suffix

            updated_prov["statement_import_id"] = str(statement_row.import_id)
            updated_prov["statement_row_id"] = str(statement_row.id)

            statement_row.match_status = "matched"
            statement_row.transaction_id = transaction.id

        transaction.source_metadata = updated_meta
        transaction.provenance = updated_prov
        transaction.updated_at = now

    match.status = "accepted"
    match_prov = dict(match.provenance or {})
    match_prov["accepted_at"] = now.isoformat()
    match.provenance = match_prov
    match.updated_at = now

    session.flush()
    return _build_match_response(session, match)


def reject_match(
    session: Session,
    plan_id: UUID,
    match_id: UUID,
    reason: str | None = None,
) -> TransactionMatchResponse:
    _require_plan(session, plan_id)

    match = session.scalar(
        select(TransactionMatch).where(
            TransactionMatch.plan_id == plan_id,
            TransactionMatch.id == match_id,
        )
    )
    if match is None:
        raise ResourceNotFound(f"Transaction match {match_id} not found.")

    now = utc_now()
    match.status = "rejected"
    prov = dict(match.provenance or {})
    prov["rejected_at"] = now.isoformat()
    if reason:
        prov["rejection_reason"] = reason
    match.provenance = prov
    match.updated_at = now

    session.flush()
    return _build_match_response(session, match)


def unlink_match(
    session: Session,
    plan_id: UUID,
    match_id: UUID,
    reason: str | None = None,
) -> TransactionMatchResponse:
    _require_plan(session, plan_id)

    match = session.scalar(
        select(TransactionMatch).where(
            TransactionMatch.plan_id == plan_id,
            TransactionMatch.id == match_id,
        )
    )
    if match is None:
        raise ResourceNotFound(f"Transaction match {match_id} not found.")

    now = utc_now()

    # Revert candidate link if candidate is attached
    if match.candidate_id:
        candidate = session.get(WatcherCandidate, match.candidate_id)
        if candidate and candidate.transaction_id == match.transaction_id:
            candidate.status = "pending"
            candidate.transaction_id = None
            candidate.updated_at = now

    # Revert statement row link if statement row is attached
    if match.statement_row_id:
        stmt_row = session.get(StatementRow, match.statement_row_id)
        if stmt_row and stmt_row.transaction_id == match.transaction_id:
            stmt_row.match_status = "unmatched"
            stmt_row.transaction_id = None

    # Record unlinking in transaction provenance
    if match.transaction_id:
        transaction = session.get(Transaction, match.transaction_id)
        if transaction:
            txn_prov = dict(transaction.provenance or {})
            unlinked_log = list(txn_prov.get("unlinked_matches", []))
            unlinked_log.append(
                {
                    "match_id": str(match.id),
                    "unlinked_at": now.isoformat(),
                    "reason": reason,
                }
            )
            txn_prov["unlinked_matches"] = unlinked_log
            transaction.provenance = txn_prov
            transaction.updated_at = now

    match.status = "unlinked"
    match_prov = dict(match.provenance or {})
    match_prov["unlinked_at"] = now.isoformat()
    if reason:
        match_prov["unlink_reason"] = reason
    match.provenance = match_prov
    match.updated_at = now

    session.flush()
    return _build_match_response(session, match)
