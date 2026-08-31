from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Plan
from app.accounts.service import ResourceNotFound
from app.ai.client import AIClient, AIProviderError, AIProviderUnavailableError
from app.ai.models import AIConfiguration, AISuggestion
from app.ai.prompts import build_candidate_prompt, build_transaction_prompt
from app.ai.schemas import (
    AIConfigResponse,
    AIConfigUpdate,
    AIModelOption,
    AISuggestionResponse,
    StructuredLLMSuggestion,
)
from app.ledger.models import Category, CategoryGroup, Tag, Transaction
from app.ledger.service import fingerprint, utc_now
from app.settings import Settings
from app.watchers.crypto import decrypt_token, encrypt_token, get_encryption_key
from app.watchers.models import WatcherCandidate


RECOMMENDED_MODELS: list[AIModelOption] = [
    # OpenRouter
    AIModelOption(
        id="openai/gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openrouter",
        recommended=True,
        description="Fast, inexpensive, highly capable structured classification.",
    ),
    AIModelOption(
        id="anthropic/claude-3.5-sonnet",
        name="Claude 3.5 Sonnet",
        provider="openrouter",
        recommended=False,
        description="High reasoning accuracy for complex receipts.",
    ),
    AIModelOption(
        id="meta-llama/llama-3.3-70b-instruct",
        name="Llama 3.3 70B Instruct",
        provider="openrouter",
        recommended=False,
        description="Open weights 70B model.",
    ),
    AIModelOption(
        id="google/gemini-2.0-flash-001",
        name="Gemini 2.0 Flash",
        provider="openrouter",
        recommended=False,
        description="Ultra-fast Google multi-modal model.",
    ),
    AIModelOption(
        id="gpt-oss-120b",
        name="GPT-OSS 120B",
        provider="openrouter",
        recommended=False,
        description="Configurable open-source recommended large model.",
    ),
    AIModelOption(
        id="gpt-oss-20b",
        name="GPT-OSS 20B",
        provider="openrouter",
        recommended=False,
        description="Configurable open-source recommended compact model.",
    ),
    # Groq
    AIModelOption(
        id="llama-3.3-70b-versatile",
        name="Llama 3.3 70B Versatile",
        provider="groq",
        recommended=True,
        description="Fast inference with strict structured outputs on Groq LPU.",
    ),
    AIModelOption(
        id="llama-3.1-8b-instant",
        name="Llama 3.1 8B Instant",
        provider="groq",
        recommended=False,
        description="Instant low-latency model.",
    ),
    AIModelOption(
        id="mixtral-8x7b-32768",
        name="Mixtral 8x7B",
        provider="groq",
        recommended=False,
        description="Fast MoE model.",
    ),
]


def _require_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} does not exist.")
    return plan


