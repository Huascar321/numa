from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Plan
from app.db import session_factory_for
from app.main import create_app
from app.settings import Settings
from app.watchers.crypto import (
    decrypt_token,
    encrypt_token,
    get_encryption_key,
)
from app.watchers.email_decoder import (
    decode_gmail_message_payload,
    decode_rfc2047,
    decode_rfc822_bytes,
)
from app.watchers.gmail_client import (
    GMAIL_READONLY_SCOPE,
    GmailClient,
    GmailHistoryExpiredError,
    GmailNotConfiguredError,
)
from app.watchers.models import WatcherRawMessage, WatcherSource
from app.watchers.schemas import ConnectGmailRequest
from app.watchers.service import (
    connect_gmail,
    disconnect_watcher_source,
    get_gmail_auth_url,
    list_watcher_raw_messages,
    list_watcher_sources,
    sync_watcher_source,
)


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_watchers_db(postgres_sessions: sessionmaker[Session]):
    statement = text(
        "TRUNCATE watcher_raw_messages, watcher_sources, "
        "reconciliation_sessions, transfer_legs, transfers, "
        "transaction_tags, posted_account_movements, transaction_corrections, "
        "monthly_budget_assignments, transactions, tags, categories, "
        "category_groups, accounts, plans CASCADE"
    )
    with postgres_sessions.begin() as session:
        session.execute(statement)
    yield


@pytest.fixture
def configured_settings(migrated_postgres_url: str) -> Settings:
    return Settings(
        database_url=migrated_postgres_url,
        gmail_client_id="test-client-id.apps.googleusercontent.com",
        gmail_client_secret="test-client-secret",
        token_encryption_key="test-encryption-key-for-unit-tests",
    )


@pytest.fixture
def client(configured_settings: Settings) -> TestClient:
    return TestClient(create_app(configured_settings))


def create_test_plan(client: TestClient) -> str:
    plan_id = str(uuid4())
    resp = client.put(
        f"/plans/{plan_id}",
        json={
            "name": "Watcher Test Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": "America/La_Paz",
        },
    )
    assert resp.status_code == 201
    return plan_id


# ---------------------------------------------------------------------------
# 1. Crypto: Symmetric Token Encryption & Decryption Tests
# ---------------------------------------------------------------------------


def test_token_encryption_and_decryption_roundtrip_and_tampering():
    key = "super-secret-server-encryption-key"
    token = "1//04_abcdef123456_REFRESH_TOKEN_SAMPLE_XYZ"

    encrypted = encrypt_token(token, key)
    assert encrypted.startswith("v1:")
    assert encrypted != token

    decrypted = decrypt_token(encrypted, key)
    assert decrypted == token

    # Mismatched key must fail
    with pytest.raises(ValueError, match="tag mismatch"):
        decrypt_token(encrypted, "different-wrong-key")

    # Tampered ciphertext must fail
    tampered = encrypted[:-5] + "XXXXX"
    with pytest.raises(ValueError):
        decrypt_token(tampered, key)

    # Empty token / key checks
    with pytest.raises(ValueError):
        encrypt_token("", key)
    with pytest.raises(ValueError):
        encrypt_token(token, "")


# ---------------------------------------------------------------------------
# 2. Invariants: Password Rejection & Readonly Scope
# ---------------------------------------------------------------------------


def test_password_rejection():
    # Schema validation
    with pytest.raises(ValidationError):
        ConnectGmailRequest(
            code="test-code",
            redirect_uri="http://localhost:5173/oauth/callback",
            password="user_provided_password",  # type: ignore[arg-type]
        )

    # Service & Client validation
    settings = Settings(
        gmail_client_id="cid",
        gmail_client_secret="csec",
    )
    client = GmailClient(settings)
    with pytest.raises(ValueError, match="Password collection is strictly prohibited"):
        client.exchange_code_for_tokens(
            code="test-code",
            redirect_uri="http://localhost:5173/callback",
            password="secret_password",
        )


