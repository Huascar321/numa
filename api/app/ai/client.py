from __future__ import annotations

import json
from typing import Any
import httpx

from app.ai.schemas import StructuredLLMSuggestion


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class AIProviderError(Exception):
    """Raised when an AI provider returns an error or malformed response."""


class AIProviderUnavailableError(AIProviderError):
    """Raised when the AI provider is unreachable or experiencing an outage."""


class AIClient:
    """Client for calling OpenRouter, Groq, or custom OpenAI-compatible AI providers."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=30.0)

    def _get_endpoint(self, provider: str, base_url: str | None = None) -> str:
        if base_url:
            return base_url.rstrip("/") + "/chat/completions" if not base_url.endswith("/chat/completions") else base_url
        if provider == "groq":
            return GROQ_ENDPOINT
        return OPENROUTER_ENDPOINT

    def generate_structured_completion(
        self,
        *,
        provider: str,
        model: str,
        api_key: str,
        messages: list[dict[str, str]],
        base_url: str | None = None,
        schema: type[StructuredLLMSuggestion] = StructuredLLMSuggestion,
    ) -> dict[str, Any]:
        """Send chat completion request expecting JSON / structured response."""
        endpoint = self._get_endpoint(provider, base_url)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/numa"
            headers["X-Title"] = "Numa Finance"

        json_schema = schema.model_json_schema()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {
                "type": "json_object",
            },
        }

        # If provider is groq or openrouter, attempt structured schema output if supported
        if provider == "groq":
            payload["response_format"] = {
                "type": "json_object",
            }
        elif provider == "openrouter":
            payload["response_format"] = {
                "type": "json_object",
            }

        client = self._get_client()
        try:
            response = client.post(endpoint, headers=headers, json=payload)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIProviderUnavailableError(f"AI provider network failure: {exc}") from exc
        except Exception as exc:
            raise AIProviderError(f"Unexpected AI request error: {exc}") from exc

        if response.status_code >= 500:
            raise AIProviderUnavailableError(
                f"AI provider returned server error {response.status_code}: {response.text}"
            )
        if response.status_code != 200:
            raise AIProviderError(
                f"AI provider returned error {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise AIProviderError("AI provider returned unparsable HTTP response") from exc

        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            raise AIProviderError("AI provider response missing choices")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise AIProviderError("AI provider returned empty message content")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"AI provider response content is not valid JSON: {content}") from exc
