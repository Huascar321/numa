from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from app.db import session_factory_for
from app.gmail.client import (
    READONLY_SCOPE,
    GmailClient,
    GmailError,
    decrypt_secret,
    encrypt_secret,
)
from app.gmail.mime import decode_message
from app.gmail.models import GmailMessage, GmailOAuthState, GmailSource
from app.gmail.routes import get_client
from app.gmail.service import handle_job, schedule_due
from app.jobs.models import Job
from app.jobs.service import utc_now
from app.main import create_app
from app.settings import Settings
from app.worker import Worker

RAW = b"From: notice@example.com\r\nSubject: =?utf-8?b?QXZpc28gY29uIMOx?=\r\nMessage-ID: <one@example.com>\r\nContent-Type: multipart/mixed; boundary=outer\r\n\r\n--outer\r\nContent-Type: multipart/alternative; boundary=inner\r\n\r\n--inner\r\nContent-Type: text/html; charset=iso-8859-1\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n<meta charset=utf-8>Se=F1al\r\n--inner--\r\n--outer--\r\n"


def settings_for(**kwargs):
    kwargs.setdefault("gmail_allowed_senders", ["notice@example.com"])
    return Settings(
        _env_file=None,
        gmail_client_id="client",
        gmail_client_secret="secret",
        gmail_redirect_uri="http://localhost/gmail/oauth/callback",
        gmail_token_key=Fernet.generate_key().decode(),
        **kwargs,
    )


class Provider:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.history_expired = False
        self.full_pages = {
            None: {"messages": [{"id": "one"}], "nextPageToken": "next"},
            "next": {"messages": [{"id": "one"}, {"id": "two"}]},
        }
        self.history_pages = {
            None: {
                "historyId": "200",
                "history": [
                    {
                        "messagesAdded": [
                            {"message": {"id": "two"}},
                            {"message": {"id": "three"}},
                        ]
                    }
                ],
            }
        }
        self.envelopes = {}
        self.metadata = {}
        self.scope = READONLY_SCOPE
        self.email = "me@example.com"

    def respond(self, request):
        self.calls.append(request)
        path = request.url.path
        if path == "/token":
            if self.failure:
                return httpx.Response(
                    self.failure,
                    json={
                        "error": "invalid_grant"
                        if self.failure == 400
                        else "private secret details"
                    },
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "scope": self.scope,
                },
            )
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": self.email, "historyId": "100"}
            )
        if path.endswith("/messages"):
            return httpx.Response(
                200, json=self.full_pages[request.url.params.get("pageToken")]
            )
        if path.endswith("/history"):
            if self.history_expired:
                return httpx.Response(404, json={"error": {"message": "expired"}})
            return httpx.Response(
                200, json=self.history_pages[request.url.params.get("pageToken")]
            )
        message_id = path.rsplit("/", 1)[-1]
        if request.url.params.get("format") == "metadata":
            metadata = self.metadata.get(message_id, {
                "id": message_id, "labelIds": ["INBOX"],
                "payload": {"headers": [{"name": "From", "value": "Notice <notice@example.com>"}]},
            })
            if isinstance(metadata, int):
                return httpx.Response(metadata, json={"error": "private message details"})
            return httpx.Response(200, json=metadata)
        envelope = self.envelopes.get(
            message_id,
            {"id": message_id, "raw": base64.urlsafe_b64encode(RAW).decode()},
        )
        if isinstance(envelope, int):
            return httpx.Response(envelope, json={"error": "private message details"})
        return httpx.Response(200, json=envelope)


@pytest.fixture
def gmail(migrated_postgres_url):
    sessions = session_factory_for(migrated_postgres_url)
    with sessions.begin() as session:
        session.execute(text("TRUNCATE plans, jobs CASCADE"))
    settings = settings_for(database_url=migrated_postgres_url)
    provider = Provider()
    client = GmailClient(settings, transport=httpx.MockTransport(provider.respond))
    app = create_app(settings)
    app.dependency_overrides[get_client] = lambda: client
    api = TestClient(app, base_url="http://localhost")
    plan_id, source_id = uuid4(), uuid4()
    result = api.put(
        f"/plans/{plan_id}",
        json={
            "name": "Gmail test",
            "reporting_currency_code": "BOB",
            "budget_timezone": "America/La_Paz",
        },
    )
    assert result.status_code == 201
    yield api, sessions, settings, provider, client, plan_id, source_id
    client.close()


