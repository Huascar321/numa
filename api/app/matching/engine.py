from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re
from typing import Any
import unicodedata


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    # Normalize unicode (decompose accents)
    normalized = unicodedata.normalize("NFKD", text)
    # Remove accents
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    # Lowercase and replace non-alphanumeric with spaces
    cleaned = re.sub(r"[^\w\s]", " ", ascii_text.lower())
    # Collapse whitespace
    return " ".join(cleaned.split())


def text_token_similarity(text1: str | None, text2: str | None) -> float:
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    if not norm1 and not norm2:
        return 0.5
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0
    if norm1 in norm2 or norm2 in norm1:
        return 0.85

    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    jaccard = len(intersection) / len(union) if union else 0.0
    return min(1.0, max(0.0, jaccard))


def extract_identifiers(item: Any) -> dict[str, str]:
    """Extract all available provider identifiers and retain them."""
    identifiers: dict[str, str] = {}
    if item is None:
        return identifiers

    # If WatcherCandidate
    candidate_type = getattr(item, "candidate_type", None)
    if candidate_type == "bcp_qr":
        raw_payload = getattr(item, "raw_payload", {}) or {}
        provenance = getattr(item, "provenance", {}) or {}
        tx_id = (
            raw_payload.get("transaction_id")
            or raw_payload.get("id_transaccion")
            or provenance.get("transaction_id")
        )
        rcpt_id = (
            raw_payload.get("receipt_id")
            or raw_payload.get("nro_comprobante")
            or provenance.get("receipt_id")
        )
        msg_id = getattr(item, "message_id_header", None)
        if tx_id:
            identifiers["bcp_transaction_id"] = str(tx_id).strip()
        if rcpt_id:
            identifiers["bcp_receipt_id"] = str(rcpt_id).strip()
        if msg_id:
            identifiers["message_id"] = str(msg_id).strip()

    elif candidate_type == "binance_card":
        msg_id = getattr(item, "message_id_header", None)
        prov_uuid = getattr(item, "provider_uuid", None)
        if msg_id:
            identifiers["message_id"] = str(msg_id).strip()
        if prov_uuid:
            identifiers["provider_uuid"] = str(prov_uuid).strip()

    elif candidate_type == "banco_ganadero":
        msg_id = getattr(item, "message_id_header", None)
        if msg_id:
            identifiers["message_id"] = str(msg_id).strip()

    # If StatementRow
    compound_id = getattr(item, "compound_identity", None)
    tx_num = getattr(item, "transaction_number", None)
    if compound_id:
        identifiers["compound_identity"] = str(compound_id).strip()
    if tx_num:
        identifiers["transaction_number"] = str(tx_num).strip()

    # If Transaction
    source_meta = getattr(item, "source_metadata", {}) or {}
    provenance = getattr(item, "provenance", {}) or {}
    for key in (
        "bcp_transaction_id",
        "bcp_receipt_id",
        "transaction_id",
        "receipt_id",
        "transaction_number",
        "compound_identity",
        "message_id",
        "provider_uuid",
    ):
        val = source_meta.get(key) or provenance.get(key)
        if val:
            identifiers[key] = str(val).strip()

    return identifiers


def evaluate_identifier_signal(source: Any, target: Any) -> dict[str, Any]:
    source_ids = extract_identifiers(source)
    target_ids = extract_identifiers(target)

    matched = False
    matched_key: str | None = None
    score = 0.0

    # Check BCP QR Precedence: transaction_id > receipt_id > message_id
    src_bcp_tx = source_ids.get("bcp_transaction_id") or source_ids.get("transaction_id")
    tgt_bcp_tx = (
        target_ids.get("bcp_transaction_id")
        or target_ids.get("transaction_id")
        or target_ids.get("transaction_number")
    )
    if src_bcp_tx and tgt_bcp_tx and src_bcp_tx == tgt_bcp_tx:
        matched = True
        matched_key = "transaction_id"
        score = 1.0

    if not matched:
        src_bcp_rcpt = source_ids.get("bcp_receipt_id") or source_ids.get("receipt_id")
        tgt_bcp_rcpt = target_ids.get("bcp_receipt_id") or target_ids.get("receipt_id")
        if src_bcp_rcpt and tgt_bcp_rcpt and src_bcp_rcpt == tgt_bcp_rcpt:
            matched = True
            matched_key = "receipt_id"
            score = 0.90

    if not matched:
        src_cmp = source_ids.get("compound_identity")
        tgt_cmp = target_ids.get("compound_identity")
        if src_cmp and tgt_cmp and src_cmp == tgt_cmp:
            matched = True
            matched_key = "compound_identity"
            score = 1.0

    if not matched:
        src_tx_num = source_ids.get("transaction_number")
        tgt_tx_num = target_ids.get("transaction_number")
        if src_tx_num and tgt_tx_num and src_tx_num == tgt_tx_num:
            matched = True
            matched_key = "transaction_number"
            score = 0.95

    if not matched:
        src_msg = source_ids.get("message_id")
        tgt_msg = target_ids.get("message_id")
        if src_msg and tgt_msg and src_msg == tgt_msg:
            matched = True
            matched_key = "message_id"
            score = 0.85

    return {
        "score": score,
        "matched": matched,
        "matched_identifier": matched_key,
        "source_identifiers": source_ids,
        "target_identifiers": target_ids,
    }


