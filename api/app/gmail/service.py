from __future__ import annotations

import base64
import binascii
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.service import get_plan, ResourceNotFound
from app.gmail.client import (
    GmailClient,
    GmailConfigurationError,
    GmailError,
    access_token,
    authorization_url,
    decrypt_secret,
    encrypt_secret,
    require_configuration,
    require_sender_configuration,
    required_string,
)
from app.gmail.mime import decode_message
from app.gmail.filter import metadata_is_allowed, normalize_senders, sender_query
from app.gmail.models import GmailMessage, GmailOAuthState, GmailSource
from app.jobs.models import Job
from app.jobs.service import enqueue_job, utc_now
from app.settings import Settings

JOB_TYPE = "gmail.sync"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def source_for(
    session: Session, plan_id: UUID, source_id: UUID, *, lock: bool = False
) -> GmailSource:
    statement = select(GmailSource).where(
        GmailSource.plan_id == plan_id, GmailSource.id == source_id
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    source = session.scalar(statement)
    if source is None:
        raise ResourceNotFound("Gmail connection not found.")
    return source


def start_oauth(
    session: Session, settings: Settings, plan_id: UUID, source_id: UUID
) -> tuple[str, str, str]:
    require_configuration(settings)
    require_sender_configuration(settings)
    state, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    with session.begin():
        get_plan(session, plan_id)
        session.execute(
            insert(GmailSource)
            .values(
                id=source_id, plan_id=plan_id, status="connecting", sync_mode="full"
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        source_for(session, plan_id, source_id, lock=True)
        session.execute(
            update(GmailOAuthState)
            .where(GmailOAuthState.source_id == source_id)
            .values(expires_at=utc_now())
        )
        session.add(
            GmailOAuthState(
                state_hash=digest(state),
                source_id=source_id,
                browser_hash=digest(browser),
                verifier_ciphertext=encrypt_secret(settings, state, verifier),
                expires_at=utc_now() + timedelta(minutes=10),
            )
        )
    return authorization_url(settings, state, verifier), state, browser


def finish_oauth(
    session: Session,
    settings: Settings,
    client: GmailClient,
    state: str,
    browser: str,
    code: str | None,
    denied: bool,
) -> GmailSource:
    require_sender_configuration(settings)
    failure: Exception | None = None
    with session.begin():
        oauth = session.get(GmailOAuthState, digest(state))
        if oauth is None:
            raise GmailError("invalid_oauth_state")
        # Use the same lock order as start/disconnect and serialize credential replacement.
        source = session.scalar(
            select(GmailSource)
            .where(GmailSource.id == oauth.source_id)
            .with_for_update()
        )
        session.refresh(oauth)
        if (
            oauth.consumed_at is not None
            or oauth.expires_at <= utc_now()
            or not secrets.compare_digest(oauth.browser_hash, digest(browser))
        ):
            raise GmailError("invalid_oauth_state")
        oauth.consumed_at = utc_now()
        session.flush()
        try:
            with session.begin_nested():
                if denied or not code:
                    raise GmailError("authorization_denied")
                verifier = decrypt_secret(settings, state, oauth.verifier_ciphertext)
                tokens = client.exchange_code(code, verifier)
                token = access_token(tokens, require_scope=True)
                refresh = required_string(tokens, "refresh_token")
                profile = client.get(token, "profile")
                email = required_string(profile, "emailAddress").lower()
                if source.email is not None and source.email != email:
                    raise GmailError("mailbox_mismatch")
                source.email = email
                source.refresh_token_ciphertext = encrypt_secret(
                    settings, str(source.id), refresh
                )
                source.status = "active"
                source.allowed_senders = list(settings.gmail_allowed_senders)
                reset_full_sync(source)
                source.last_error = None
                queue_page(session, source)
                session.flush()
        except GmailError as exc:
            failure = exc
        except IntegrityError:
            failure = GmailError("mailbox_already_connected")
    if failure:
        raise failure
    return source


def reset_full_sync(source: GmailSource) -> None:
    source.sync_mode = "full"
    source.history_id = None
    source.full_sync_history_id = None
    source.page_token = None


def queue_page(session: Session, source: GmailSource) -> Job:
    # The source row lock and persisted pending ID make each successor unique.
    key = str(uuid4())
    job = enqueue_job(
        session,
        job_type=JOB_TYPE,
        payload={"source_id": str(source.id)},
        idempotency_key=key,
        request_fingerprint=str(source.id),
    )
    source.pending_job_id = job.id
    source.next_poll_at = None
    return job


def disconnect(session: Session, plan_id: UUID, source_id: UUID) -> GmailSource:
    with session.begin():
        source = source_for(session, plan_id, source_id, lock=True)
        source.status = "disconnected"
        source.refresh_token_ciphertext = None
        source.pending_job_id = None
        source.next_poll_at = None
        session.execute(
            update(GmailOAuthState)
            .where(GmailOAuthState.source_id == source_id)
            .values(expires_at=utc_now())
        )
    return source


def schedule_due(sessions: sessionmaker[Session], settings: Settings) -> None:
    try:
        require_configuration(settings)
    except GmailConfigurationError:
        return
    with sessions.begin() as session:
        sources = session.scalars(
            select(GmailSource)
            .where(GmailSource.status == "active")
            .order_by(GmailSource.id)
            .with_for_update(skip_locked=True)
        ).all()
        for source in sources:
            pending = (
                session.get(Job, source.pending_job_id)
                if source.pending_job_id
                else None
            )
            if pending and pending.status in {"queued", "running"}:
                continue
            if source.next_poll_at is None or source.next_poll_at <= utc_now():
                queue_page(session, source)


def _store_message(
    session: Session,
    source: GmailSource,
    client: GmailClient,
    token: str,
    gmail_id: str,
) -> None:
    if session.scalar(
        select(GmailMessage.id).where(
            GmailMessage.source_id == source.id, GmailMessage.gmail_id == gmail_id
        )
    ):
        return
    try:
        metadata = client.get(
            token, "messages/" + quote(gmail_id, safe=""),
            format="metadata", metadataHeaders="From", fields="id,labelIds,payload/headers",
        )
    except GmailError as exc:
        if exc.status == 404:
            return  # No evidence of an approved sender: do not fetch/store a body.
        raise
    if not metadata_is_allowed(metadata, gmail_id, source.allowed_senders):
        return
    try:
        envelope = client.get(
            token, "messages/" + quote(gmail_id, safe=""), format="raw"
        )
    except GmailError as exc:
        if exc.status != 404:
            raise
        envelope = {"id": gmail_id, "unavailable": True}
    raw = None
    decoded = {"issues": ["message_unavailable"]}
    status = "unavailable"
    if not envelope.get("unavailable"):
        try:
            encoded = required_string(envelope, "raw")
            raw = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            )
            decoded = decode_message(raw)
            status = "review" if decoded["issues"] else "decoded"
        except (
            ValueError,
            binascii.Error,
            UnicodeError,
            LookupError,
            GmailError,
            RecursionError,
        ):
            decoded, status = {"issues": ["message_decode_failed"]}, "review"
    message = GmailMessage(
            source_id=source.id,
            gmail_id=gmail_id,
            raw_mime=raw,
            provider_metadata=envelope,
            decoded=decoded,
            status=status,
        )
    session.add(message)
    session.flush()
    from app.binance_card.service import record_message

    record_message(session, message)


def sync_page(
    session: Session, source: GmailSource, client: GmailClient, settings: Settings
) -> None:
    try:
        senders = normalize_senders(source.allowed_senders)
    except ValueError:
        raise GmailError("ingestion_filter_required") from None
    if not senders:
        raise GmailError("ingestion_filter_required")
    refresh = decrypt_secret(
        settings, str(source.id), source.refresh_token_ciphertext or ""
    )
    tokens = client.refresh(refresh)
    token = access_token(tokens)
    if tokens.get("refresh_token"):
        source.refresh_token_ciphertext = encrypt_secret(
            settings, str(source.id), required_string(tokens, "refresh_token")
        )
    params = {"maxResults": "25"}
    if source.page_token:
        params["pageToken"] = source.page_token
    if source.sync_mode == "full":
        if not source.full_sync_history_id:
            # Capture BEFORE listing to catch messages arriving during a paginated scan.
            source.full_sync_history_id = required_string(
                client.get(token, "profile"), "historyId"
            )
        page = client.get(
            token, "messages", q=sender_query(senders), includeSpamTrash="false", **params
        )
        message_ids = [required_string(item, "id") for item in page.get("messages", [])]
    else:
        try:
            page = client.get(
                token, "history", startHistoryId=source.history_id or "", **params
            )
        except GmailError as exc:
            if exc.status == 404:
                reset_full_sync(source)
                queue_page(session, source)
                return
            raise
        message_ids = []
        for record in page.get("history", []):
            # Specific change lists avoid the duplicate generic `messages` collection.
            for change in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                message_ids.extend(
                    required_string(item["message"], "id")
                    for item in record.get(change, [])
                )

    for gmail_id in dict.fromkeys(message_ids):
        _store_message(session, source, client, token, gmail_id)

    next_page = page.get("nextPageToken")
    if next_page is not None and (not isinstance(next_page, str) or not next_page):
        raise GmailError("invalid_provider_response", retryable=True)
    source.page_token = next_page
    source.last_error = None
    if next_page:
        queue_page(session, source)
    else:
        was_full = source.sync_mode == "full"
        source.history_id = (
            source.full_sync_history_id
            if was_full
            else required_string(page, "historyId")
        )
        source.full_sync_history_id = None
        source.sync_mode = "history"
        source.pending_job_id = None
        source.last_synced_at = utc_now()
        source.next_poll_at = utc_now() + timedelta(
            seconds=0 if was_full else settings.gmail_poll_seconds
        )


def handle_job(
    sessions: sessionmaker[Session],
    settings: Settings,
    job: Job,
    client: GmailClient | None = None,
) -> None:
    from app.worker import RetryableJobError, TerminalJobError

    if job.job_type != JOB_TYPE:
        raise TerminalJobError("No handler is configured for this job type.")
    failure: GmailError | None = None
    owned_client = None
    try:
        with sessions.begin() as session:
            source = session.scalar(
                select(GmailSource)
                .where(GmailSource.id == UUID(job.payload["source_id"]))
                .with_for_update()
            )
            # Expired workers/replayed jobs cannot process a successor's checkpoint.
            if (
                source is None
                or source.status != "active"
                or source.pending_job_id != job.id
            ):
                return
            try:
                with session.begin_nested():
                    if client is None:
                        owned_client = GmailClient(settings)
                    sync_page(session, source, client or owned_client, settings)
            except GmailConfigurationError:
                failure = GmailError("gmail_not_configured", retryable=True)
            except GmailError as exc:
                failure = exc
            except (KeyError, TypeError, ValueError, AttributeError):
                failure = GmailError("invalid_provider_response", retryable=True)
            if failure:
                source.last_error = failure.code
                source.next_poll_at = utc_now() + timedelta(
                    seconds=settings.gmail_poll_seconds
                )
                if not failure.retryable:
                    source.status = "needs_authorization"
                    source.pending_job_id = None
    finally:
        if owned_client:
            owned_client.close()
    if failure:
        error_type = RetryableJobError if failure.retryable else TerminalJobError
        raise error_type(failure.code)