def authorize(gmail):
    api, sessions, settings, provider, client, plan, source = gmail
    result = api.post(f"/plans/{plan}/gmail/{source}/oauth", json={})
    assert result.status_code == 200, result.text
    params = parse_qs(urlparse(result.json()["authorization_url"]).query)
    callback = {"state": params["state"][0], "code": "private-code"}
    result = api.get("/gmail/oauth/callback", params=callback, follow_redirects=False)
    assert result.status_code == 303, result.text
    return params, callback


def worker_for(gmail):
    _, sessions, settings, _, client, _, _ = gmail
    return Worker(
        sessions,
        claimant_name="gmail-test",
        handler=lambda job: handle_job(sessions, settings, job, client),
        lease_duration=timedelta(seconds=60),
        retry_delay=timedelta(seconds=0),
        scheduler=lambda: schedule_due(sessions, settings),
    )


def test_nested_mime_header_transfer_encoding_and_charset_precedence():
    result = decode_message(RAW)
    assert result["issues"] == []
    assert (
        next(h["value"] for h in result["headers"] if h["name"] == "Subject")
        == "Aviso con ñ"
    )
    assert result["parts"][0]["mime_charset"] == "iso-8859-1"
    assert "Señal" in result["parts"][0]["text"]
    assert result["authentication_independently_verified"] is False
    broken = decode_message(b"Content-Type: text/plain; charset=unknown\r\n\r\n\xff")
    assert "body_decode_failed" in broken["issues"]
    encoded = decode_message(
        b"Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\naG9sYQ=="
    )
    assert encoded["parts"][0]["text"] == "hola"


def test_cipher_is_owner_bound_and_wrong_key_is_rejected():
    settings = settings_for()
    encrypted = encrypt_secret(settings, "source", "refresh-secret")
    assert "refresh-secret" not in encrypted
    assert decrypt_secret(settings, "source", encrypted) == "refresh-secret"
    for owner, config in [("other", settings), ("source", settings_for())]:
        with pytest.raises(GmailError, match="credential_unreadable"):
            decrypt_secret(config, owner, encrypted)


def test_optional_gmail_and_password_rejection():
    app = create_app(
        Settings(_env_file=None, database_url="postgresql+psycopg://localhost/unused")
    )
    api = TestClient(app)
    assert api.get("/health/live").status_code == 200
    result = api.post(
        f"/plans/{uuid4()}/gmail/{uuid4()}/oauth", json={"password": "not-collected"}
    )
    assert result.status_code == 422
    assert "not-collected" not in result.text
    # Disabled configuration fails before database/provider access.
    result = api.post(f"/plans/{uuid4()}/gmail/{uuid4()}/oauth", json={})
    assert result.status_code == 503


def test_empty_sender_scope_blocks_oauth_before_database_or_provider():
    app = create_app(settings_for(gmail_allowed_senders=[], database_url="postgresql+psycopg://localhost/unused"))
    api = TestClient(app)
    assert api.post(f"/plans/{uuid4()}/gmail/{uuid4()}/oauth", json={}).status_code == 503
    assert api.get("/health/live").status_code == 200