def get_or_create_ai_config(
    session: Session, plan_id: UUID, settings: Settings
) -> AIConfiguration:
    _require_plan(session, plan_id)
    config = session.scalar(
        select(AIConfiguration).where(AIConfiguration.plan_id == plan_id)
    )
    if config is None:
        config = AIConfiguration(
            id=uuid4(),
            plan_id=plan_id,
            provider="openrouter",
            model="openai/gpt-4o-mini",
            encrypted_api_key=None,
            is_enabled=False,
            base_url=None,
            settings={},
            creation_fingerprint=fingerprint({"plan_id": str(plan_id), "scope": "ai_config"}),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(config)
        session.flush()
    return config


def get_ai_config(
    session: Session, plan_id: UUID, settings: Settings
) -> AIConfigResponse:
    config = get_or_create_ai_config(session, plan_id, settings)
    has_key = bool(config.encrypted_api_key)
    masked_key = "••••••••" if has_key else None
    return AIConfigResponse(
        id=config.id,
        plan_id=config.plan_id,
        provider=config.provider,
        model=config.model,
        has_api_key=has_key,
        masked_api_key=masked_key,
        is_enabled=config.is_enabled,
        base_url=config.base_url,
        settings=config.settings,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def update_ai_config(
    session: Session, plan_id: UUID, payload: AIConfigUpdate, settings: Settings
) -> AIConfigResponse:
    config = get_or_create_ai_config(session, plan_id, settings)

    if payload.provider is not None:
        if payload.provider not in ("openrouter", "groq", "custom"):
            raise ValueError(f"Unsupported provider '{payload.provider}'")
        config.provider = payload.provider

    if payload.model is not None:
        if not payload.model.strip():
            raise ValueError("Model name must not be empty.")
        config.model = payload.model.strip()

    if payload.clear_api_key:
        config.encrypted_api_key = None
    elif payload.api_key is not None and payload.api_key.strip():
        enc_key = get_encryption_key(settings)
        config.encrypted_api_key = encrypt_token(payload.api_key.strip(), enc_key)

    if payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled

    if payload.base_url is not None:
        config.base_url = payload.base_url.strip() if payload.base_url.strip() else None

    if payload.settings is not None:
        config.settings = payload.settings

    config.updated_at = utc_now()
    session.flush()

    return get_ai_config(session, plan_id, settings)


def get_recommended_models(provider: str | None = None) -> list[AIModelOption]:
    if provider:
        return [m for m in RECOMMENDED_MODELS if m.provider == provider]
    return RECOMMENDED_MODELS


def _build_suggestion_response(suggestion: AISuggestion) -> AISuggestionResponse:
    return AISuggestionResponse(
        id=suggestion.id,
        plan_id=suggestion.plan_id,
        candidate_id=suggestion.candidate_id,
        transaction_id=suggestion.transaction_id,
        suggestion_type=suggestion.suggestion_type,
        status=suggestion.status,
        suggested_category_id=suggestion.suggested_category_id,
        suggested_merchant=suggestion.suggested_merchant,
        suggested_glosa=suggestion.suggested_glosa,
        suggested_tags=suggestion.suggested_tags,
        confidence=suggestion.confidence,
        reasoning=suggestion.reasoning,
        validation_errors=suggestion.validation_errors,
        provenance=suggestion.provenance,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


def generate_candidate_suggestion(
    session: Session,
    plan_id: UUID,
    candidate_id: UUID,
    settings: Settings,
    ai_client: AIClient | None = None,
) -> AISuggestionResponse:
    """Generate bounded AI suggestions for a bank/card watcher candidate."""
    _require_plan(session, plan_id)
    candidate = session.scalar(
        select(WatcherCandidate).where(
            WatcherCandidate.plan_id == plan_id,
            WatcherCandidate.id == candidate_id,
        )
    )
    if candidate is None:
        raise ResourceNotFound(f"Watcher candidate {candidate_id} not found.")

    config = get_or_create_ai_config(session, plan_id, settings)
    if not config.is_enabled or not config.encrypted_api_key:
        raise ValueError("AI is disabled or unconfigured for this plan.")

    # BCP QR Glosa boundary check
    if candidate.candidate_type == "bcp_qr":
        raw_g = (candidate.raw_glosa or candidate.glosa or "").strip()
        is_default_or_empty = (
            not raw_g or raw_g.upper() == "BM BM QR INTERBANCARIA"
        )
        if is_default_or_empty:
            # AI MUST NOT invent glosa or generate an ungrounded category suggestion
            suggestion = AISuggestion(
                id=uuid4(),
                plan_id=plan_id,
                candidate_id=candidate.id,
                transaction_id=None,
                suggestion_type="categorization",
                status="suggested",
                suggested_category_id=None,
                suggested_merchant=candidate.merchant,
                suggested_glosa=candidate.glosa or candidate.raw_glosa,
                suggested_tags=[],
                confidence=Decimal("0.0"),
                reasoning=(
                    "BCP QR candidate has missing or default non-informative glosa ('BM BM QR INTERBANCARIA'). "
                    "Category inference is omitted per bounded anti-fabrication rules."
                ),
                raw_prompt="[bcp_qr_glosa_boundary_applied]",
                raw_response={"glosa_boundary": True, "category_id": None},
                validation_errors=None,
                provenance={
                    "provider": config.provider,
                    "model": config.model,
                    "glosa_boundary_applied": True,
                },
                creation_fingerprint=fingerprint({
                    "plan_id": str(plan_id),
                    "candidate_id": str(candidate_id),
                    "glosa_boundary": True,
                    "now": utc_now().isoformat(),
                }),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(suggestion)
            session.flush()
            return _build_suggestion_response(suggestion)

    # Active categories and tags
    categories = session.scalars(
        select(Category).where(
            Category.plan_id == plan_id,
            Category.status == "active",
        )
    ).all()
    category_groups = {
        g.id: g.name
        for g in session.scalars(
            select(CategoryGroup).where(CategoryGroup.plan_id == plan_id)
        ).all()
    }
    categories_data = [
        {
            "id": c.id,
            "name": c.name,
            "group_name": category_groups.get(c.group_id) if c.group_id else None,
        }
        for c in categories
    ]
    valid_cat_ids = {c.id for c in categories}

    tags = session.scalars(
        select(Tag).where(Tag.plan_id == plan_id, Tag.status == "active")
    ).all()
    tags_data = [{"id": t.id, "name": t.name} for t in tags]

    candidate_data = {
        "id": str(candidate.id),
        "candidate_type": candidate.candidate_type,
        "reported_amount": str(candidate.reported_amount),
        "reported_currency": candidate.reported_currency,
        "merchant": candidate.merchant,
        "subject": candidate.subject,
        "glosa": candidate.glosa or candidate.raw_glosa,
        "direction": candidate.direction,
    }

    messages = build_candidate_prompt(candidate_data, categories_data, tags_data)
    client = ai_client or AIClient()
    decrypted_key = decrypt_token(config.encrypted_api_key, get_encryption_key(settings))

    raw_output: dict[str, Any] | None = None
    validation_errors: dict[str, Any] | None = None
    parsed: StructuredLLMSuggestion | None = None

    try:
        raw_output = client.generate_structured_completion(
            provider=config.provider,
            model=config.model,
            api_key=decrypted_key,
            messages=messages,
            base_url=config.base_url,
        )
        parsed = StructuredLLMSuggestion.model_validate(raw_output)
    except ValidationError as err:
        validation_errors = {"error": "Pydantic validation error", "details": err.errors()}
    except (AIProviderUnavailableError, AIProviderError) as exc:
        raise ValueError(f"AI Provider error: {exc}") from exc
    except Exception as exc:
        validation_errors = {"error": "Unexpected output formatting error", "details": str(exc)}

    # If parsing failed, record quarantined suggestion
    if parsed is None:
        suggestion = AISuggestion(
            id=uuid4(),
            plan_id=plan_id,
            candidate_id=candidate.id,
            transaction_id=None,
            suggestion_type="categorization",
            status="quarantined",
            suggested_category_id=None,
            suggested_merchant=None,
            suggested_glosa=None,
            suggested_tags=[],
            confidence=Decimal("0.0"),
            reasoning="AI output failed local JSON-schema validation.",
            raw_prompt=messages[-1]["content"],
            raw_response=raw_output,
            validation_errors=validation_errors,
            provenance={"provider": config.provider, "model": config.model},
            creation_fingerprint=fingerprint({
                "plan_id": str(plan_id),
                "candidate_id": str(candidate_id),
                "quarantined": True,
                "now": utc_now().isoformat(),
            }),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(suggestion)
        session.flush()
        return _build_suggestion_response(suggestion)

    # Valid schema output: check category ID boundary
    suggested_cat_id: UUID | None = None
    if parsed.category_id:
        try:
            candidate_cat_uuid = UUID(parsed.category_id)
            if candidate_cat_uuid in valid_cat_ids:
                suggested_cat_id = candidate_cat_uuid
            else:
                validation_errors = {
                    "warning": f"Suggested category_id {parsed.category_id} is not an active category of this plan."
                }
        except ValueError:
            validation_errors = {"warning": f"Invalid UUID format for category_id: {parsed.category_id}"}

    conf_score = (
        Decimal(str(round(parsed.confidence, 4)))
        if parsed.confidence is not None
        else Decimal("0.8000")
    )

    suggestion = AISuggestion(
        id=uuid4(),
        plan_id=plan_id,
        candidate_id=candidate.id,
        transaction_id=None,
        suggestion_type="categorization",
        status="suggested",
        suggested_category_id=suggested_cat_id,
        suggested_merchant=parsed.merchant or candidate.merchant,
        suggested_glosa=parsed.glosa or candidate.glosa or candidate.raw_glosa,
        suggested_tags=parsed.tags,
        confidence=conf_score,
        reasoning=parsed.reasoning,
        raw_prompt=messages[-1]["content"],
        raw_response=raw_output,
        validation_errors=validation_errors,
        provenance={"provider": config.provider, "model": config.model},
        creation_fingerprint=fingerprint({
            "plan_id": str(plan_id),
            "candidate_id": str(candidate_id),
            "now": utc_now().isoformat(),
        }),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(suggestion)
    session.flush()
    return _build_suggestion_response(suggestion)


def generate_transaction_suggestion(
    session: Session,
    plan_id: UUID,
    transaction_id: UUID,
    settings: Settings,
    ai_client: AIClient | None = None,
) -> AISuggestionResponse:
    """Generate bounded AI suggestions for an existing ledger transaction."""
    _require_plan(session, plan_id)
    txn = session.scalar(
        select(Transaction).where(
            Transaction.plan_id == plan_id,
            Transaction.id == transaction_id,
        )
    )
    if txn is None:
        raise ResourceNotFound(f"Transaction {transaction_id} not found.")

    config = get_or_create_ai_config(session, plan_id, settings)
    if not config.is_enabled or not config.encrypted_api_key:
        raise ValueError("AI is disabled or unconfigured for this plan.")

    categories = session.scalars(
        select(Category).where(
            Category.plan_id == plan_id,
            Category.status == "active",
        )
    ).all()
    category_groups = {
        g.id: g.name
        for g in session.scalars(
            select(CategoryGroup).where(CategoryGroup.plan_id == plan_id)
        ).all()
    }
    categories_data = [
        {
            "id": c.id,
            "name": c.name,
            "group_name": category_groups.get(c.group_id) if c.group_id else None,
        }
        for c in categories
    ]
    valid_cat_ids = {c.id for c in categories}

    tags = session.scalars(
        select(Tag).where(Tag.plan_id == plan_id, Tag.status == "active")
    ).all()
    tags_data = [{"id": t.id, "name": t.name} for t in tags]

    transaction_data = {
        "id": str(txn.id),
        "type": txn.type,
        "amount": str(txn.amount),
        "currency_code": txn.currency_code,
        "merchant": txn.merchant,
        "memo": txn.memo,
        "source": txn.source,
    }

    messages = build_transaction_prompt(transaction_data, categories_data, tags_data)
    client = ai_client or AIClient()
    decrypted_key = decrypt_token(config.encrypted_api_key, get_encryption_key(settings))

    raw_output: dict[str, Any] | None = None
    validation_errors: dict[str, Any] | None = None
    parsed: StructuredLLMSuggestion | None = None

    try:
        raw_output = client.generate_structured_completion(
            provider=config.provider,
            model=config.model,
            api_key=decrypted_key,
            messages=messages,
            base_url=config.base_url,
        )
        parsed = StructuredLLMSuggestion.model_validate(raw_output)
    except ValidationError as err:
        validation_errors = {"error": "Pydantic validation error", "details": err.errors()}
    except (AIProviderUnavailableError, AIProviderError) as exc:
        raise ValueError(f"AI Provider error: {exc}") from exc
    except Exception as exc:
        validation_errors = {"error": "Unexpected output formatting error", "details": str(exc)}

    if parsed is None:
        suggestion = AISuggestion(
            id=uuid4(),
            plan_id=plan_id,
            candidate_id=None,
            transaction_id=txn.id,
            suggestion_type="categorization",
            status="quarantined",
            suggested_category_id=None,
            suggested_merchant=None,
            suggested_glosa=None,
            suggested_tags=[],
            confidence=Decimal("0.0"),
            reasoning="AI output failed local JSON-schema validation.",
            raw_prompt=messages[-1]["content"],
            raw_response=raw_output,
            validation_errors=validation_errors,
            provenance={"provider": config.provider, "model": config.model},
            creation_fingerprint=fingerprint({
                "plan_id": str(plan_id),
                "transaction_id": str(transaction_id),
                "quarantined": True,
                "now": utc_now().isoformat(),
            }),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(suggestion)
        session.flush()
        return _build_suggestion_response(suggestion)

    suggested_cat_id: UUID | None = None
    if parsed.category_id:
        try:
            parsed_uuid = UUID(parsed.category_id)
            if parsed_uuid in valid_cat_ids:
                suggested_cat_id = parsed_uuid
            else:
                validation_errors = {
                    "warning": f"Suggested category_id {parsed.category_id} is not an active category of this plan."
                }
        except ValueError:
            validation_errors = {"warning": f"Invalid UUID format for category_id: {parsed.category_id}"}

    conf_score = (
        Decimal(str(round(parsed.confidence, 4)))
        if parsed.confidence is not None
        else Decimal("0.8000")
    )

    suggestion = AISuggestion(
        id=uuid4(),
        plan_id=plan_id,
        candidate_id=None,
        transaction_id=txn.id,
        suggestion_type="categorization",
        status="suggested",
        suggested_category_id=suggested_cat_id,
        suggested_merchant=parsed.merchant or txn.merchant,
        suggested_glosa=parsed.glosa or txn.memo,
        suggested_tags=parsed.tags,
        confidence=conf_score,
        reasoning=parsed.reasoning,
        raw_prompt=messages[-1]["content"],
        raw_response=raw_output,
        validation_errors=validation_errors,
        provenance={"provider": config.provider, "model": config.model},
        creation_fingerprint=fingerprint({
            "plan_id": str(plan_id),
            "transaction_id": str(transaction_id),
            "now": utc_now().isoformat(),
        }),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(suggestion)
    session.flush()
    return _build_suggestion_response(suggestion)


def list_ai_suggestions(
    session: Session,
    plan_id: UUID,
    status: str | None = None,
    candidate_id: UUID | None = None,
    transaction_id: UUID | None = None,
) -> list[AISuggestionResponse]:
    _require_plan(session, plan_id)
    stmt = select(AISuggestion).where(AISuggestion.plan_id == plan_id)
    if status:
        stmt = stmt.where(AISuggestion.status == status)
    if candidate_id:
        stmt = stmt.where(AISuggestion.candidate_id == candidate_id)
    if transaction_id:
        stmt = stmt.where(AISuggestion.transaction_id == transaction_id)
    stmt = stmt.order_by(AISuggestion.created_at.desc())

    suggestions = session.scalars(stmt).all()
    return [_build_suggestion_response(s) for s in suggestions]


def get_ai_suggestion(
    session: Session, plan_id: UUID, suggestion_id: UUID
) -> AISuggestionResponse:
    _require_plan(session, plan_id)
    suggestion = session.scalar(
        select(AISuggestion).where(
            AISuggestion.plan_id == plan_id,
            AISuggestion.id == suggestion_id,
        )
    )
    if suggestion is None:
        raise ResourceNotFound(f"AI suggestion {suggestion_id} not found.")
    return _build_suggestion_response(suggestion)


def accept_ai_suggestion(
    session: Session, plan_id: UUID, suggestion_id: UUID
) -> AISuggestionResponse:
    """Accept an AI suggestion, applying non-financial metadata (category/merchant/tags)."""
    _require_plan(session, plan_id)
    suggestion = session.scalar(
        select(AISuggestion).where(
            AISuggestion.plan_id == plan_id,
            AISuggestion.id == suggestion_id,
        )
    )
    if suggestion is None:
        raise ResourceNotFound(f"AI suggestion {suggestion_id} not found.")
    if suggestion.status != "suggested":
        raise ValueError(f"Cannot accept suggestion in '{suggestion.status}' status.")

    # Invariant: AI MUST NEVER mutate amounts, currencies, target accounts, timestamps, or directions!
    if suggestion.candidate_id:
        candidate = session.scalar(
            select(WatcherCandidate).where(
                WatcherCandidate.plan_id == plan_id,
                WatcherCandidate.id == suggestion.candidate_id,
            )
        )
        if candidate:
            if suggestion.suggested_merchant and not candidate.merchant:
                candidate.merchant = suggestion.suggested_merchant
            # Add to rule_evidence/provenance
            candidate.rule_evidence = [
                *candidate.rule_evidence,
                {
                    "rule_name": "ai_suggestion_applied",
                    "result": "accepted",
                    "category_id": str(suggestion.suggested_category_id)
                    if suggestion.suggested_category_id
                    else None,
                    "merchant": suggestion.suggested_merchant,
                },
            ]
            candidate.updated_at = utc_now()

    if suggestion.transaction_id:
        txn = session.scalar(
            select(Transaction).where(
                Transaction.plan_id == plan_id,
                Transaction.id == suggestion.transaction_id,
            )
        )
        if txn:
            if suggestion.suggested_category_id:
                txn.category_id = suggestion.suggested_category_id
            if suggestion.suggested_merchant and not txn.merchant:
                txn.merchant = suggestion.suggested_merchant
            txn.updated_at = utc_now()

    suggestion.status = "accepted"
    suggestion.updated_at = utc_now()
    session.flush()
    return _build_suggestion_response(suggestion)


def reject_ai_suggestion(
    session: Session, plan_id: UUID, suggestion_id: UUID, reason: str | None = None
) -> AISuggestionResponse:
    """Reject/dismiss an AI suggestion."""
    _require_plan(session, plan_id)
    suggestion = session.scalar(
        select(AISuggestion).where(
            AISuggestion.plan_id == plan_id,
            AISuggestion.id == suggestion_id,
        )
    )
    if suggestion is None:
        raise ResourceNotFound(f"AI suggestion {suggestion_id} not found.")
    if suggestion.status not in ("suggested", "quarantined"):
        raise ValueError(f"Cannot reject suggestion in '{suggestion.status}' status.")

    suggestion.status = "rejected"
    if reason:
        suggestion.reasoning = f"{suggestion.reasoning or ''} (Dismissed: {reason})".strip()
    suggestion.updated_at = utc_now()
    session.flush()
    return _build_suggestion_response(suggestion)