def test_oauth_url_and_readonly_scope(configured_settings: Settings):
    client = GmailClient(configured_settings)
    auth_url = client.build_auth_url("http://localhost:5173/oauth/callback", "state-123")

    assert "https://accounts.google.com/o/oauth2/v2/auth" in auth_url
    assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.readonly" in auth_url
    assert GMAIL_READONLY_SCOPE in auth_url or "gmail.readonly" in auth_url
    assert "access_type=offline" in auth_url
    assert "prompt=consent" in auth_url


def test_graceful_degradation_without_gmail_config(migrated_postgres_url: str):
    unconfigured_settings = Settings(
        database_url=migrated_postgres_url,
        gmail_client_id=None,
        gmail_client_secret=None,
    )
    test_client = TestClient(create_app(unconfigured_settings))

    # Health check is completely unaffected
    health_resp = test_client.get("/health/ready")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "ok"}

    plan_id = str(uuid4())
    create_resp = test_client.put(
        f"/plans/{plan_id}",
        json={
            "name": "No-Gmail Plan",
            "reporting_currency_code": "BOB",
            "budget_timezone": "America/La_Paz",
        },
    )
    assert create_resp.status_code == 201

    # Requesting Gmail auth URL gracefully returns 503 Service Unavailable
    auth_resp = test_client.get(
        f"/plans/{plan_id}/watchers/gmail/auth-url?redirect_uri=http://localhost/cb"
    )
    assert auth_resp.status_code == 503
    assert "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required" in auth_resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Email Decoding: MIME, RFC2047, Charset Precedence & Provenance
# ---------------------------------------------------------------------------


def test_rfc2047_header_decoding():
    # UTF-8 Q-encoding
    assert decode_rfc2047("=?utf-8?Q?Caf=C3=A9_Transaction?=") == "Café Transaction"
    # UTF-8 B-encoding
    b64_str = base64.b64encode("Banco Ganadero - Notificación".encode("utf-8")).decode("ascii")
    assert decode_rfc2047(f"=?UTF-8?B?{b64_str}?=") == "Banco Ganadero - Notificación"
    # ISO-8859-1 Q-encoding
    assert decode_rfc2047("=?ISO-8859-1?Q?Env=EDo_exitoso?=") == "Envío exitoso"
    # Plain text
    assert decode_rfc2047("Simple Subject") == "Simple Subject"


def test_recursive_mime_and_provenance_decoding():
    # Construct a sample nested multipart Gmail resource
    html_body_bytes = b"<html><body><p>Recibiste Bs 150.50 de Juan Perez</p></body></html>"
    html_b64 = base64.urlsafe_b64encode(html_body_bytes).decode("ascii")

    plain_body_bytes = b"Recibiste Bs 150.50 de Juan Perez"
    plain_b64 = base64.urlsafe_b64encode(plain_body_bytes).decode("ascii")

    gmail_resource = {
        "id": "msg_001",
        "threadId": "thread_001",
        "internalDate": "1724500000000",
        "snippet": "Recibiste Bs 150.50",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "=?UTF-8?B?QmFuY28gR2FuYWRlcm8=?= <notificaciones@bg.com.bo>"},
                {"name": "To", "value": "user@example.com"},
                {"name": "Subject", "value": "=?UTF-8?Q?Notificaci=C3=B3n_de_Abono?="},
                {"name": "Date", "value": "Mon, 24 Aug 2026 12:00:00 -0400"},
                {"name": "Message-ID", "value": "<msg-unique-001@bg.com.bo>"},
                {"name": "Authentication-Results", "value": "mx.google.com; dkim=pass header.i=@bg.com.bo; spf=pass"},
                {"name": "Received-SPF", "value": "pass (google.com: domain of notificaciones@bg.com.bo designates 1.2.3.4)"},
                {"name": "DKIM-Signature", "value": "v=1; a=rsa-sha256; d=bg.com.bo; s=s1; ..."},
            ],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain; charset=utf-8",
                            "headers": [{"name": "Content-Type", "value": "text/plain; charset=utf-8"}],
                            "body": {"data": plain_b64},
                        },
                        {
                            "mimeType": "text/html; charset=utf-8",
                            "headers": [
                                {"name": "Content-Type", "value": "text/html; charset=utf-8"},
                                {"name": "Content-Transfer-Encoding", "value": "base64"},
                            ],
                            "body": {"data": html_b64},
                        },
                    ],
                }
            ],
        },
    }

    decoded = decode_gmail_message_payload(gmail_resource)
    assert decoded.sender == "Banco Ganadero <notificaciones@bg.com.bo>"
    assert decoded.subject == "Notificación de Abono"
    assert decoded.recipient == "user@example.com"
    assert "Recibiste Bs 150.50" in (decoded.body_plain or "")
    assert "<p>Recibiste Bs 150.50 de Juan Perez</p>" in (decoded.body_html or "")

    # Check authentication provenance
    assert decoded.provenance["message_id"] == "<msg-unique-001@bg.com.bo>"
    assert len(decoded.provenance["authentication_results"]) > 0
    assert "dkim=pass" in decoded.provenance["authentication_results"][0]
    assert "pass" in decoded.provenance["received_spf"][0]
    assert len(decoded.provenance["dkim_signatures"]) > 0


