from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import fnmatch
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account, Plan
from app.accounts.service import ResourceNotFound
from app.ledger.models import Category
from app.ledger.schemas import TransactionCreate
from app.ledger.service import _pending_category, _require_active_category, create_transaction
from app.settings import Settings
from app.rules.models import Rule
from app.rules.service import apply_rules_to_candidate, list_rules
from app.watchers.bcp_qr import parse_bcp_qr_message
from app.watchers.binance_card import parse_binance_card_message
from app.watchers.crypto import decrypt_token, encrypt_token, get_encryption_key
from app.watchers.email_decoder import decode_gmail_message_payload
from app.watchers.ganadero import parse_banco_ganadero_message
from app.watchers.gmail_client import (
    GmailClient,
    GmailHistoryExpiredError,
    GmailNotConfiguredError,
)
from app.watchers.models import (
    WatcherAccountMapping,
    WatcherCandidate,
    WatcherRawMessage,
    WatcherSource,
)
from app.watchers.schemas import (
    ConnectGmailRequest,
    CreateAccountMappingRequest,
    ProcessCandidatesResponse,
    ResolveCandidateRequest,
    SyncResultResponse,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} does not exist.")
    return plan


def get_gmail_auth_url(
    session: Session,
    settings: Settings,
    plan_id: UUID,
    redirect_uri: str,
    client: GmailClient | None = None,
) -> str:
    """Generate the OAuth authorization URL for connecting a Gmail account to a Plan."""
    _require_plan(session, plan_id)
    gmail_client = client or GmailClient(settings)
    state = f"plan:{plan_id}:{uuid4()}"
    return gmail_client.build_auth_url(redirect_uri, state=state)


