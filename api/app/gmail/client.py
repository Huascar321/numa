from __future__ import annotations

import base64
import hashlib
import json
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.settings import Settings

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALLBACK_PATH = "/gmail/oauth/callback"


class GmailConfigurationError(Exception):
    def __init__(self) -> None:
        super().__init__("Gmail server configuration is missing or invalid.")


class GmailError(Exception):
    """Only stable codes are exposed or persisted; provider bodies may contain secrets."""

    def __init__(self, code: str, *, retryable: bool = False, status: int = 0) -> None:
        super().__init__(code)
        self.code, self.retryable, self.status = code, retryable, status


def token_cipher(settings: Settings) -> Fernet:
    try:
        return Fernet((settings.gmail_token_key or "").encode("ascii"))
    except (ValueError, UnicodeError):
        raise GmailConfigurationError() from None


def require_configuration(settings: Settings) -> None:
    try:
        uri = urlparse(settings.gmail_redirect_uri or "")
    except ValueError:
        raise GmailConfigurationError() from None
    if not (
        settings.gmail_client_id
        and settings.gmail_client_secret
        and uri.hostname
        and not uri.username
        and not uri.password
        and not uri.fragment
        and not uri.query
        and uri.path == CALLBACK_PATH
        and (
            uri.scheme == "https"
            or (uri.scheme == "http" and uri.hostname in {"localhost", "127.0.0.1"})
        )
    ):
        raise GmailConfigurationError()
    token_cipher(settings)


def require_sender_configuration(settings: Settings) -> None:
    if not settings.gmail_allowed_senders:
        raise GmailConfigurationError()


def encrypt_secret(settings: Settings, owner: str, value: str) -> str:
    return token_cipher(settings).encrypt(json.dumps([owner, value]).encode()).decode()


def decrypt_secret(settings: Settings, owner: str, value: str) -> str:
    try:
        stored_owner, secret = json.loads(
            token_cipher(settings).decrypt(value.encode())
        )
        if stored_owner != owner or not isinstance(secret, str):
            raise ValueError()
        return secret
    except (InvalidToken, ValueError, UnicodeError):
        raise GmailError("credential_unreadable") from None


def authorization_url(settings: Settings, state: str, verifier: str) -> str:
    require_configuration(settings)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.gmail_client_id,
            "redirect_uri": settings.gmail_redirect_uri,
            "response_type": "code",
            "scope": READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


class GmailClient:
    def __init__(
        self, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        require_configuration(settings)
        self.settings = settings
        self.http = httpx.Client(timeout=15, transport=transport)

    def close(self) -> None:
        self.http.close()

    def _request(self, method: str, url: str, **kwargs: object) -> dict:
        try:
            response = self.http.request(method, url, **kwargs)
        except httpx.RequestError:
            raise GmailError("gmail_unavailable", retryable=True) from None
        if response.status_code >= 400:
            try:
                error = response.json().get("error")
            except (ValueError, AttributeError):
                error = None
            if error == "invalid_grant" or response.status_code == 401:
                raise GmailError("authorization_required", status=response.status_code)
            rate_limited = response.status_code == 429 or (
                response.status_code == 403
                and isinstance(error, dict)
                and any(
                    item.get("reason")
                    in {"rateLimitExceeded", "userRateLimitExceeded", "backendError"}
                    for item in error.get("errors", [])
                    if isinstance(item, dict)
                )
            )
            raise GmailError(
                "gmail_request_failed",
                retryable=rate_limited or response.status_code >= 500,
                status=response.status_code,
            )
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except ValueError:
            raise GmailError("invalid_provider_response", retryable=True) from None

    def _token(self, fields: dict) -> dict:
        return self._request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.settings.gmail_client_id,
                "client_secret": self.settings.gmail_client_secret,
                **fields,
            },
        )

    def exchange_code(self, code: str, verifier: str) -> dict:
        return self._token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": self.settings.gmail_redirect_uri,
            }
        )

    def refresh(self, refresh_token: str) -> dict:
        return self._token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    def get(self, access_token: str, path: str, **params: str) -> dict:
        return self._request(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/" + path,
            headers={"Authorization": "Bearer " + access_token},
            params=params,
        )


def required_string(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise GmailError("invalid_provider_response", retryable=True)
    return value


def access_token(body: dict, *, require_scope: bool = False) -> str:
    if require_scope or "scope" in body:
        scope = body.get("scope", "")
        if not isinstance(scope, str) or scope.split() != [READONLY_SCOPE]:
            raise GmailError("readonly_scope_required")
    return required_string(body, "access_token")