def test_mime_charset_precedence_over_conflicting_inner_metadata():
    # Invariant: MIME charset takes precedence over conflicting inner metadata.
    # Spanish text encoded as UTF-8 bytes:
    sample_text = "Transacción exitosa: Pago con QR Móvil"
    utf8_bytes = sample_text.encode("utf-8")

    # The HTML body misleadingly has <meta charset="windows-1252">
    conflicting_html_bytes = (
        b'<html><head><meta charset="windows-1252"></head><body>'
        + utf8_bytes
        + b"</body></html>"
    )
    conflicting_b64 = base64.urlsafe_b64encode(conflicting_html_bytes).decode("ascii")

    gmail_resource = {
        "id": "msg_bcp_002",
        "threadId": "thread_002",
        "internalDate": "1724500000000",
        "payload": {
            "mimeType": "text/html; charset=utf-8",
            "headers": [
                {"name": "From", "value": "bcp@bcp.com.bo"},
                {"name": "Subject", "value": "BCP QR Pago"},
                {"name": "Content-Type", "value": "text/html; charset=utf-8"},
            ],
            "body": {"data": conflicting_b64},
        },
    }

    decoded = decode_gmail_message_payload(gmail_resource)
    # Because MIME charset=utf-8 takes precedence over inner windows-1252, Spanish accents decode cleanly!
    assert "Transacción exitosa: Pago con QR Móvil" in (decoded.body_html or "")
    assert decoded.mime_metadata["parts"][0]["mime_charset"] == "utf-8"
    assert decoded.mime_metadata["parts"][0]["inner_charset"] == "windows-1252"
    assert decoded.mime_metadata["parts"][0]["mime_charset_precedence"] is True


# ---------------------------------------------------------------------------
# 4. Watcher Service & History 404 Recovery & Idempotent Ingestion
# ---------------------------------------------------------------------------


