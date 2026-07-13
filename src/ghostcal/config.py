"""Application configuration — 12-factor, validated, fail-fast at startup.

All configuration comes from the environment (or a local .env in development). Importing
``settings`` triggers validation; a missing or malformed required value raises immediately
rather than failing deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GHOSTCAL_",
        extra="forbid",
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Browser origins allowed to call the API (the Next.js frontend in dev).
    cors_allow_origins: list[str] = ["http://localhost:3000"]

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
    email_verification_ttl_seconds: int = 60 * 60 * 24  # 24 h
    invitation_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # Encryption key for calendar tokens at rest (envelope key, base64)
    token_encryption_key: SecretStr = Field(min_length=32)

    # Where the frontend lives — used to build links sent by email.
    frontend_base_url: str = "http://localhost:3001"

    # SSO / OIDC (single operator-configured provider). Off by default: when disabled, the OIDC
    # routes 404 and the frontend hides the SSO button. Authentication only — the zero-knowledge
    # content is still unlocked by a separate encryption passphrase (the server never sees it).
    oidc_enabled: bool = False
    oidc_issuer: str | None = None  # e.g. https://accounts.google.com — discovery via .well-known
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    # The provider redirects here after consent; must exactly match the app's callback URL and be
    # registered with the IdP. Defaults to the API's own callback if unset.
    oidc_redirect_uri: str | None = None

    # How often the worker re-syncs each connected CalDAV calendar's busy time.
    caldav_sync_interval_seconds: int = 900  # 15 min
    # How often the worker refreshes subscribed public ICS feeds.
    subscription_sync_interval_seconds: int = 3600  # 1 h

    # Booking reminders: how often the worker scans for due reminders, and the offsets (minutes
    # before the meeting) at which an invitee is reminded. Default: 24 h and 1 h before.
    reminder_scan_interval_seconds: int = 300  # 5 min
    reminder_offsets_minutes: list[int] = [1440, 60]

    # How often the worker purges bookings past their organization's retention window. Daily: the
    # window is measured in days, so scanning more often would only burn cycles — and this is the
    # one periodic job that destroys data.
    retention_purge_interval_seconds: int = 86400  # 24 h

    # Per-IP rate limits (requests/minute) on abuse-prone public endpoints.
    booking_rate_limit_per_minute: int = 20
    vote_rate_limit_per_minute: int = 60
    # Tighter limit on auth endpoints (login/register/etc.): brute-force + Argon2 CPU-DoS guard.
    auth_rate_limit_per_minute: int = 10

    # How long computed availability is cached (seconds). Short, so freshly-taken slots clear fast.
    availability_cache_ttl_seconds: int = 45

    # Transactional email (Resend). When the API key is unset, emails are logged instead of sent.
    resend_api_key: SecretStr | None = None
    email_from: str = "GhostCal <onboarding@resend.dev>"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _reject_placeholder_secrets(self) -> Settings:
        # Outside development, refuse the .env.example placeholders so a half-configured deploy
        # can't ship a publicly-known signing/encryption key (JWT forgery / dump decryption).
        if self.environment == "development":
            return self
        for name in ("secret_key", "token_encryption_key"):
            value = getattr(self, name).get_secret_value()
            if "change-me" in value.lower():
                raise ValueError(
                    f"{name} is still a placeholder — set a real secret outside development"
                )
        return self

    @model_validator(mode="after")
    def _require_oidc_config_when_enabled(self) -> Settings:
        # Fail fast: enabling OIDC without a full provider config would 500 on first login.
        if self.oidc_enabled and not (
            self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret
        ):
            raise ValueError(
                "oidc_enabled=true requires oidc_issuer, oidc_client_id and oidc_client_secret"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Call sites depend on this, not the module-level instance,
    so tests can override the environment before first access."""
    return Settings()  # values come from the environment
