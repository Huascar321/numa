from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fnmatch
import re
from typing import Any
from uuid import UUID

from app.rules.models import Rule


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuleEvaluationOutcome:
    candidate_id: UUID
    has_conflict: bool = False
    conflict_reason: str | None = None
    applied_fields: dict[str, Any] = field(default_factory=dict)
    rule_evidence: list[dict[str, Any]] = field(default_factory=list)


def _get_candidate_field_value(candidate: Any, field_name: str) -> Any:
    """Extract a field or nested property from a WatcherCandidate or candidate dict."""
    if isinstance(candidate, dict):
        if field_name in candidate:
            return candidate[field_name]
        if "." in field_name:
            parts = field_name.split(".")
            curr = candidate
            for p in parts:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                else:
                    return None
            return curr
        # Check raw_payload / provenance fallbacks
        raw_payload = candidate.get("raw_payload") or {}
        if isinstance(raw_payload, dict) and field_name in raw_payload:
            return raw_payload[field_name]
        return None

    # Object attribute access
    if hasattr(candidate, field_name):
        return getattr(candidate, field_name)

    if "." in field_name:
        parts = field_name.split(".")
        curr: Any = candidate
        for p in parts:
            if hasattr(curr, p):
                curr = getattr(curr, p)
            elif isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                return None
        return curr

    # Check raw_payload / provenance on candidate object
    raw_payload = getattr(candidate, "raw_payload", None)
    if isinstance(raw_payload, dict) and field_name in raw_payload:
        return raw_payload[field_name]

    provenance = getattr(candidate, "provenance", None)
    if isinstance(provenance, dict) and field_name in provenance:
        return provenance[field_name]

    return None


def match_predicate_condition(field_val: Any, expected: Any) -> bool:
    """Match a single field value against an expected condition or operator dict."""
    if expected is None:
        return field_val is None

    # Simple scalar equality
    if not isinstance(expected, dict):
        if field_val is None:
            return False
        if isinstance(field_val, Decimal) or isinstance(expected, (int, float, Decimal)):
            try:
                return Decimal(str(field_val)) == Decimal(str(expected))
            except (InvalidOperation, ValueError):
                pass
        if isinstance(field_val, str) and isinstance(expected, str):
            return field_val.strip() == expected.strip()
        return field_val == expected

    # Operator dictionary
    for op, target in expected.items():
        op_lower = op.lower()
        if op_lower in {"equals", "exact", "eq", "=="}:
            if field_val is None:
                return False
            if isinstance(field_val, str) and isinstance(target, str):
                if field_val.strip() != target.strip():
                    return False
            elif field_val != target:
                return False
        elif op_lower in {"iequals", "iexact"}:
            if field_val is None:
                return False
            if str(field_val).strip().lower() != str(target).strip().lower():
                return False
        elif op_lower in {"in", "isin"}:
            if field_val is None:
                return False
            if isinstance(target, (list, set, tuple)):
                if isinstance(field_val, str):
                    if not any(str(field_val).strip() == str(t).strip() for t in target):
                        return False
                elif field_val not in target:
                    return False
            else:
                return False
        elif op_lower in {"contains", "icontains"}:
            if field_val is None:
                return False
            if op_lower == "contains":
                if str(target) not in str(field_val):
                    return False
            else:
                if str(target).lower() not in str(field_val).lower():
                    return False
        elif op_lower in {"glob", "pattern"}:
            if field_val is None:
                return False
            if not fnmatch.fnmatch(str(field_val).lower(), str(target).lower()):
                return False
        elif op_lower in {"regex", "match"}:
            if field_val is None:
                return False
            if not re.search(str(target), str(field_val)):
                return False
        elif op_lower in {"gt", ">"}:
            if field_val is None:
                return False
            try:
                if Decimal(str(field_val)) <= Decimal(str(target)):
                    return False
            except (InvalidOperation, ValueError):
                return False
        elif op_lower in {"gte", ">="}:
            if field_val is None:
                return False
            try:
                if Decimal(str(field_val)) < Decimal(str(target)):
                    return False
            except (InvalidOperation, ValueError):
                return False
        elif op_lower in {"lt", "<"}:
            if field_val is None:
                return False
            try:
                if Decimal(str(field_val)) >= Decimal(str(target)):
                    return False
            except (InvalidOperation, ValueError):
                return False
        elif op_lower in {"lte", "<="}:
            if field_val is None:
                return False
            try:
                if Decimal(str(field_val)) > Decimal(str(target)):
                    return False
            except (InvalidOperation, ValueError):
                return False
        elif op_lower in {"is_null", "isnull"}:
            is_null = field_val is None
            if is_null != bool(target):
                return False
        elif op_lower in {"exists"}:
            exists = field_val is not None
            if exists != bool(target):
                return False
        else:
            # Unknown operator, treat as mismatch
            return False

    return True


