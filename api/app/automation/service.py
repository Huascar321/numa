from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Plan
from app.accounts.service import ResourceNotFound
from app.automation.detector import detect_automation_suggestions
from app.automation.models import AutomationRuleSuggestion
from app.automation.schemas import AutomationSuggestionAcceptRequest
from app.rules.models import Rule
from app.rules.schemas import RuleCreate
from app.rules.service import create_rule, get_rule


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} does not exist.")
    return plan


def _fingerprint_for_suggestion(
    plan_id: UUID,
    suggestion_type: str,
    predicate: dict[str, Any],
    action: dict[str, Any],
) -> str:
    pred_str = json.dumps(predicate, sort_keys=True)
    act_str = json.dumps(action, sort_keys=True)
    raw = f"suggestion:{plan_id}:{suggestion_type}:{pred_str}:{act_str}"
    return sha256(raw.encode("utf-8")).hexdigest()


def discover_suggestions(
    session: Session,
    plan_id: UUID,
) -> tuple[int, int, list[AutomationRuleSuggestion]]:
    """Run pattern detection and persist newly discovered automation rule suggestions."""
    _require_plan(session, plan_id)

    detected = detect_automation_suggestions(session, plan_id)
    discovered_count = len(detected)
    created_count = 0
    now = utc_now()

    for item in detected:
        fingerprint = _fingerprint_for_suggestion(
            plan_id=plan_id,
            suggestion_type=item["suggestion_type"],
            predicate=item["predicate"],
            action=item["action"],
        )

        existing = session.scalar(
            select(AutomationRuleSuggestion).where(
                AutomationRuleSuggestion.plan_id == plan_id,
                AutomationRuleSuggestion.creation_fingerprint == fingerprint,
            )
        )

        if existing is None:
            suggestion = AutomationRuleSuggestion(
                id=uuid4(),
                plan_id=plan_id,
                suggestion_type=item["suggestion_type"],
                status="suggested",
                title=item["title"],
                description=item.get("description"),
                rule_stage=item.get("rule_stage", "watcher_candidate"),
                suggested_priority=item.get("suggested_priority", 100),
                predicate=item["predicate"],
                action=item["action"],
                evidence=item.get("evidence", {}),
                confidence=item.get("confidence"),
                source=item.get("source", "pattern_detector"),
                creation_fingerprint=fingerprint,
                created_at=now,
                updated_at=now,
            )
            session.add(suggestion)
            created_count += 1

    session.flush()

    current_suggestions = list(
        session.scalars(
            select(AutomationRuleSuggestion)
            .where(
                AutomationRuleSuggestion.plan_id == plan_id,
                AutomationRuleSuggestion.status == "suggested",
            )
            .order_by(
                AutomationRuleSuggestion.created_at.desc(),
                AutomationRuleSuggestion.id.asc(),
            )
        ).all()
    )

    return discovered_count, created_count, current_suggestions


def list_suggestions(
    session: Session,
    plan_id: UUID,
    status: str | None = None,
    source: str | None = None,
) -> list[AutomationRuleSuggestion]:
    """List automation rule suggestions for a plan with optional status/source filtering."""
    _require_plan(session, plan_id)
    query = select(AutomationRuleSuggestion).where(
        AutomationRuleSuggestion.plan_id == plan_id
    )
    if status is not None:
        query = query.where(AutomationRuleSuggestion.status == status)
    if source is not None:
        query = query.where(AutomationRuleSuggestion.source == source)
    query = query.order_by(
        AutomationRuleSuggestion.created_at.desc(),
        AutomationRuleSuggestion.id.asc(),
    )
    return list(session.scalars(query).all())


def get_suggestion(
    session: Session,
    plan_id: UUID,
    suggestion_id: UUID,
) -> AutomationRuleSuggestion:
    """Get a single automation rule suggestion."""
    _require_plan(session, plan_id)
    suggestion = session.scalar(
        select(AutomationRuleSuggestion).where(
            AutomationRuleSuggestion.plan_id == plan_id,
            AutomationRuleSuggestion.id == suggestion_id,
        )
    )
    if suggestion is None:
        raise ResourceNotFound(f"Automation suggestion {suggestion_id} does not exist.")
    return suggestion


def accept_suggestion(
    session: Session,
    plan_id: UUID,
    suggestion_id: UUID,
    payload: AutomationSuggestionAcceptRequest | None = None,
) -> tuple[AutomationRuleSuggestion, Rule]:
    """Accept an automation rule suggestion, creating an active deterministic Rule atomically.

    Invariants:
    1. Zero money mutation: Does NOT post or alter money, accounts, or timestamps.
    2. Atomically creates a Rule and marks suggestion as 'accepted' with created_rule_id.
    """
    suggestion = get_suggestion(session, plan_id, suggestion_id)
    now = utc_now()

    if suggestion.status == "accepted" and suggestion.created_rule_id is not None:
        rule = get_rule(session, plan_id, suggestion.created_rule_id)
        return suggestion, rule

    rule_name = (
        payload.name
        if (payload and payload.name and payload.name.strip())
        else suggestion.title
    )
    rule_priority = (
        payload.priority
        if (payload and payload.priority is not None)
        else suggestion.suggested_priority
    )
    rule_predicate = (
        payload.predicate
        if (payload and payload.predicate is not None)
        else suggestion.predicate
    )
    rule_action = (
        payload.action
        if (payload and payload.action is not None)
        else suggestion.action
    )

    # Atomically create deterministic Rule
    rule = create_rule(
        session=session,
        plan_id=plan_id,
        payload=RuleCreate(
            name=rule_name,
            stage=suggestion.rule_stage,
            priority=rule_priority,
            enabled=True,
            predicate=rule_predicate,
            action=rule_action,
        ),
    )

    # Update suggestion record
    suggestion.status = "accepted"
    suggestion.created_rule_id = rule.id
    suggestion.decided_at = now
    suggestion.updated_at = now
    session.flush()

    return suggestion, rule


def reject_suggestion(
    session: Session,
    plan_id: UUID,
    suggestion_id: UUID,
    reason: str | None = None,
) -> AutomationRuleSuggestion:
    """Reject an automation rule suggestion without modifying financial data."""
    suggestion = get_suggestion(session, plan_id, suggestion_id)
    now = utc_now()

    suggestion.status = "rejected"
    suggestion.decided_at = now
    suggestion.updated_at = now

    if reason:
        evidence = dict(suggestion.evidence)
        evidence["rejection_reason"] = reason
        suggestion.evidence = evidence

    session.flush()
    return suggestion


def dismiss_suggestion(
    session: Session,
    plan_id: UUID,
    suggestion_id: UUID,
) -> AutomationRuleSuggestion:
    """Dismiss an automation rule suggestion without modifying financial data."""
    suggestion = get_suggestion(session, plan_id, suggestion_id)
    now = utc_now()

    suggestion.status = "dismissed"
    suggestion.decided_at = now
    suggestion.updated_at = now

    session.flush()
    return suggestion
