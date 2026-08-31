from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account, Plan
from app.accounts.service import ResourceNotFound
from app.ledger.models import Category
from app.ledger.schemas import TransactionCreate
from app.ledger.service import _pending_category, create_transaction
from app.rules.engine import evaluate_rules_for_candidate
from app.rules.models import Rule
from app.rules.schemas import ReplayRulesResponse, RuleCreate, RuleUpdate
from app.watchers.models import WatcherCandidate


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} does not exist.")
    return plan


def list_rules(
    session: Session,
    plan_id: UUID,
    stage: str | None = None,
    enabled: bool | None = None,
) -> list[Rule]:
    _require_plan(session, plan_id)
    query = select(Rule).where(Rule.plan_id == plan_id)
    if stage is not None:
        query = query.where(Rule.stage == stage)
    if enabled is not None:
        query = query.where(Rule.enabled == enabled)
    query = query.order_by(Rule.priority.asc(), Rule.created_at.asc(), Rule.id.asc())
    return list(session.scalars(query).all())


def get_rule(session: Session, plan_id: UUID, rule_id: UUID) -> Rule:
    _require_plan(session, plan_id)
    rule = session.scalar(
        select(Rule).where(
            Rule.plan_id == plan_id,
            Rule.id == rule_id,
        )
    )
    if rule is None:
        raise ResourceNotFound(f"Rule {rule_id} does not exist.")
    return rule


def create_rule(
    session: Session,
    plan_id: UUID,
    payload: RuleCreate,
) -> Rule:
    _require_plan(session, plan_id)
    now = utc_now()
    rule_id = uuid4()
    fingerprint = sha256(f"rule:{plan_id}:{payload.name}:{rule_id}".encode("utf-8")).hexdigest()
    rule = Rule(
        id=rule_id,
        plan_id=plan_id,
        name=payload.name,
        stage=payload.stage,
        priority=payload.priority,
        enabled=payload.enabled,
        predicate=payload.predicate,
        action=payload.action,
        version=1,
        creation_fingerprint=fingerprint,
        created_at=now,
        updated_at=now,
    )
    session.add(rule)
    session.flush()
    return rule


def update_rule(
    session: Session,
    plan_id: UUID,
    rule_id: UUID,
    payload: RuleUpdate,
) -> Rule:
    rule = get_rule(session, plan_id, rule_id)
    now = utc_now()

    if payload.name is not None:
        rule.name = payload.name
    if payload.stage is not None:
        rule.stage = payload.stage
    if payload.priority is not None:
        rule.priority = payload.priority
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.predicate is not None:
        rule.predicate = payload.predicate
    if payload.action is not None:
        rule.action = payload.action

    rule.version += 1
    rule.updated_at = now
    session.flush()
    return rule


def delete_rule(
    session: Session,
    plan_id: UUID,
    rule_id: UUID,
) -> None:
    rule = get_rule(session, plan_id, rule_id)
    session.delete(rule)
    session.flush()