def test_oauth_readonly_pkce_encryption_browser_binding_and_single_use(gmail):
    api, sessions, settings, provider, client, plan, source = gmail
    result = api.post(f"/plans/{plan}/gmail/{source}/oauth", json={})
    params = parse_qs(urlparse(result.json()["authorization_url"]).query)
    assert params["scope"] == [READONLY_SCOPE]
    assert params["code_challenge_method"] == ["S256"]
    assert params["access_type"] == ["offline"]
    assert "HttpOnly" in result.headers["set-cookie"]
    callback = {"state": params["state"][0], "code": "private-code"}
    stranger = TestClient(api.app, base_url="http://localhost")
    assert stranger.get("/gmail/oauth/callback", params=callback).status_code == 400
    assert not provider.calls
    result = api.get("/gmail/oauth/callback", params=callback, follow_redirects=False)
    assert result.status_code == 303
    assert api.get("/gmail/oauth/callback", params=callback).status_code == 400
    with sessions() as session:
        record = session.get(GmailSource, source)
        assert (
            decrypt_secret(settings, str(source), record.refresh_token_ciphertext)
            == "refresh-secret"
        )
        assert session.scalar(select(func.count()).select_from(Job)) == 1
    response = api.get(f"/plans/{plan}/gmail")
    assert response.status_code == 200
    assert response.json()["configured_senders"] == ["notice@example.com"]
    assert response.json()["sources"][0]["allowed_senders"] == ["notice@example.com"]
    assert all(
        value not in response.text
        for value in ["refresh-secret", "access-secret", "ciphertext", "private-code"]
    )
    token_request = provider.calls[0]
    assert "code_verifier=" in token_request.content.decode()


def test_oauth_expiry_denial_scope_and_replay(gmail):
    api, sessions, _, provider, _, plan, source = gmail
    for mode in ("expired", "denied", "scope"):
        result = api.post(f"/plans/{plan}/gmail/{source}/oauth", json={})
        state = parse_qs(urlparse(result.json()["authorization_url"]).query)["state"][0]
        if mode == "expired":
            with sessions.begin() as session:
                for row in session.scalars(select(GmailOAuthState)):
                    row.expires_at = utc_now() - timedelta(seconds=1)
        provider.scope = (
            READONLY_SCOPE + " https://mail.google.com/"
            if mode == "scope"
            else READONLY_SCOPE
        )
        params = (
            {"state": state, "error": "access_denied"}
            if mode == "denied"
            else {"state": state, "code": "private-code"}
        )
        response = api.get("/gmail/oauth/callback", params=params)
        assert response.status_code == 400
        assert (
            api.get(
                "/gmail/oauth/callback", params={"state": state, "code": "code"}
            ).status_code
            == 400
        )
    with sessions() as session:
        assert session.get(GmailSource, source).refresh_token_ciphertext is None
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_full_scan_history_pagination_idempotency_and_no_financial_mutation(gmail):
    _, sessions, _, provider, _, _, source = gmail
    authorize(gmail)
    worker = worker_for(gmail)
    assert worker.run_once()
    with sessions() as session:
        record = session.get(GmailSource, source)
        assert record.page_token == "next"
        assert record.history_id is None
        assert record.full_sync_history_id == "100"
        first_job = session.scalar(select(Job).order_by(Job.created_at))
    assert worker.run_once()
    provider.history_pages = {
        None: {
            "historyId": "200",
            "nextPageToken": "history-next",
            "history": [{"messagesAdded": [{"message": {"id": "three"}}]}],
        },
        "history-next": {
            "historyId": "300",
            "history": [{"messagesAdded": [{"message": {"id": "three"}}]}],
        },
    }
    assert worker.run_once()
    with sessions() as session:
        assert session.get(GmailSource, source).history_id == "100"
    assert worker.run_once()
    handle_job(
        sessions, gmail[2], first_job, gmail[4]
    )  # Replaying a finished job is inert.
    assert not worker.run_once()
    with sessions() as session:
        assert session.get(GmailSource, source).history_id == "300"
        rows = session.scalars(select(GmailMessage)).all()
        assert {row.gmail_id for row in rows} == {"one", "two", "three"}
        assert all(row.raw_mime == RAW for row in rows)
        assert session.scalar(text("SELECT count(*) FROM transactions")) == 0
        assert (
            session.scalar(text("SELECT count(*) FROM posted_account_movements")) == 0
        )
    history_calls = [r for r in provider.calls if r.url.path.endswith("/history")]
    assert all(r.url.params["startHistoryId"] == "100" for r in history_calls)
    list_calls = [r for r in provider.calls if r.url.path.endswith("/messages")]
    assert all(r.url.params["q"] == "{from:notice@example.com}" for r in list_calls)
    assert all(r.url.params["includeSpamTrash"] == "false" for r in list_calls)