def test_gmail_connect_and_sync_and_idempotent_ingestion(
    postgres_sessions: sessionmaker[Session],
    configured_settings: Settings,
):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="Service Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="test-fp",
        )
        session.add(plan)
        session.commit()
        plan_id = plan.id

    mock_client = MagicMock(spec=GmailClient)
    mock_client.exchange_code_for_tokens.return_value = {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh-token-12345",
    }
    mock_client.get_user_profile.return_value = {
        "emailAddress": "notificaciones@example.com",
        "historyId": "1001",
    }
    mock_client.refresh_access_token.return_value = "fake-fresh-access-token"
    mock_client.list_messages.return_value = {
        "messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]
    }

    raw_html_m1 = base64.urlsafe_b64encode(b"<b>Notice 1</b>").decode("ascii")
    raw_html_m2 = base64.urlsafe_b64encode(b"<b>Notice 2</b>").decode("ascii")

    mock_client.get_message.side_effect = lambda token, msg_id, format_type="full": {
        "id": msg_id,
        "threadId": f"t_{msg_id}",
        "internalDate": "1724500000000",
        "payload": {
            "mimeType": "text/html",
            "headers": [
                {"name": "From", "value": "bank@example.com"},
                {"name": "Subject", "value": f"Subject for {msg_id}"},
                {"name": "Date", "value": "Mon, 24 Aug 2026 12:00:00 GMT"},
            ],
            "body": {"data": raw_html_m1 if msg_id == "m1" else raw_html_m2},
        },
    }

    with postgres_sessions() as session:
        # 1. Connect
        source = connect_gmail(
            session=session,
            settings=configured_settings,
            plan_id=plan_id,
            payload=ConnectGmailRequest(
                code="auth-code-xyz",
                redirect_uri="http://localhost:5173/callback",
            ),
            client=mock_client,
        )
        assert source.email_address == "notificaciones@example.com"
        assert source.status == "active"
        assert source.encrypted_refresh_token.startswith("v1:")
        session.commit()
        source_id = source.id

        # 2. Initial Full Sync
        sync_result = sync_watcher_source(
            session=session,
            settings=configured_settings,
            plan_id=plan_id,
            source_id=source_id,
            client=mock_client,
        )
        assert sync_result.synced_count == 2
        assert sync_result.new_messages_count == 2
        assert sync_result.history_id == "1001"
        session.commit()

        messages = list_watcher_raw_messages(session, plan_id)
        assert len(messages) == 2
        assert {m.external_message_id for m in messages} == {"m1", "m2"}

        # 3. Re-sync with SAME messages -> Idempotent Ingestion (0 new messages written)
        mock_client.list_history.return_value = {
            "history": [
                {"messages": [{"id": "m1"}, {"id": "m2"}]}
            ],
            "historyId": "1002",
        }
        resync_result = sync_watcher_source(
            session=session,
            settings=configured_settings,
            plan_id=plan_id,
            source_id=source_id,
            client=mock_client,
        )
        assert resync_result.new_messages_count == 0  # Idempotent!
        assert resync_result.history_id == "1002"
        session.commit()

        messages_after = list_watcher_raw_messages(session, plan_id)
        assert len(messages_after) == 2


def test_gmail_history_404_recovery_performs_full_resync(
    postgres_sessions: sessionmaker[Session],
    configured_settings: Settings,
):
    with postgres_sessions() as session:
        plan = Plan(
            id=uuid4(),
            name="History Recovery Plan",
            reporting_currency_code="BOB",
            budget_timezone="America/La_Paz",
            creation_fingerprint="recovery-fp",
        )
        session.add(plan)
        session.commit()
        plan_id = plan.id

    mock_client = MagicMock(spec=GmailClient)
    mock_client.exchange_code_for_tokens.return_value = {
        "access_token": "token",
        "refresh_token": "refresh-123",
    }
    mock_client.get_user_profile.return_value = {
        "emailAddress": "recovery@example.com",
        "historyId": "2000",
    }
    mock_client.refresh_access_token.return_value = "fresh-token"
    mock_client.get_message.return_value = {
        "id": "m_recovered",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "bank@example.com"},
                {"name": "Subject", "value": "Recovered Message"},
            ],
            "body": {"data": base64.urlsafe_b64encode(b"Recovered").decode("ascii")},
        },
    }

    with postgres_sessions() as session:
        source = connect_gmail(
            session=session,
            settings=configured_settings,
            plan_id=plan_id,
            payload=ConnectGmailRequest(
                code="auth-code-xyz",
                redirect_uri="http://localhost:5173/callback",
            ),
            client=mock_client,
        )
        # Set a stale/expired history_id
        source.history_id = "expired-history-id-999"
        session.commit()
        source_id = source.id

        # Make list_history raise GmailHistoryExpiredError (HTTP 404)
        mock_client.list_history.side_effect = GmailHistoryExpiredError(
            "Gmail history cursor expired (HTTP 404)"
        )
        # When 404 occurs, it falls back to full sync list_messages:
        mock_client.list_messages.return_value = {"messages": [{"id": "m_recovered"}]}

        # Sync should catch 404, reset cursor, and complete full sync idempotently!
        sync_result = sync_watcher_source(
            session=session,
            settings=configured_settings,
            plan_id=plan_id,
            source_id=source_id,
            client=mock_client,
        )

        assert sync_result.synced_count == 1
        assert sync_result.new_messages_count == 1
        assert sync_result.history_id == "2000"
        session.commit()

        updated_source = session.get(WatcherSource, source_id)
        assert updated_source is not None
        assert updated_source.history_id == "2000"

        messages = list_watcher_raw_messages(session, plan_id)
        assert len(messages) == 1
        assert messages[0].external_message_id == "m_recovered"


