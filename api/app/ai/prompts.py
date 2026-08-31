from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """You are Numa's financial assistant. Your task is to provide bounded, non-authoritative suggestions (categorization, merchant normalization, tag suggestions) for personal finance transactions and bank notice candidates.

Strict Invariants and Boundaries:
1. YOU HAVE NO FINANCIAL AUTHORITY. You MUST NOT modify transaction amounts, currencies, accounts, timestamps, or directions.
2. Categories MUST be selected ONLY from the provided allowed category list (by their UUID). If none of the allowed categories fit with confidence, return null for category_id.
3. ANTI-FABRICATION RULE: Do NOT fabricate, synthesize, or invent glosas, merchant names, or facts.
4. BCP QR RULE: For BCP QR candidates, suggest a category ONLY if an informative, non-default raw glosa is provided (e.g., 'BM BM QR PAGO DE PRODUCTOS'). If glosa is missing or is the default generic phrase ('BM BM QR INTERBANCARIA'), DO NOT invent a glosa and return null for category_id.
5. Provide your output strictly as a JSON object adhering to the specified schema.
"""


def build_candidate_prompt(
    candidate_data: dict[str, Any],
    categories: list[dict[str, Any]],
    tags: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build bounded messages for candidate suggestion."""
    categories_formatted = [
        {
            "id": str(cat["id"]),
            "name": cat["name"],
            "group": cat.get("group_name"),
        }
        for cat in categories
    ]
    tags_formatted = [t["name"] for t in (tags or [])]

    payload = {
        "candidate": candidate_data,
        "available_categories": categories_formatted,
        "available_tags": tags_formatted,
        "instructions": (
            "Analyze the candidate details (merchant, subject, glosa, amount, currency) "
            "and suggest the most appropriate category_id from available_categories, "
            "a normalized merchant name (if applicable), relevant tags, and a confidence score between 0.0 and 1.0. "
            "If the candidate is BCP QR and has missing glosa or 'BM BM QR INTERBANCARIA', category_id MUST be null. "
            "Provide reasoning explaining your selection."
        ),
    }

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
    ]


def build_transaction_prompt(
    transaction_data: dict[str, Any],
    categories: list[dict[str, Any]],
    tags: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build bounded messages for transaction categorization suggestion."""
    categories_formatted = [
        {
            "id": str(cat["id"]),
            "name": cat["name"],
            "group": cat.get("group_name"),
        }
        for cat in categories
    ]
    tags_formatted = [t["name"] for t in (tags or [])]

    payload = {
        "transaction": transaction_data,
        "available_categories": categories_formatted,
        "available_tags": tags_formatted,
        "instructions": (
            "Analyze the transaction details (merchant, memo, amount, currency, source) "
            "and suggest the most appropriate category_id from available_categories, "
            "a normalized merchant name, relevant tags, and a confidence score between 0.0 and 1.0. "
            "Provide reasoning explaining your selection."
        ),
    }

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
    ]