def test_expired_history_schedules_one_full_resync_and_preserves_evidence(gmail):
    _, sessions, settings, provider, client, _, source = gmail
    authorize(gmail)
    worker = worker_for(gmail)
    assert worker.run_once() and worker.run_once()
    provider.history_expired = True
    assert worker.run_once()
    with sessions() as session:
        record = session.get(GmailSource, source)
        assert record.sync_mode == "full" and record.history_id is None
        pending = record.pending_job_id
        old = session.scalar(
            select(Job).where(Job.status == "succeeded").order_by(Job.created_at.desc())
        )
    handle_job(sessions, settings, old, client)
    schedule_due(sessions, settings)
    with sessions() as session:
        assert session.get(GmailSource, source).pending_job_id == pending
        assert (
            session.scalar(
                select(func.count()).select_from(Job).where(Job.status == "queued")
            )
            == 1
        )
    assert worker.run_once() and worker.run_once()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 2


def test_outage_retries_without_cursor_advance_and_recovers_after_exhaustion(gmail):
    api, sessions, settings, provider, _, plan, source = gmail
    authorize(gmail)
    provider.failure = 503
    worker = worker_for(gmail)
    assert worker.run_once() and worker.run_once() and worker.run_once()
    assert not worker.run_once()
    assert api.get("/health/live").status_code == 200
    assert api.get(f"/plans/{plan}/accounts").status_code == 200
    with sessions.begin() as session:
        record = session.get(GmailSource, source)
        assert record.history_id is None and record.page_token is None
        assert record.last_error == "gmail_request_failed"
        record.next_poll_at = utc_now() - timedelta(seconds=1)
        failed = session.scalar(select(Job).where(Job.status == "failed"))
        assert "private secret" not in str(failed.failure_details)
    provider.failure = None
    assert worker.run_once()
    with sessions() as session:
        assert session.get(GmailSource, source).page_token == "next"


def test_mid_page_failure_rolls_back_messages_and_checkpoint(gmail):
    _, sessions, _, provider, _, _, source = gmail
    authorize(gmail)
    provider.full_pages = {None: {"messages": [{"id": "one"}, {"id": "two"}]}}
    provider.envelopes["two"] = 503
    worker = worker_for(gmail)
    assert worker.run_once()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 0
        assert session.get(GmailSource, source).history_id is None
    del provider.envelopes["two"]
    assert worker.run_once()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 2


def test_revoked_grant_disconnect_plan_isolation_and_review(gmail):
    api, sessions, _, provider, _, plan, source = gmail
    authorize(gmail)
    provider.envelopes["one"] = {"id": "one", "raw": "!bad!"}
    provider.envelopes["two"] = 404
    worker = worker_for(gmail)
    assert worker.run_once() and worker.run_once()
    response = api.get(f"/plans/{plan}/gmail/{source}/messages?limit=1")
    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "review"
    next_after = response.json()["next_after"]
    assert (
        api.get(f"/plans/{plan}/gmail/{source}/messages?after={next_after}").json()[
            "items"
        ][0]["status"]
        == "unavailable"
    )
    assert api.get(f"/plans/{uuid4()}/gmail/{source}/messages").status_code == 404
    assert (
        api.post(f"/plans/{uuid4()}/gmail/{source}/disconnect", json={}).status_code
        == 404
    )
    provider.failure = 400
    assert worker.run_once()
    with sessions() as session:
        assert session.get(GmailSource, source).status == "needs_authorization"
    assert not worker.run_once()
    assert (
        api.post(f"/plans/{plan}/gmail/{source}/disconnect", json={}).status_code == 200
    )
    with sessions() as session:
        assert session.get(GmailSource, source).refresh_token_ciphertext is None
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 2


def test_concurrent_schedulers_and_workers_ingest_once(gmail):
    _, sessions, settings, _, _, _, source = gmail
    authorize(gmail)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: schedule_due(sessions, settings), range(2)))
        list(pool.map(lambda _: worker_for(gmail).run_once(), range(2)))
    with sessions() as session:
        rows = session.scalars(select(GmailMessage)).all()
        assert len({row.gmail_id for row in rows}) == len(rows)
        assert len(rows) >= 1