def apply_rules_to_candidate(
    session: Session,
    candidate: WatcherCandidate,
    rules: list[Rule],
) -> WatcherCandidate:
    """Evaluate and apply rules to a single candidate, handling conflicts and auto-resolution."""
    outcome = evaluate_rules_for_candidate(candidate, rules)
    candidate.rule_evidence = outcome.rule_evidence

    if outcome.has_conflict:
        candidate.status = "quarantined"
        candidate.quarantine_reason = "rule_conflict"
        candidate.updated_at = utc_now()
        session.flush()
        return candidate

    # Apply non-conflicting targets
    applied = outcome.applied_fields
    if "qr_subtype" in applied and applied["qr_subtype"]:
        candidate.qr_subtype = str(applied["qr_subtype"])

    if "merchant" in applied and applied["merchant"]:
        candidate.merchant = str(applied["merchant"])

    if "direction" in applied and applied["direction"]:
        candidate.direction = str(applied["direction"])

    # If previously quarantined for rule conflict and now resolved
    if candidate.quarantine_reason == "rule_conflict":
        candidate.quarantine_reason = None
        if candidate.status == "quarantined":
            candidate.status = "pending"

    # Check auto-resolve directive
    auto_resolve = applied.get("auto_resolve") is True
    target_account_id = (
        applied.get("account_id")
        or applied.get("target_account_id")
        or applied.get("suggested_account_id")
    )

    if auto_resolve and target_account_id and candidate.status != "resolved":
        try:
            account_uuid = (
                UUID(str(target_account_id))
                if isinstance(target_account_id, str)
                else target_account_id
            )
            account = session.scalar(
                select(Account).where(
                    Account.plan_id == candidate.plan_id,
                    Account.id == account_uuid,
                    Account.status == "active",
                )
            )
            if account is not None and candidate.event_at is not None:
                category_id = (
                    applied.get("category_id")
                    or applied.get("target_category_id")
                    or applied.get("suggested_category_id")
                )
                category = None
                if category_id:
                    cat_uuid = (
                        UUID(str(category_id))
                        if isinstance(category_id, str)
                        else category_id
                    )
                    category = session.get(Category, cat_uuid)
                if category is None or category.plan_id != candidate.plan_id:
                    category = _pending_category(session, candidate.plan_id)

                tx_type = "expense"
                if candidate.direction == "credit":
                    tx_type = "income"

                tx_id = uuid4()
                tx_payload = TransactionCreate(
                    type=tx_type,
                    account_id=account.id,
                    amount=str(candidate.reported_amount),
                    currency_code=account.currency_code,
                    event_at=candidate.event_at,
                    category_id=category.id,
                    merchant=candidate.merchant,
                    memo=applied.get("memo") or f"Rule auto-resolved {candidate.candidate_type}",
                    tags=[],
                    source_metadata={
                        "candidate_id": str(candidate.id),
                        "candidate_type": candidate.candidate_type,
                        "reported_amount": str(candidate.reported_amount),
                        "reported_currency": candidate.reported_currency,
                        "qr_subtype": candidate.qr_subtype,
                    },
                    provenance={
                        "source": f"rule_auto_resolve:{candidate.candidate_type}",
                        "raw_message_id": str(candidate.raw_message_id),
                        "rule_evidence": outcome.rule_evidence,
                    },
                )
                tx_result = create_transaction(
                    session=session,
                    plan_id=candidate.plan_id,
                    transaction_id=tx_id,
                    payload=tx_payload,
                )
                candidate.status = "resolved"
                candidate.settlement_amount = candidate.reported_amount
                candidate.settlement_currency = account.currency_code
                candidate.transaction_id = tx_result.resource.id
                candidate.quarantine_reason = None
        except Exception:
            # If auto-resolution fails, keep candidate pending or reviewable
            pass

    candidate.updated_at = utc_now()
    session.flush()
    return candidate


def replay_plan_rules(
    session: Session,
    plan_id: UUID,
    candidate_ids: list[UUID] | None = None,
) -> ReplayRulesResponse:
    """Replay current enabled rules across candidates while preserving raw provenance and audit history."""
    _require_plan(session, plan_id)
    rules = list_rules(session, plan_id, stage="watcher_candidate", enabled=True)

    query = select(WatcherCandidate).where(WatcherCandidate.plan_id == plan_id)
    if candidate_ids:
        query = query.where(WatcherCandidate.id.in_(candidate_ids))
    else:
        # Replay pending, quarantined, and reviewable candidates (preserve already resolved)
        query = query.where(WatcherCandidate.status.in_(["pending", "quarantined", "ignored"]))

    candidates = list(session.scalars(query).all())

    replayed_count = len(candidates)
    resolved_count = 0
    quarantined_count = 0
    pending_count = 0

    for cand in candidates:
        apply_rules_to_candidate(session, cand, rules)
        if cand.status == "resolved":
            resolved_count += 1
        elif cand.status == "quarantined":
            quarantined_count += 1
        elif cand.status == "pending":
            pending_count += 1

    return ReplayRulesResponse(
        replayed_count=replayed_count,
        resolved_count=resolved_count,
        quarantined_count=quarantined_count,
        pending_count=pending_count,
    )
