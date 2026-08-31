from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger.models import Category, Transaction
from app.rules.models import Rule
from app.watchers.models import WatcherCandidate


NON_INFORMATIVE_QR_GLOSAS = {
    "BM BM QR INTERBANCARIA",
    "INTERBANCARIA",
    "QR INTERBANCARIA",
}


def _is_rule_already_covered(
    existing_rules: list[Rule],
    predicate: dict[str, Any],
    action: dict[str, Any],
) -> bool:
    """Check if an active rule already implements this predicate/action pattern."""
    for rule in existing_rules:
        if not rule.enabled:
            continue
        # If the predicate checks the same key with the same value
        match_pred = True
        for k, v in predicate.items():
            if rule.predicate.get(k) != v:
                match_pred = False
                break
        if match_pred:
            # Check if action also matches or covers the target field
            match_act = True
            for ak, av in action.items():
                if rule.action.get(ak) != av and rule.action.get(f"set_{ak}") != av:
                    # Also check nested set_fields
                    set_fields = rule.action.get("set_fields", {})
                    if isinstance(set_fields, dict) and set_fields.get(ak) == av:
                        continue
                    match_act = False
                    break
            if match_act:
                return True
    return False


def detect_automation_suggestions(
    session: Session,
    plan_id: UUID,
) -> list[dict[str, Any]]:
    """Analyze transactions and watcher candidates to discover deterministic automation rule candidates.

    Invariants:
    1. Suggestions MUST NOT mutate money, accounts, or timestamps.
    2. Missing or default 'BM BM QR INTERBANCARIA' glosa MUST NOT generate ungrounded suggestions.
    3. Existing active rules prevent duplicate suggestion proposals.
    """
    suggestions: list[dict[str, Any]] = []

    # Fetch active rules to avoid proposing already configured automations
    existing_rules = list(
        session.scalars(
            select(Rule).where(Rule.plan_id == plan_id, Rule.enabled == True)
        ).all()
    )

    # ---------------------------------------------------------
    # 1. Recurring Merchant -> Category pattern from transactions
    # ---------------------------------------------------------
    categories = {
        cat.id: cat
        for cat in session.scalars(
            select(Category).where(
                Category.plan_id == plan_id,
                Category.status == "active",
            )
        ).all()
    }

    transactions = list(
        session.scalars(
            select(Transaction).where(
                Transaction.plan_id == plan_id,
                Transaction.merchant.isnot(None),
                Transaction.category_id.isnot(None),
            )
        ).all()
    )

    # Group transactions by normalized merchant
    merchant_tx_map: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        m = (tx.merchant or "").strip()
        if not m:
            continue
        cat = categories.get(tx.category_id)
        if cat is None or cat.is_pending:
            continue
        merchant_tx_map[m].append(tx)

    for merchant_name, tx_list in merchant_tx_map.items():
        if len(tx_list) < 2:
            continue

        cat_counts: dict[UUID, int] = defaultdict(int)
        for tx in tx_list:
            if tx.category_id is not None:
                cat_counts[tx.category_id] += 1

        top_cat_id, top_count = max(cat_counts.items(), key=lambda item: item[1])
        total_tx = len(tx_list)
        ratio = top_count / total_tx

        if top_count >= 2 and ratio >= 0.75:
            cat_obj = categories.get(top_cat_id)
            if cat_obj is None:
                continue

            predicate = {"merchant": merchant_name}
            action = {"category_id": str(top_cat_id)}

            if _is_rule_already_covered(existing_rules, predicate, action):
                continue

            confidence = Decimal(str(round(min(ratio, 0.99), 2)))
            matching_sample = [tx for tx in tx_list if tx.category_id == top_cat_id]

            suggestions.append({
                "suggestion_type": "merchant_category",
                "title": f"Auto-categorize '{merchant_name}' as {cat_obj.name}",
                "description": (
                    f"Observed {top_count} of {total_tx} transactions from "
                    f"'{merchant_name}' categorized as '{cat_obj.name}'."
                ),
                "rule_stage": "watcher_candidate",
                "suggested_priority": 100,
                "predicate": predicate,
                "action": action,
                "evidence": {
                    "pattern": "recurring_merchant_category",
                    "merchant": merchant_name,
                    "category_id": str(top_cat_id),
                    "category_name": cat_obj.name,
                    "occurrence_count": top_count,
                    "total_count": total_tx,
                    "sample_transaction_ids": [str(t.id) for t in matching_sample[:5]],
                },
                "confidence": confidence,
                "source": "pattern_detector",
            })

    # ---------------------------------------------------------
    # 2. Informative BCP QR Glosa -> QR Subtype pattern
    # ---------------------------------------------------------
    candidates = list(
        session.scalars(
            select(WatcherCandidate).where(
                WatcherCandidate.plan_id == plan_id,
                WatcherCandidate.candidate_type == "bcp_qr",
            )
        ).all()
    )

    qr_glosa_map: dict[str, list[WatcherCandidate]] = defaultdict(list)
    for cand in candidates:
        raw_glosa = (cand.raw_glosa or cand.glosa or "").strip()
        # Invariant: Absent or default glosa MUST NOT generate ungrounded suggestions
        if not raw_glosa:
            continue
        if raw_glosa.upper() in NON_INFORMATIVE_QR_GLOSAS:
            continue
        qr_glosa_map[raw_glosa].append(cand)

    for raw_glosa, cand_list in qr_glosa_map.items():
        if not cand_list:
            continue

        count = len(cand_list)
        is_known_product = (raw_glosa.upper() == "BM BM QR PAGO DE PRODUCTOS")

        if is_known_product:
            qr_subtype = "product_payment"
            title = "Classify BCP QR product payment"
            desc = f"Observed {count} BCP QR notice(s) with informative glosa '{raw_glosa}'."
            confidence = Decimal("0.95")
        else:
            qr_subtype = "informative_qr"
            title = f"Classify QR subtype for '{raw_glosa}'"
            desc = f"Observed {count} BCP QR notice(s) with raw glosa '{raw_glosa}'."
            confidence = Decimal("0.85")

        predicate = {"raw_glosa": raw_glosa}
        action = {"qr_subtype": qr_subtype}

        if _is_rule_already_covered(existing_rules, predicate, action):
            continue

        suggestions.append({
            "suggestion_type": "qr_glosa_subtype",
            "title": title,
            "description": desc,
            "rule_stage": "watcher_candidate",
            "suggested_priority": 100,
            "predicate": predicate,
            "action": action,
            "evidence": {
                "pattern": "informative_qr_glosa",
                "raw_glosa": raw_glosa,
                "qr_subtype": qr_subtype,
                "occurrence_count": count,
                "sample_candidate_ids": [str(c.id) for c in cand_list[:5]],
            },
            "confidence": confidence,
            "source": "pattern_detector",
        })

    return suggestions