def test_reconnect_cannot_replace_mailbox_identity_or_duplicate_connection(gmail):
    api, sessions, _, provider, _, plan, source = gmail
    authorize(gmail)
    assert worker_for(gmail).run_once()
    with sessions() as session:
        original = session.get(GmailSource, source)
        saved_credential, pending = (
            original.refresh_token_ciphertext,
            original.pending_job_id,
        )
    for source_id, email, expected in [
        (source, "another@example.com", "mailbox_mismatch"),
        (uuid4(), "me@example.com", "mailbox_already_connected"),
    ]:
        provider.email = email
        result = api.post(f"/plans/{plan}/gmail/{source_id}/oauth", json={})
        state = parse_qs(urlparse(result.json()["authorization_url"]).query)["state"][0]
        response = api.get(
            "/gmail/oauth/callback", params={"state": state, "code": "code"}
        )
        assert response.status_code == 409
        assert response.json()["detail"] == expected
        assert (
            api.get(
                "/gmail/oauth/callback", params={"state": state, "code": "code"}
            ).status_code
            == 400
        )
    with sessions() as session:
        original = session.get(GmailSource, source)
        assert original.email == "me@example.com"
        assert original.refresh_token_ciphertext == saved_credential
        assert original.pending_job_id == pending
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 1


def test_disconnect_fences_pending_jobs_and_outstanding_oauth(gmail):
    api, sessions, settings, provider, client, plan, source = gmail
    authorize(gmail)
    result = api.post(f"/plans/{plan}/gmail/{source}/oauth", json={})
    state = parse_qs(urlparse(result.json()["authorization_url"]).query)["state"][0]
    with sessions() as session:
        pending = session.get(Job, session.get(GmailSource, source).pending_job_id)
    assert (
        api.post(f"/plans/{plan}/gmail/{source}/disconnect", json={}).status_code == 200
    )
    provider.calls.clear()
    handle_job(sessions, settings, pending, client)
    assert (
        api.get(
            "/gmail/oauth/callback", params={"state": state, "code": "code"}
        ).status_code
        == 400
    )
    assert provider.calls == []
    with sessions() as session:
        assert session.get(GmailSource, source).status == "disconnected"
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 0


