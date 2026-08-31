from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    ai_api_key: str | None = None
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    exchange_api_key: str | None = None
    worker_poll_seconds: int = 5
    worker_lease_seconds: int = 60
    reconciliation_policy: Literal["block", "warn"] = "block"
    reconciliation_tolerance_atoms: int = Field(default=0, ge=0)

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for database-backed operation.")
        return self.database_url