def evaluate_predicate(predicate: dict[str, Any], candidate: Any) -> bool:
    """Evaluate a compound or simple rule predicate against a candidate."""
    if not predicate:
        return True

    # Logical combinators
    if "all" in predicate:
        sub_preds = predicate["all"]
        if isinstance(sub_preds, list):
            return all(evaluate_predicate(p, candidate) for p in sub_preds)

    if "any" in predicate:
        sub_preds = predicate["any"]
        if isinstance(sub_preds, list):
            return any(evaluate_predicate(p, candidate) for p in sub_preds)

    if "not" in predicate:
        sub_pred = predicate["not"]
        if isinstance(sub_pred, dict):
            return not evaluate_predicate(sub_pred, candidate)

    # Key-value field checks
    for field_name, expected_cond in predicate.items():
        if field_name in {"all", "any", "not"}:
            continue
        field_val = _get_candidate_field_value(candidate, field_name)
        if not match_predicate_condition(field_val, expected_cond):
            return False

    return True


def extract_action_targets(action: dict[str, Any]) -> dict[str, Any]:
    """Normalize rule action into target key-value pairs."""
    targets: dict[str, Any] = {}
    if not action:
        return targets

    # If action has "set_fields"
    if "set_fields" in action and isinstance(action["set_fields"], dict):
        targets.update(action["set_fields"])

    for k, v in action.items():
        if k == "set_fields":
            continue
        if k.startswith("set_"):
            clean_k = k[4:]
            targets[clean_k] = v
        else:
            targets[k] = v

    return targets


def evaluate_rules_for_candidate(
    candidate: Any,
    rules: list[Rule],
) -> RuleEvaluationOutcome:
    """Evaluate an ordered list of rules on a candidate deterministically.

    Invariants:
    1. Rules execute in stable priority order (priority ASC, created_at ASC, id ASC).
    2. Conflicting rules for the same target field MUST NOT be resolved silently.
       They MUST record conflict evidence and quarantine the candidate with `quarantine_reason = "rule_conflict"`.
    3. Applied, skipped, and conflicting rule evidence MUST be recorded.
    """
    sorted_rules = sorted(
        [r for r in rules if r.enabled],
        key=lambda r: (r.priority, r.created_at, str(r.id)),
    )

    candidate_id = getattr(candidate, "id", None) or UUID("00000000-0000-0000-0000-000000000000")
    outcome = RuleEvaluationOutcome(candidate_id=candidate_id)

    # Map of target_field -> (value, rule_id, rule_name)
    applied_targets: dict[str, tuple[Any, UUID, str]] = {}
    rule_evidence: list[dict[str, Any]] = []

    for rule in sorted_rules:
        now_ts = utc_now_iso()
        matches = evaluate_predicate(rule.predicate, candidate)
        if not matches:
            rule_evidence.append({
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "result": "skipped",
                "reason": "predicate_unmatched",
                "timestamp": now_ts,
            })
            continue

        targets = extract_action_targets(rule.action)
        rule_has_conflict = False

        for target_field, target_val in targets.items():
            if target_field in applied_targets:
                existing_val, prev_rule_id, prev_rule_name = applied_targets[target_field]
                if existing_val != target_val:
                    # Conflict detected!
                    rule_has_conflict = True
                    outcome.has_conflict = True
                    outcome.conflict_reason = "rule_conflict"
                    rule_evidence.append({
                        "rule_id": str(rule.id),
                        "rule_name": rule.name,
                        "result": "conflict",
                        "conflicting_field": target_field,
                        "existing_value": str(existing_val),
                        "attempted_value": str(target_val),
                        "existing_rule_id": str(prev_rule_id),
                        "existing_rule_name": prev_rule_name,
                        "reason": f"Conflict on field '{target_field}': '{existing_val}' vs '{target_val}'",
                        "timestamp": now_ts,
                    })
                    break

        if not rule_has_conflict:
            for target_field, target_val in targets.items():
                applied_targets[target_field] = (target_val, rule.id, rule.name)
                outcome.applied_fields[target_field] = target_val

            rule_evidence.append({
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "result": "applied",
                "applied_actions": targets,
                "timestamp": now_ts,
            })

    outcome.rule_evidence = rule_evidence
    return outcome