def test_evidence_immutable_at_database_boundary(gmail):
    _, sessions, _, _, _, _, _ = gmail
    authorize(gmail)
    assert worker_for(gmail).run_once()
    for statement in (
        "UPDATE gmail_messages SET decoded = '{}'",
        "DELETE FROM gmail_messages",
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            with sessions.begin() as session:
                session.execute(text(statement))
    with sessions() as session:
        columns = inspect(session.bind).get_columns("gmail_sources")
        assert not any(
            column["name"] in {"password", "refresh_token", "access_token"}
            for column in columns
        )


@pytest.mark.parametrize("mode", ["full", "history"])
def test_filtered_candidates_never_download_or_store_excluded_bodies(gmail, mode):
    api, sessions, _, provider, _, plan, source = gmail
    authorize(gmail)
    worker = worker_for(gmail)
    if mode == "history":
        provider.full_pages = {None: {}}
        assert worker.run_once()
    ids = ["approved", "unrelated", "spoof", "missing", "spam", "trash", "gone"]
    provider.full_pages = {None: {"messages": [{"id": x} for x in ids]}}
    provider.history_pages = {None: {"historyId": "200", "history": [{
        "messagesAdded": [{"message": {"id": x}} for x in ids],
        "labelsAdded": [{"message": {"id": "unrelated"}}],
    }]}}
    for gmail_id, value, labels in [
        ("unrelated", "friend@example.com", []),
        ("spoof", '"notice@example.com" <attacker@example.com>', []),
        ("missing", "", []),
        ("spam", "notice@example.com", ["SPAM"]),
        ("trash", "notice@example.com", ["TRASH"]),
    ]:
        provider.metadata[gmail_id] = {"id": gmail_id, "labelIds": labels,
            "payload": {"headers": [{"name": "From", "value": value}]}}
        provider.envelopes[gmail_id] = 503  # A raw fetch here would fail the page.
    provider.metadata["gone"] = 404
    provider.envelopes["gone"] = 503
    provider.calls.clear()
    assert worker.run_once()
    raw_calls = [r for r in provider.calls if r.url.params.get("format") == "raw"]
    assert [r.url.path.rsplit("/", 1)[-1] for r in raw_calls] == ["approved"]
    header_calls = [r for r in provider.calls if r.url.params.get("format") == "metadata"]
    assert all(r.url.params["metadataHeaders"] == "From" for r in header_calls)
    assert all(r.url.params["fields"] == "id,labelIds,payload/headers" for r in header_calls)
    with sessions() as session:
        assert [row.gmail_id for row in session.scalars(select(GmailMessage))] == ["approved"]
        assert session.get(GmailSource, source).history_id == ("100" if mode == "full" else "200")
    assert len(api.get(f"/plans/{plan}/gmail/{source}/messages").json()["items"]) == 1


def test_saved_scope_survives_defaults_change_restart_and_404_then_reconnects(gmail):
    _, sessions, settings, provider, _, _, source = gmail
    authorize(gmail)
    assert worker_for(gmail).run_once()
    settings.gmail_allowed_senders = ["other@example.com"]
    # New worker/session uses the persisted filter for the remaining page.
    assert worker_for(gmail).run_once()
    with sessions() as session:
        assert session.get(GmailSource, source).allowed_senders == ["notice@example.com"]
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 2
    provider.history_expired = True
    assert worker_for(gmail).run_once()
    assert worker_for(gmail).run_once()
    assert worker_for(gmail).run_once()
    list_calls = [r for r in provider.calls if r.url.path.endswith("/messages")]
    assert all(r.url.params["q"] == "{from:notice@example.com}" for r in list_calls)
    authorize(gmail)  # Explicit adoption of the new scope.
    with sessions() as session:
        record = session.get(GmailSource, source)
        assert record.allowed_senders == ["other@example.com"]
        assert record.sync_mode == "full" and record.history_id is None
    provider.full_pages = {None: {"messages": [{"id": "new"}, {"id": "excluded"}]}}
    provider.metadata["new"] = {"id": "new", "payload": {"headers": [
        {"name": "From", "value": "other@example.com"}]}}
    assert worker_for(gmail).run_once()
    with sessions() as session:
        assert {row.gmail_id for row in session.scalars(select(GmailMessage))} == {"one", "two", "new"}


def test_unscoped_source_fails_closed_without_provider_calls(gmail):
    _, sessions, _, provider, _, _, source = gmail
    authorize(gmail)
    with sessions.begin() as session:
        session.get(GmailSource, source).allowed_senders = []
    provider.calls.clear()
    assert worker_for(gmail).run_once()
    assert provider.calls == []
    with sessions() as session:
        record = session.get(GmailSource, source)
        assert record.status == "needs_authorization"
        assert record.last_error == "ingestion_filter_required"
        assert record.pending_job_id is None
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 0


def test_empty_defaults_do_not_broaden_or_change_existing_saved_scope(gmail):
    api, sessions, settings, provider, _, plan, source = gmail
    authorize(gmail)
    settings.gmail_allowed_senders = []
    assert worker_for(gmail).run_once()
    assert worker_for(gmail).run_once()
    assert api.get(f"/plans/{plan}/gmail").json()["configured"] is False
    assert api.post(f"/plans/{plan}/gmail/{source}/oauth", json={}).status_code == 503
    with sessions() as session:
        assert session.get(GmailSource, source).allowed_senders == ["notice@example.com"]
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 2


def test_metadata_failure_rolls_back_page_without_downloading_failed_body(gmail):
    _, sessions, _, provider, _, _, source = gmail
    authorize(gmail)
    provider.full_pages = {None: {"messages": [{"id": "one"}, {"id": "two"}]}}
    provider.metadata["two"] = 503
    assert worker_for(gmail).run_once()
    assert not any(r.url.path.endswith("/two") and r.url.params.get("format") == "raw" for r in provider.calls)
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 0
        assert session.get(GmailSource, source).full_sync_history_id is None
        session.get(Job, session.get(GmailSource, source).pending_job_id).available_at = utc_now()
        session.commit()
    provider.metadata.pop("two")
    assert worker_for(gmail).run_once()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(GmailMessage)) == 2
