from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
import hashlib
import json

from app.watchers.contracts import (
    HintField, MatchField, NoticeFacts, PipelineResult, Provider, Rule, RuleEvidence,
    SourceRef, Stage, StageOutcome, STAGE_ORDER,
)

ENGINE_VERSION = "review-pipeline-v1"
Parser = Callable[[], NoticeFacts]


def canonical_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()


def ordered_rules(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError("Rule IDs must be unique within a ruleset.")
    return tuple(sorted(rules, key=lambda rule: (rule.priority, rule.id, rule.version)))


def rule_snapshot(rules: tuple[Rule, ...]) -> list[dict]:
    return [asdict(rule) for rule in sorted(rules, key=lambda rule: (
        rule.priority, rule.id, rule.version, canonical_hash(asdict(rule)),
    ))]


def ruleset_hash(rules: tuple[Rule, ...], protected_hints: Mapping[str, str]) -> str:
    return canonical_hash({"rules": rule_snapshot(rules),
                           "protected_hints": dict(protected_hints)})


def execute(
    parser: Parser, rules: tuple[Rule, ...] = (), *,
    source: SourceRef,
    protected_hints: Mapping[str, str] | None = None,
) -> PipelineResult:
    """Run classification only. No financial imports, optional AI or posting."""
    if not isinstance(source, SourceRef):
        raise ValueError("A typed raw-safe source reference is required.")
    protected = dict(protected_hints or {})
    if any(key not in {field.value for field in HintField} or not isinstance(value, str)
           for key, value in protected.items()):
        raise ValueError("Only typed classification hints may be protected.")
    stages = [StageOutcome(Stage.EMAIL, "ok", "raw_reference_retained"),
              StageOutcome(Stage.WATCHER, "ok", "typed_parser_selected")]
    def quarantine(stage: Stage, code: str, facts=None, evidence=()):
        stages.append(StageOutcome(stage, "quarantined", code))
        stages.extend(StageOutcome(later, "skipped", "upstream_quarantined")
                      for later in STAGE_ORDER[len(stages):])
        return PipelineResult("quarantined", source, tuple(stages), facts,
                              tuple(sorted(protected.items())), tuple(evidence), (code,), code)
    try:
        facts = parser()
        if not isinstance(facts, NoticeFacts):
            raise ValueError("Parser returned an untyped result.")
    except Exception:
        # Exception details can contain merchant names, message bodies or secrets.
        return quarantine(Stage.PARSER, "parser_failed")
    stages.append(StageOutcome(Stage.PARSER, "ok", "reported_facts_preserved"))
    evidence: list[RuleEvidence] = []
    proposals: dict[str, set[str]] = {}
    try:
        sorted_rules = ordered_rules(rules)
        for rule in sorted_rules:
            actual = getattr(facts, rule.predicate.field.value)
            matched = actual == rule.predicate.value
            outcome = "skipped_no_match"
            if matched:
                if facts.provider is Provider.BCP_QR and rule.target is HintField.SUBTYPE and (
                    facts.raw_glosa not in {"BM BM QR PAGO DE PRODUCTOS", "BM BM QR INTERBANCARIA"}
                    or rule.predicate.field is not MatchField.RAW_GLOSA
                ):
                    outcome = "skipped_unsafe_qr_subtype"
                elif rule.target.value in protected:
                    outcome = "skipped_manual_protection"
                else:
                    outcome = "proposed"
                    proposals.setdefault(rule.target.value, set()).add(rule.value)
            evidence.append(RuleEvidence(rule.id, rule.version, rule.priority, outcome,
                rule.predicate.field.value, actual, rule.target.value, rule.value))
    except Exception:
        return quarantine(Stage.RULES, "rule_failed", facts, evidence)
    if any(len(values) > 1 for values in proposals.values()):
        return quarantine(Stage.RULES, "rule_conflict", facts, evidence)
    stages.append(StageOutcome(Stage.RULES, "ok", "rule_evidence_retained"))
    stages.append(StageOutcome(Stage.AI, "skipped", "ai_not_enabled"))
    hints = {key: next(iter(values)) for key, values in proposals.items()}
    hints.update(protected)
    reasons = []
    if facts.event_at is None:
        reasons.append("missing_event_time")
    if facts.provider is Provider.BINANCE_CARD:
        reasons.append("settlement_unresolved")
    if facts.provider is Provider.GANADERO:
        reasons.append("statement_enrichment_required")
    if facts.provider is Provider.BCP_QR and not facts.raw_glosa:
        reasons.append("missing_glosa")
    if not facts.transaction_id and not facts.receipt_id:
        reasons.append("provider_identity_unverified")
    stages.extend((StageOutcome(Stage.NORMALIZE, "ok", "no_missing_facts_invented"),
                   StageOutcome(Stage.DEDUPLICATE, "ok", "source_identity_only"),
                   StageOutcome(Stage.TRANSACTION, "blocked", "posting_not_enabled")))
    return PipelineResult("review_only", source, tuple(stages), facts, tuple(sorted(hints.items())),
                          tuple(evidence), tuple(reasons))