def connect_gmail(
    session: Session,
    settings: Settings,
    plan_id: UUID,
    payload: ConnectGmailRequest,
    client: GmailClient | None = None,
) -> WatcherSource:
    """Exchange authorization code, encrypt refresh token, and create/update WatcherSource.

    Password collection is strictly forbidden.
    """
    if payload.password is not None:
        raise ValueError("Password collection is strictly prohibited.")

    _require_plan(session, plan_id)
    gmail_client = client or GmailClient(settings)

    tokens = gmail_client.exchange_code_for_tokens(
        payload.code,
        payload.redirect_uri,
        password=payload.password,
    )
    access_token = str(tokens["access_token"])
    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        # If Google didn't return a refresh_token, we can't do offline background sync
        raise ValueError(
            "Google did not return a refresh token. Ensure consent prompt was approved."
        )

    profile = gmail_client.get_user_profile(access_token)
    email_address = str(profile.get("emailAddress", "")).strip().lower()
    if not email_address:
        raise ValueError("Failed to retrieve email address from Google profile.")

    encryption_key = get_encryption_key(settings)
    encrypted_refresh_token = encrypt_token(refresh_token, encryption_key)

    existing_source = session.scalar(
        select(WatcherSource).where(
            WatcherSource.plan_id == plan_id,
            WatcherSource.source_type == "gmail",
            WatcherSource.email_address == email_address,
        )
    )

    now = utc_now()
    if existing_source is not None:
        existing_source.encrypted_refresh_token = encrypted_refresh_token
        existing_source.status = "active"
        existing_source.last_error = None
        existing_source.updated_at = now
        session.flush()
        return existing_source

    source = WatcherSource(
        id=uuid4(),
        plan_id=plan_id,
        source_type="gmail",
        email_address=email_address,
        encrypted_refresh_token=encrypted_refresh_token,
        history_id=None,
        status="active",
        creation_fingerprint=f"gmail:{email_address}",
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    session.flush()
    return source


def list_watcher_sources(session: Session, plan_id: UUID) -> list[WatcherSource]:
    _require_plan(session, plan_id)
    return list(
        session.scalars(
            select(WatcherSource)
            .where(WatcherSource.plan_id == plan_id)
            .order_by(WatcherSource.created_at)
        ).all()
    )


def get_watcher_source(session: Session, plan_id: UUID, source_id: UUID) -> WatcherSource:
    _require_plan(session, plan_id)
    source = session.scalar(
        select(WatcherSource).where(
            WatcherSource.plan_id == plan_id,
            WatcherSource.id == source_id,
        )
    )
    if source is None:
        raise ResourceNotFound(f"Watcher source {source_id} does not exist.")
    return source


def disconnect_watcher_source(
    session: Session,
    plan_id: UUID,
    source_id: UUID,
) -> WatcherSource:
    source = get_watcher_source(session, plan_id, source_id)
    source.status = "disconnected"
    source.encrypted_refresh_token = ""
    source.updated_at = utc_now()
    session.flush()
    return source


def sync_watcher_source(
    session: Session,
    settings: Settings,
    plan_id: UUID,
    source_id: UUID,
    client: GmailClient | None = None,
) -> SyncResultResponse:
    """Perform synchronization of a Gmail watcher source with 404 History recovery."""
    source = get_watcher_source(session, plan_id, source_id)
    if source.status == "disconnected":
        raise ValueError("Cannot sync a disconnected watcher source.")

    encryption_key = get_encryption_key(settings)
    refresh_token = decrypt_token(source.encrypted_refresh_token, encryption_key)

    gmail_client = client or GmailClient(settings)
    access_token = gmail_client.refresh_access_token(refresh_token)

    message_ids_to_fetch: set[str] = set()
    latest_history_id: str | None = None

    if source.history_id is None:
        # Full sync
        msg_list_resp = gmail_client.list_messages(access_token)
        for msg in msg_list_resp.get("messages", []):
            if "id" in msg:
                message_ids_to_fetch.add(str(msg["id"]))
        profile = gmail_client.get_user_profile(access_token)
        latest_history_id = str(profile.get("historyId", "")) or None
    else:
        # Incremental history sync
        try:
            hist_resp = gmail_client.list_history(
                access_token,
                start_history_id=source.history_id,
            )
            for item in hist_resp.get("history", []):
                for msg in item.get("messagesAdded", []):
                    if "message" in msg and "id" in msg["message"]:
                        message_ids_to_fetch.add(str(msg["message"]["id"]))
                for msg in item.get("messages", []):
                    if "id" in msg:
                        message_ids_to_fetch.add(str(msg["id"]))
            latest_history_id = str(hist_resp.get("historyId", source.history_id))
        except GmailHistoryExpiredError:
            # History cursor 404 recovery: reset cursor and perform full resync
            source.history_id = None
            msg_list_resp = gmail_client.list_messages(access_token)
            for msg in msg_list_resp.get("messages", []):
                if "id" in msg:
                    message_ids_to_fetch.add(str(msg["id"]))
            profile = gmail_client.get_user_profile(access_token)
            latest_history_id = str(profile.get("historyId", "")) or None

    new_messages_count = 0
    now = utc_now()

    for msg_id in message_ids_to_fetch:
        # Idempotent raw message ingestion
        existing = session.scalar(
            select(WatcherRawMessage).where(
                WatcherRawMessage.source_id == source.id,
                WatcherRawMessage.external_message_id == msg_id,
            )
        )
        if existing is not None:
            continue

        raw_msg_data = gmail_client.get_message(access_token, msg_id, format_type="full")
        decoded = decode_gmail_message_payload(raw_msg_data)

        raw_message = WatcherRawMessage(
            id=uuid4(),
            plan_id=plan_id,
            source_id=source.id,
            external_message_id=msg_id,
            external_thread_id=raw_msg_data.get("threadId"),
            internal_date=decoded.internal_date,
            history_id=str(raw_msg_data.get("historyId", "")) or None,
            sender=decoded.sender,
            recipient=decoded.recipient,
            subject=decoded.subject,
            snippet=decoded.snippet,
            raw_headers=decoded.raw_headers,
            body_plain=decoded.body_plain,
            body_html=decoded.body_html,
            mime_metadata=decoded.mime_metadata,
            provenance=decoded.provenance,
            status="pending",
            creation_fingerprint=f"{source.id}:{msg_id}",
            created_at=now,
        )
        session.add(raw_message)
        session.flush()
        new_messages_count += 1

        # Automatically process message through Candidate parsers and Rules
        process_raw_message_for_candidates(session, raw_message)

    source.history_id = latest_history_id
    source.last_sync_at = now
    source.last_error = None
    source.updated_at = now
    session.flush()

    return SyncResultResponse(
        synced_count=len(message_ids_to_fetch),
        new_messages_count=new_messages_count,
        history_id=latest_history_id,
    )


def list_watcher_raw_messages(
    session: Session,
    plan_id: UUID,
    source_id: UUID | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[WatcherRawMessage]:
    _require_plan(session, plan_id)
    query = select(WatcherRawMessage).where(WatcherRawMessage.plan_id == plan_id)
    if source_id is not None:
        query = query.where(WatcherRawMessage.source_id == source_id)
    if status is not None:
        query = query.where(WatcherRawMessage.status == status)
    query = query.order_by(WatcherRawMessage.created_at.desc()).limit(limit)
    return list(session.scalars(query).all())


def get_watcher_raw_message(
    session: Session,
    plan_id: UUID,
    message_id: UUID,
) -> WatcherRawMessage:
    _require_plan(session, plan_id)
    msg = session.scalar(
        select(WatcherRawMessage).where(
            WatcherRawMessage.plan_id == plan_id,
            WatcherRawMessage.id == message_id,
        )
    )
    if msg is None:
        raise ResourceNotFound(f"Watcher raw message {message_id} does not exist.")
    return msg


# ---------------------------------------------------------------------------
# Watcher Candidates & Parsers Integration Logic
# ---------------------------------------------------------------------------


def find_matching_account_mapping(
    session: Session,
    plan_id: UUID,
    source_type: str,
    pattern_val: str | None,
) -> WatcherAccountMapping | None:
    """Find the best matching authoritative account mapping for a plan."""
    mappings = list(
        session.scalars(
            select(WatcherAccountMapping).where(
                WatcherAccountMapping.plan_id == plan_id,
                WatcherAccountMapping.source_type == source_type,
            )
        ).all()
    )
    if not mappings:
        return None

    # Exact or glob match on pattern_val
    if pattern_val:
        clean_val = pattern_val.strip().lower()
        for mapping in mappings:
            p = mapping.pattern.strip().lower()
            if p != "*" and (p == clean_val or fnmatch.fnmatch(clean_val, p)):
                return mapping

    # Fallback to wildcard '*' mapping
    for mapping in mappings:
        if mapping.pattern.strip() == "*":
            return mapping

    return None


def process_raw_message_for_candidates(
    session: Session,
    raw_message: WatcherRawMessage,
) -> WatcherCandidate | None:
    """Parse raw message into a WatcherCandidate using Binance, Ganadero, or BCP QR parser, then apply rules."""
    # Check if already processed idempotently
    existing_candidate = session.scalar(
        select(WatcherCandidate).where(
            WatcherCandidate.raw_message_id == raw_message.id
        )
    )
    if existing_candidate is not None:
        return existing_candidate

    rules = list_rules(session, raw_message.plan_id, stage="watcher_candidate", enabled=True)
    now = utc_now()
    candidate_id = uuid4()

    # 1. Try Binance Card
    parsed_binance = parse_binance_card_message(raw_message)
    if parsed_binance.is_binance_card:
        assert parsed_binance.reported_amount is not None
        assert parsed_binance.reported_currency is not None
        assert parsed_binance.event_at is not None

        candidate = WatcherCandidate(
            id=candidate_id,
            plan_id=raw_message.plan_id,
            raw_message_id=raw_message.id,
            source_id=raw_message.source_id,
            candidate_type="binance_card",
            status="pending",
            event_at=parsed_binance.event_at,
            notification_at=parsed_binance.notification_at,
            reported_amount=parsed_binance.reported_amount,
            reported_currency=parsed_binance.reported_currency,
            settlement_amount=None,
            settlement_currency=None,
            merchant=parsed_binance.merchant,
            subject=raw_message.subject,
            sender=raw_message.sender,
            provider_uuid=parsed_binance.provider_uuid,
            message_id_header=parsed_binance.message_id_header,
            quarantine_reason=None,
            rule_evidence=[],
            glosa=None,
            raw_glosa=None,
            qr_subtype=None,
            account_suffix=None,
            direction=None,
            raw_payload={
                "body_plain": raw_message.body_plain,
                "snippet": raw_message.snippet,
            },
            provenance={
                "source": "watcher:binance_card",
                "raw_message_id": str(raw_message.id),
                "external_message_id": raw_message.external_message_id,
                "message_id": parsed_binance.message_id_header,
                "date_header": raw_message.raw_headers.get("date"),
                "provider_uuid": parsed_binance.provider_uuid,
            },
            transaction_id=None,
            creation_fingerprint=f"binance_card:{raw_message.id}",
            created_at=now,
            updated_at=now,
        )
        session.add(candidate)
        session.flush()

        # Apply deterministic rules
        apply_rules_to_candidate(session, candidate, rules)

        if candidate.status not in {"resolved", "quarantined"}:
            # Fall back to account mapping
            mapping = find_matching_account_mapping(
                session=session,
                plan_id=raw_message.plan_id,
                source_type="binance_card",
                pattern_val=parsed_binance.merchant,
            )
            if mapping is None:
                candidate.status = "quarantined"
                candidate.quarantine_reason = (
                    "Settlement unresolved: reported USD requires authoritative account mapping or manual review."
                )
            else:
                account = session.scalar(
                    select(Account).where(
                        Account.plan_id == raw_message.plan_id,
                        Account.id == mapping.account_id,
                        Account.status == "active",
                    )
                )
                if account is None:
                    candidate.status = "quarantined"
                    candidate.quarantine_reason = f"Mapped account {mapping.account_id} is missing or inactive."
                elif mapping.auto_resolve:
                    category = (
                        session.get(Category, mapping.default_category_id)
                        if mapping.default_category_id
                        else _pending_category(session, raw_message.plan_id)
                    )
                    if category is None or category.plan_id != raw_message.plan_id:
                        category = _pending_category(session, raw_message.plan_id)

                    tx_id = uuid4()
                    tx_payload = TransactionCreate(
                        type="expense",
                        account_id=account.id,
                        amount=str(parsed_binance.reported_amount),
                        currency_code=account.currency_code,
                        event_at=parsed_binance.event_at,
                        category_id=category.id,
                        merchant=parsed_binance.merchant,
                        memo=f"Binance Card spent {parsed_binance.reported_amount} {parsed_binance.reported_currency}",
                        tags=[],
                        source_metadata={
                            "candidate_id": str(candidate_id),
                            "candidate_type": "binance_card",
                            "reported_amount": str(parsed_binance.reported_amount),
                            "reported_currency": parsed_binance.reported_currency,
                            "provider_uuid": parsed_binance.provider_uuid,
                        },
                        provenance={
                            "source": "watcher:binance_card",
                            "raw_message_id": str(raw_message.id),
                            "message_id": parsed_binance.message_id_header,
                            "mapping_id": str(mapping.id),
                            "auto_resolved": True,
                        },
                    )
                    tx_result = create_transaction(
                        session=session,
                        plan_id=raw_message.plan_id,
                        transaction_id=tx_id,
                        payload=tx_payload,
                    )
                    candidate.status = "resolved"
                    candidate.settlement_amount = parsed_binance.reported_amount
                    candidate.settlement_currency = account.currency_code
                    candidate.transaction_id = tx_result.resource.id
                else:
                    candidate.status = "pending"

        raw_message.status = "quarantined" if candidate.status == "quarantined" else "parsed"
        session.flush()
        return candidate

    # 2. Try Banco Ganadero
    parsed_ganadero = parse_banco_ganadero_message(raw_message)
    if parsed_ganadero.is_banco_ganadero:
        assert parsed_ganadero.reported_amount is not None

        candidate = WatcherCandidate(
            id=candidate_id,
            plan_id=raw_message.plan_id,
            raw_message_id=raw_message.id,
            source_id=raw_message.source_id,
            candidate_type="banco_ganadero",
            status="pending",
            event_at=None,  # Explicitly null per specification
            notification_at=parsed_ganadero.notification_at,
            reported_amount=parsed_ganadero.reported_amount,
            reported_currency="BOB",
            settlement_amount=None,
            settlement_currency=None,
            merchant=None,
            subject=raw_message.subject,
            sender=raw_message.sender,
            provider_uuid=None,
            message_id_header=parsed_ganadero.message_id_header,
            quarantine_reason=None,
            rule_evidence=[],
            glosa=None,
            raw_glosa=None,
            qr_subtype=None,
            account_suffix=parsed_ganadero.account_suffix,
            direction=parsed_ganadero.direction,
            raw_payload={
                "body_plain": raw_message.body_plain,
                "snippet": raw_message.snippet,
                "raw_token": parsed_ganadero.raw_currency_token,
            },
            provenance={
                "source": "watcher:banco_ganadero",
                "raw_message_id": str(raw_message.id),
                "external_message_id": raw_message.external_message_id,
                "message_id": parsed_ganadero.message_id_header,
                "raw_token": parsed_ganadero.raw_currency_token,
                "direction": parsed_ganadero.direction,
                "account_suffix": parsed_ganadero.account_suffix,
            },
            transaction_id=None,
            creation_fingerprint=f"banco_ganadero:{raw_message.id}",
            created_at=now,
            updated_at=now,
        )
        session.add(candidate)
        session.flush()

        apply_rules_to_candidate(session, candidate, rules)
        raw_message.status = "quarantined" if candidate.status == "quarantined" else "parsed"
        session.flush()
        return candidate

    # 3. Try BCP QR
    parsed_bcp = parse_bcp_qr_message(raw_message)
    if parsed_bcp.is_bcp_qr:
        assert parsed_bcp.reported_amount is not None

        candidate = WatcherCandidate(
            id=candidate_id,
            plan_id=raw_message.plan_id,
            raw_message_id=raw_message.id,
            source_id=raw_message.source_id,
            candidate_type="bcp_qr",
            status="pending",
            event_at=parsed_bcp.event_at,
            notification_at=parsed_bcp.notification_at,
            reported_amount=parsed_bcp.reported_amount,
            reported_currency="BOB",
            settlement_amount=None,
            settlement_currency=None,
            merchant=parsed_bcp.beneficiary,
            subject=raw_message.subject,
            sender=raw_message.sender,
            provider_uuid=parsed_bcp.transaction_id,
            message_id_header=parsed_bcp.message_id_header,
            quarantine_reason=None,
            rule_evidence=[],
            glosa=parsed_bcp.glosa,
            raw_glosa=parsed_bcp.raw_glosa,
            qr_subtype=None,
            account_suffix=None,
            direction="debit",
            raw_payload={
                "body_plain": raw_message.body_plain,
                "snippet": raw_message.snippet,
                "parties": parsed_bcp.parties,
                "beneficiary": parsed_bcp.beneficiary,
                "destination_bank": parsed_bcp.destination_bank,
                "transaction_id": parsed_bcp.transaction_id,
                "receipt_id": parsed_bcp.receipt_id,
            },
            provenance={
                "source": "watcher:bcp_qr",
                "raw_message_id": str(raw_message.id),
                "external_message_id": raw_message.external_message_id,
                "message_id": parsed_bcp.message_id_header,
                "transaction_id": parsed_bcp.transaction_id,
                "receipt_id": parsed_bcp.receipt_id,
                "timezone_provenance": parsed_bcp.timezone_provenance,
            },
            transaction_id=None,
            creation_fingerprint=f"bcp_qr:{raw_message.id}",
            created_at=now,
            updated_at=now,
        )
        session.add(candidate)
        session.flush()

        apply_rules_to_candidate(session, candidate, rules)
        raw_message.status = "quarantined" if candidate.status == "quarantined" else "parsed"
        session.flush()
        return candidate

    return None


process_raw_message_for_binance_card = process_raw_message_for_candidates


def process_plan_candidates(
    session: Session,
    plan_id: UUID,
) -> ProcessCandidatesResponse:
    """Process all unprocessed raw messages for a plan across all notice types."""
    _require_plan(session, plan_id)
    raw_messages = list(
        session.scalars(
            select(WatcherRawMessage)
            .where(WatcherRawMessage.plan_id == plan_id)
            .order_by(WatcherRawMessage.created_at.asc())
        ).all()
    )

    processed_count = 0
    created_count = 0
    resolved_count = 0
    quarantined_count = 0

    for msg in raw_messages:
        # Check if candidate already exists
        existing = session.scalar(
            select(WatcherCandidate).where(WatcherCandidate.raw_message_id == msg.id)
        )
        if existing is not None:
            continue

        candidate = process_raw_message_for_candidates(session, msg)
        if candidate is not None:
            processed_count += 1
            created_count += 1
            if candidate.status == "resolved":
                resolved_count += 1
            elif candidate.status == "quarantined":
                quarantined_count += 1

    return ProcessCandidatesResponse(
        processed_count=processed_count,
        candidates_created=created_count,
        candidates_resolved=resolved_count,
        candidates_quarantined=quarantined_count,
    )


process_plan_binance_card_messages = process_plan_candidates


def list_watcher_candidates(
    session: Session,
    plan_id: UUID,
    status: str | None = None,
    candidate_type: str | None = None,
    limit: int = 100,
) -> list[WatcherCandidate]:
    _require_plan(session, plan_id)
    query = select(WatcherCandidate).where(WatcherCandidate.plan_id == plan_id)
    if status is not None:
        query = query.where(WatcherCandidate.status == status)
    if candidate_type is not None:
        query = query.where(WatcherCandidate.candidate_type == candidate_type)
    query = query.order_by(WatcherCandidate.created_at.desc()).limit(limit)
    return list(session.scalars(query).all())


def get_watcher_candidate(
    session: Session,
    plan_id: UUID,
    candidate_id: UUID,
) -> WatcherCandidate:
    _require_plan(session, plan_id)
    candidate = session.scalar(
        select(WatcherCandidate).where(
            WatcherCandidate.plan_id == plan_id,
            WatcherCandidate.id == candidate_id,
        )
    )
    if candidate is None:
        raise ResourceNotFound(f"Watcher candidate {candidate_id} does not exist.")
    return candidate


def resolve_candidate(
    session: Session,
    plan_id: UUID,
    candidate_id: UUID,
    payload: ResolveCandidateRequest,
) -> WatcherCandidate:
    """Manually resolve a candidate into a posted Transaction."""
    candidate = get_watcher_candidate(session, plan_id, candidate_id)
    if candidate.status == "resolved":
        return candidate

    account = session.scalar(
        select(Account).where(
            Account.plan_id == plan_id,
            Account.id == payload.account_id,
        )
    )
    if account is None:
        raise ResourceNotFound(f"Account {payload.account_id} not found.")
    if account.status != "active":
        raise ValueError("Cannot resolve transaction to an archived account.")

    settlement_currency = payload.settlement_currency or account.currency_code
    if settlement_currency != account.currency_code:
        raise ValueError(
            f"Settlement currency '{settlement_currency}' must match Account currency '{account.currency_code}'."
        )

    settlement_amount = payload.settlement_amount or candidate.reported_amount
    if settlement_amount <= 0:
        raise ValueError("Settlement amount must be positive.")

    category = (
        _require_active_category(session, plan_id, payload.category_id)
        if payload.category_id
        else _pending_category(session, plan_id)
    )

    event_at = candidate.event_at or candidate.notification_at or utc_now()
    tx_type = "expense"
    if candidate.direction == "credit":
        tx_type = "income"

    tx_id = uuid4()
    tag_ids = [UUID(str(t)) for t in payload.tags] if payload.tags else []
    tx_payload = TransactionCreate(
        type=tx_type,
        account_id=account.id,
        amount=str(settlement_amount),
        currency_code=account.currency_code,
        event_at=event_at,
        category_id=category.id,
        merchant=candidate.merchant,
        memo=payload.memo or f"{candidate.candidate_type} {candidate.reported_amount} {candidate.reported_currency}",
        tags=tag_ids,
        source_metadata={
            "candidate_id": str(candidate.id),
            "candidate_type": candidate.candidate_type,
            "reported_amount": str(candidate.reported_amount),
            "reported_currency": candidate.reported_currency,
            "provider_uuid": candidate.provider_uuid,
            "qr_subtype": candidate.qr_subtype,
            "account_suffix": candidate.account_suffix,
        },
        provenance={
            "source": f"watcher:{candidate.candidate_type}",
            "raw_message_id": str(candidate.raw_message_id),
            "message_id": candidate.message_id_header,
            "notification_at": (
                candidate.notification_at.isoformat() if candidate.notification_at else None
            ),
            "resolved_at": utc_now().isoformat(),
        },
    )
    tx_result = create_transaction(
        session=session,
        plan_id=plan_id,
        transaction_id=tx_id,
        payload=tx_payload,
    )

    candidate.status = "resolved"
    candidate.settlement_amount = settlement_amount
    candidate.settlement_currency = settlement_currency
    candidate.transaction_id = tx_result.resource.id
    candidate.quarantine_reason = None
    candidate.updated_at = utc_now()
    session.flush()

    return candidate


def ignore_candidate(
    session: Session,
    plan_id: UUID,
    candidate_id: UUID,
    reason: str | None = None,
) -> WatcherCandidate:
    """Mark a candidate as ignored / dismissed."""
    candidate = get_watcher_candidate(session, plan_id, candidate_id)
    candidate.status = "ignored"
    if reason:
        candidate.quarantine_reason = reason
    candidate.updated_at = utc_now()
    session.flush()
    return candidate


# ---------------------------------------------------------------------------
# Account Mappings CRUD
# ---------------------------------------------------------------------------


def list_watcher_account_mappings(
    session: Session,
    plan_id: UUID,
    source_type: str | None = None,
) -> list[WatcherAccountMapping]:
    _require_plan(session, plan_id)
    query = select(WatcherAccountMapping).where(WatcherAccountMapping.plan_id == plan_id)
    if source_type is not None:
        query = query.where(WatcherAccountMapping.source_type == source_type)
    query = query.order_by(WatcherAccountMapping.created_at.asc())
    return list(session.scalars(query).all())


def create_watcher_account_mapping(
    session: Session,
    plan_id: UUID,
    payload: CreateAccountMappingRequest,
) -> WatcherAccountMapping:
    _require_plan(session, plan_id)
    account = session.scalar(
        select(Account).where(
            Account.plan_id == plan_id,
            Account.id == payload.account_id,
        )
    )
    if account is None:
        raise ResourceNotFound(f"Account {payload.account_id} does not exist.")
    if account.status != "active":
        raise ValueError("Cannot map to an archived account.")

    if payload.default_category_id is not None:
        cat = session.scalar(
            select(Category).where(
                Category.plan_id == plan_id,
                Category.id == payload.default_category_id,
            )
        )
        if cat is None:
            raise ResourceNotFound(f"Category {payload.default_category_id} does not exist.")
        if cat.status != "active":
            raise ValueError("Default category cannot be archived.")

    existing = session.scalar(
        select(WatcherAccountMapping).where(
            WatcherAccountMapping.plan_id == plan_id,
            WatcherAccountMapping.source_type == payload.source_type,
            WatcherAccountMapping.pattern == payload.pattern,
        )
    )

    now = utc_now()
    if existing is not None:
        existing.account_id = payload.account_id
        existing.default_category_id = payload.default_category_id
        existing.auto_resolve = payload.auto_resolve
        existing.updated_at = now
        session.flush()
        return existing

    mapping = WatcherAccountMapping(
        id=uuid4(),
        plan_id=plan_id,
        source_type=payload.source_type,
        pattern=payload.pattern,
        account_id=payload.account_id,
        default_category_id=payload.default_category_id,
        auto_resolve=payload.auto_resolve,
        creation_fingerprint=f"map:{plan_id}:{payload.source_type}:{payload.pattern}",
        created_at=now,
        updated_at=now,
    )
    session.add(mapping)
    session.flush()
    return mapping


def delete_watcher_account_mapping(
    session: Session,
    plan_id: UUID,
    mapping_id: UUID,
) -> None:
    _require_plan(session, plan_id)
    mapping = session.scalar(
        select(WatcherAccountMapping).where(
            WatcherAccountMapping.plan_id == plan_id,
            WatcherAccountMapping.id == mapping_id,
        )
    )
    if mapping is None:
        raise ResourceNotFound(f"Watcher account mapping {mapping_id} does not exist.")
    session.delete(mapping)
    session.flush()
