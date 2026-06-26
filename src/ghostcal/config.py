"""Application configuration — 12-factor, validated, fail-fast at startup.

All configuration comes from the environment (or a local .env in development). Importing
``settings`` triggers validation; a missing or malformed required value raises immediately
rather than failing deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GHOSTCAL_",
        extra="forbid",
    )

    environment: Literal["development", "staging", "production"] = "development"

    # Core infrastructure.
    # database_url: the *application* connection — a NON-superuser, NON-BYPASSRLS role, so
    #   Row-Level Security policies always apply.
    # database_admin_url: a privileged role used only by Alembic migrations and role bootstrap
    #   (owns the schema, creates policies). Never used to serve requests.
    database_url: PostgresDsn
    database_admin_url: PostgresDsn | None = None
    redis_url: RedisDsn

    # Auth / crypto
    secret_key: SecretStr = Field(min_length=32)
    access_token_ttl_seconds: int = 900  # 15 min
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days

    # Encryption key for calendar tokens at rest (envelope key, base64)
    token_encryption_key: SecretStr = Field(min_length=32)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Call sites depend on this, not the module-level instance,
    so tests can override the environment before first access."""
    return Settings()  # values come from the environment