# ---------------------------------------------------------------------------
# 5. Full REST API Route Tests
# ---------------------------------------------------------------------------


def test_watcher_api_endpoints_full_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    plan_id = create_test_plan(client)

    # 1. GET auth-url
    auth_resp = client.get(
        f"/plans/{plan_id}/watchers/gmail/auth-url?redirect_uri=http://localhost:5173/oauth/callback"
    )
    assert auth_resp.status_code == 200
    assert "https://accounts.google.com/o/oauth2/v2/auth" in auth_resp.json()["auth_url"]

    # 2. Mock GmailClient methods for connect and sync
    mock_tokens = {"access_token": "api-access-token", "refresh_token": "api-refresh-token"}
    mock_profile = {"emailAddress": "api-watcher@example.com", "historyId": "3001"}
    mock_messages_list = {"messages": [{"id": "api_msg_1"}]}
    mock_msg = {
        "id": "api_msg_1",
        "internalDate": "1724500000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "notif@bank.com"},
                {"name": "Subject", "value": "API Message Subject"},
            ],
            "body": {"data": base64.urlsafe_b64encode(b"API Body").decode("ascii")},
        },
    }

    monkeypatch.setattr(GmailClient, "exchange_code_for_tokens", lambda *args, **kwargs: mock_tokens)
    monkeypatch.setattr(GmailClient, "get_user_profile", lambda *args, **kwargs: mock_profile)
    monkeypatch.setattr(GmailClient, "refresh_access_token", lambda *args, **kwargs: "fresh-api-token")
    monkeypatch.setattr(GmailClient, "list_messages", lambda *args, **kwargs: mock_messages_list)
    monkeypatch.setattr(GmailClient, "get_message", lambda *args, **kwargs: mock_msg)

    # 3. Connect Gmail
    connect_resp = client.post(
        f"/plans/{plan_id}/watchers/gmail/connect",
        json={
            "code": "sample-code",
            "redirect_uri": "http://localhost:5173/oauth/callback",
        },
    )
    assert connect_resp.status_code == 201
    source_data = connect_resp.json()
    assert source_data["email_address"] == "api-watcher@example.com"
    assert source_data["status"] == "active"
    assert "encrypted_refresh_token" not in source_data  # Never exposed!
    source_id = source_data["id"]

    # 4. List Watcher Sources
    list_resp = client.get(f"/plans/{plan_id}/watchers/sources")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 5. Sync Watcher Source
    sync_resp = client.post(f"/plans/{plan_id}/watchers/sources/{source_id}/sync")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["synced_count"] == 1
    assert sync_resp.json()["new_messages_count"] == 1

    # 6. List Ingested Messages
    msgs_resp = client.get(f"/plans/{plan_id}/watchers/messages")
    assert msgs_resp.status_code == 200
    msgs_list = msgs_resp.json()
    assert len(msgs_list) == 1
    assert msgs_list[0]["subject"] == "API Message Subject"
    assert msgs_list[0]["sender"] == "notif@bank.com"
    message_id = msgs_list[0]["id"]

    # 7. Get Message Detail
    msg_detail_resp = client.get(f"/plans/{plan_id}/watchers/messages/{message_id}")
    assert msg_detail_resp.status_code == 200
    assert msg_detail_resp.json()["id"] == message_id

    # 8. Disconnect Watcher Source
    disconnect_resp = client.post(f"/plans/{plan_id}/watchers/sources/{source_id}/disconnect")
    assert disconnect_resp.status_code == 200
    assert disconnect_resp.json()["status"] == "disconnected"

    # 9. Syncing disconnected source fails
    sync_disconnected_resp = client.post(f"/plans/{plan_id}/watchers/sources/{source_id}/sync")
    assert sync_disconnected_resp.status_code == 422
