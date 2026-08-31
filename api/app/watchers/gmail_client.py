from __future__ import annotations

import urllib.parse
from typing import Any
import httpx

from app.settings import Settings


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailNotConfiguredError(Exception):
    """Raised when Gmail OAuth credentials are missing from server configuration."""


class GmailHistoryExpiredError(Exception):
    """Raised when Gmail API returns 404 for a historyId cursor, requiring a full resync."""


class GmailApiError(Exception):
    """Raised when Gmail API returns an unexpected error response."""


class GmailClient:
    """Client for interacting with Google OAuth and the Gmail API."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=30.0)

    def require_credentials(self) -> tuple[str, str]:
        if not self.settings.gmail_client_id or not self.settings.gmail_client_secret:
            raise GmailNotConfiguredError(
                "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required for Gmail integration."
            )
        return self.settings.gmail_client_id, self.settings.gmail_client_secret

    def build_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Google OAuth 2.0 authorization URL with readonly scope."""
        client_id, _ = self.require_credentials()
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
        password: str | None = None,
    ) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens.

        Strictly rejects password parameter if provided.
        """
        if password is not None:
            raise ValueError("Password collection is strictly prohibited.")

        client_id, client_secret = self.require_credentials()
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        client = self._get_client()
        response = client.post(GOOGLE_TOKEN_ENDPOINT, data=payload)
        if response.status_code != 200:
            raise GmailApiError(f"OAuth code exchange failed: {response.text}")
        return response.json()

    def refresh_access_token(self, refresh_token: str) -> str:
        """Obtain a new access token using a refresh token."""
        client_id, client_secret = self.require_credentials()
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        client = self._get_client()
        response = client.post(GOOGLE_TOKEN_ENDPOINT, data=payload)
        if response.status_code != 200:
            raise GmailApiError(f"Token refresh failed: {response.text}")
        token_data = response.json()
        return str(token_data["access_token"])

    def get_user_profile(self, access_token: str) -> dict[str, Any]:
        """Fetch the authenticated user's email address and current historyId."""
        headers = {"Authorization": f"Bearer {access_token}"}
        client = self._get_client()
        response = client.get(f"{GMAIL_API_BASE}/profile", headers=headers)
        if response.status_code != 200:
            raise GmailApiError(f"Failed to fetch user profile: {response.text}")
        return response.json()

    def list_messages(
        self,
        access_token: str,
        query: str | None = None,
        max_results: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List messages in the mailbox (for full initial synchronization)."""
        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        client = self._get_client()
        response = client.get(f"{GMAIL_API_BASE}/messages", headers=headers, params=params)
        if response.status_code != 200:
            raise GmailApiError(f"Failed to list messages: {response.text}")
        return response.json()

    def get_message(
        self,
        access_token: str,
        message_id: str,
        format_type: str = "full",
    ) -> dict[str, Any]:
        """Fetch full details of a specific message."""
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"format": format_type}
        client = self._get_client()
        response = client.get(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            headers=headers,
            params=params,
        )
        if response.status_code != 200:
            raise GmailApiError(f"Failed to fetch message {message_id}: {response.text}")
        return response.json()

    def list_history(
        self,
        access_token: str,
        start_history_id: str,
        max_results: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch history records since start_history_id.

        Raises GmailHistoryExpiredError on HTTP 404 (cursor expired).
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token

        client = self._get_client()
        response = client.get(f"{GMAIL_API_BASE}/history", headers=headers, params=params)

        if response.status_code == 404:
            raise GmailHistoryExpiredError(
                f"Gmail history cursor {start_history_id} is expired or invalid (HTTP 404)."
            )

        if response.status_code == 400:
            # Google sometimes returns 400 with "historyId not found" or "Invalid historyId"
            err_text = response.text.lower()
            if "historyid" in err_text or "not found" in err_text:
                raise GmailHistoryExpiredError(
                    f"Gmail history cursor {start_history_id} is expired or invalid (HTTP 400): {response.text}"
                )
            raise GmailApiError(f"Gmail history API error: {response.text}")

        if response.status_code != 200:
            raise GmailApiError(f"Failed to list history: {response.text}")

        return response.json()