def evaluate_amount_currency_signal(source: Any, target: Any) -> dict[str, Any]:
    # Extract source amount & currency
    src_amount: Decimal | None = None
    src_currency: str | None = None
    if hasattr(source, "reported_amount"):
        src_amount = Decimal(str(source.settlement_amount or source.reported_amount))
        src_currency = str(source.settlement_currency or source.reported_currency)
    elif hasattr(source, "amount"):
        src_amount = Decimal(str(source.amount))
        src_currency = getattr(source, "currency_code", None)

    # Extract target amount & currency
    tgt_amount: Decimal | None = None
    tgt_currency: str | None = None
    if hasattr(target, "amount"):
        tgt_amount = Decimal(str(target.amount))
        tgt_currency = getattr(target, "currency_code", None)

    if src_amount is None or tgt_amount is None:
        return {"score": 0.0, "matched": False, "details": "missing amount"}

    amount_matched = abs(src_amount - tgt_amount) == 0
    currency_matched = (
        (src_currency is None or tgt_currency is None)
        or (src_currency.upper() == tgt_currency.upper())
    )

    matched = amount_matched and currency_matched
    score = 1.0 if matched else 0.0
    return {
        "score": score,
        "matched": matched,
        "source_amount": str(src_amount),
        "source_currency": src_currency,
        "target_amount": str(tgt_amount),
        "target_currency": tgt_currency,
    }


def evaluate_account_signal(
    source: Any, target: Any, account_mappings: dict[str, Any] | None = None
) -> dict[str, Any]:
    src_acc_id = getattr(source, "account_id", None)
    tgt_acc_id = getattr(target, "account_id", None)

    src_meta = getattr(source, "source_metadata", {}) or {}
    tgt_meta = getattr(target, "source_metadata", {}) or {}

    src_suffix = (
        getattr(source, "account_suffix", None)
        or getattr(source, "card_suffix", None)
        or src_meta.get("card_suffix")
        or src_meta.get("account_suffix")
    )
    tgt_suffix = (
        getattr(target, "card_suffix", None)
        or getattr(target, "account_suffix", None)
        or tgt_meta.get("card_suffix")
        or tgt_meta.get("account_suffix")
    )

    tgt_text = " ".join(
        filter(
            None,
            [
                getattr(target, "memo", None),
                getattr(target, "description", None),
            ],
        )
    )

    if src_acc_id and tgt_acc_id:
        if src_acc_id == tgt_acc_id:
            return {"score": 1.0, "matched": True, "account_id": str(src_acc_id)}
        else:
            return {"score": 0.0, "matched": False, "mismatch": True}

    if src_suffix:
        if tgt_suffix and str(src_suffix).strip() == str(tgt_suffix).strip():
            return {"score": 0.85, "matched": True, "matched_suffix": str(src_suffix)}
        if tgt_text and str(src_suffix).strip() in tgt_text:
            return {"score": 0.85, "matched": True, "matched_suffix": str(src_suffix)}

    # Neutral if account is not yet specified
    return {"score": 0.50, "matched": False, "neutral": True}


def evaluate_timestamp_signal(source: Any, target: Any) -> dict[str, Any]:
    src_event_at: datetime | None = getattr(source, "event_at", None)
    src_notif_at: datetime | None = getattr(source, "notification_at", None)
    tgt_event_at: datetime | None = getattr(target, "event_at", None)

    if src_event_at is not None and tgt_event_at is not None:
        delta_sec = abs((src_event_at - tgt_event_at).total_seconds())
        if delta_sec <= 300:  # <= 5 min
            score = 1.0
        elif delta_sec <= 3600:  # <= 1 hour
            score = 0.95
        elif delta_sec <= 86400:  # <= 24 hours
            score = 0.85
        elif delta_sec <= 172800:  # <= 48 hours
            score = 0.70
        elif delta_sec <= 604800:  # <= 7 days
            score = 0.40
        else:
            score = 0.05
        return {
            "score": score,
            "matched": score >= 0.70,
            "delta_seconds": delta_sec,
            "is_authoritative": True,
            "source_event_at": src_event_at.isoformat(),
            "target_event_at": tgt_event_at.isoformat(),
        }

    # For Ganadero notice where event_at is None and only notification_at exists
    if src_notif_at is not None and tgt_event_at is not None:
        delta_sec = abs((src_notif_at - tgt_event_at).total_seconds())
        if delta_sec <= 86400:  # <= 24 hours
            score = 0.70
        elif delta_sec <= 172800:  # <= 48 hours
            score = 0.50
        elif delta_sec <= 604800:  # <= 7 days
            score = 0.40
        else:
            score = 0.10
        return {
            "score": score,
            "matched": score >= 0.40,
            "delta_seconds": delta_sec,
            "is_authoritative": False,
            "notification_at": src_notif_at.isoformat(),
            "target_event_at": tgt_event_at.isoformat(),
        }

    return {"score": 0.50, "matched": False, "delta_seconds": None, "neutral": True}



def evaluate_description_signal(source: Any, target: Any) -> dict[str, Any]:
    # Source text representations
    src_texts = [
        getattr(source, "merchant", None),
        getattr(source, "glosa", None),
        getattr(source, "description", None),
        getattr(source, "subject", None),
    ]
    # Target text representations
    tgt_texts = [
        getattr(target, "merchant", None),
        getattr(target, "memo", None),
        getattr(target, "description", None),
    ]

    best_score = 0.0
    best_pair: tuple[str, str] | None = None
    for s in src_texts:
        if not s:
            continue
        for t in tgt_texts:
            if not t:
                continue
            sim = text_token_similarity(s, t)
            if sim > best_score:
                best_score = sim
                best_pair = (s, t)

    return {
        "score": best_score,
        "matched": best_score >= 0.70,
        "best_source_text": best_pair[0] if best_pair else None,
        "best_target_text": best_pair[1] if best_pair else None,
    }


def evaluate_match_pair(
    source: Any,
    target: Any,
    account_mappings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    id_sig = evaluate_identifier_signal(source, target)
    amt_sig = evaluate_amount_currency_signal(source, target)
    acc_sig = evaluate_account_signal(source, target, account_mappings)
    time_sig = evaluate_timestamp_signal(source, target)
    desc_sig = evaluate_description_signal(source, target)

    signals = {
        "identifier": id_sig,
        "amount_currency": amt_sig,
        "account": acc_sig,
        "timestamp": time_sig,
        "description": desc_sig,
    }

    # Classification logic
    if not amt_sig["matched"]:
        confidence = Decimal("0.0000")
        classification = "NEW_TRANSACTION"

    elif id_sig["matched"] and id_sig["score"] >= 0.95:
        # Primary identifier match (BCP QR transaction_id, compound_identity, transaction_number)
        confidence = Decimal("1.0000") if id_sig["score"] == 1.0 else Decimal("0.9500")
        classification = "EXACT_MATCH"

    elif (
        acc_sig["matched"]
        and acc_sig["score"] == 1.0
        and time_sig.get("is_authoritative")
        and time_sig["score"] >= 0.85
        and desc_sig["score"] >= 0.70
    ):
        confidence = Decimal("0.9500")
        classification = "EXACT_MATCH"

    elif (
        id_sig["matched"]
        or (
            time_sig["score"] >= 0.70
            and (acc_sig["matched"] or desc_sig["score"] >= 0.70)
        )
    ):
        confidence = Decimal("0.8500")
        classification = "HIGH_CONFIDENCE_MATCH"

    elif (
        time_sig["score"] >= 0.40
        or acc_sig["matched"]
        or desc_sig["score"] >= 0.30
    ):
        # Inconclusive signals -> POSSIBLE_MATCH (requires human review, never auto-merged)
        confidence = Decimal("0.6000")
        classification = "POSSIBLE_MATCH"

    else:
        confidence = Decimal("0.3000")
        classification = "NEW_TRANSACTION"

    return {
        "classification": classification,
        "confidence_score": confidence,
        "signals": signals,
    }
