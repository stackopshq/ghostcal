"""Application configuration — 12-factor, validated, fail-fast at startup.

All configuration comes from the environment (or a local .env in development). Importing
``settings`` triggers validation; a missing or malformed required value raises immediately
rather than failing deep inside a request.
"""

from __future__ import annotations

import ipaddress
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

    # Where the sibling GhostMail lives, if this deployment has one.
    #
    # Served to the browser at runtime rather than compiled in. The "email these
    # guests" button used to read NEXT_PUBLIC_GHOSTMAIL_URL, which Next inlines
    # at BUILD time -- so the published image carried `http://localhost:3002` in
    # its bundle, and setting the variable on the host changed nothing. Measured
    # 2026-08-16: the button opened a dead tab on the user's own machine.
    #
    # None means no GhostMail here, and the frontend hides the button rather
    # than offering a link that goes nowhere. Absent is a real answer for a
    # self-hosted product: most deployments run one app, not the suite.
    ghostmail_url: str | None = None

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
    # Expected ``aud`` on a GhostAuth access token presented by the ghostboard portal. Defaults to
    # the client id — the common case, where GhostAuth mints tokens whose audience is the requesting
    # client. Set this when the realm issues a distinct resource identifier instead.
    oidc_audience: str | None = None
    # Treat the address as vouched for when it comes from `oidc_issuer`, even
    # though the provider never emits `email_verified`.
    #
    # **False by default, and it must stay that way.** The address is what proves
    # who the caller is: it links an SSO login to an existing account, and it is
    # what `accept_organization_invitation` accepts as ownership of an invited
    # address. An address the provider has not vouched for is worth nothing here,
    # and an absent claim counts as unverified — a provider that omits it has not
    # made the assertion.
    #
    # Some providers never make it while still guaranteeing the identity by other
    # means. Cloudflare Access is one: its OIDC discovery advertises no
    # `claims_supported`, yet the identity comes from Google Workspace and its
    # Access policy decides who may even reach the consent screen. Measured on
    # 2026-08-13 — **no first SSO login could succeed, for anyone**, and the
    # refusal was indistinguishable from a deliberate configuration.
    #
    # This flag therefore moves the proof **from the claim to the issuer**. It
    # applies only to identities whose issuer is exactly `oidc_issuer`, never to
    # any other. Turn it on only if the answer is yes to: *does this issuer
    # already refuse addresses it has not verified possession of?*
    oidc_trust_issuer_email: bool = False

    # How often the worker re-syncs each connected CalDAV calendar's busy time.
    caldav_sync_interval_seconds: int = 900  # 15 min
    # How often the worker refreshes subscribed public ICS feeds.
    subscription_sync_interval_seconds: int = 3600  # 1 h

    # Which peers may be believed when they send X-Forwarded-For.
    #
    # The app sits behind the Next same-origin proxy, so the socket peer is the proxy and the real
    # client is in the header. But a header is client-controlled: honouring it from *any* peer lets
    # anyone mint a fresh rate-limit bucket per request, which is what the auth limiter exists to
    # prevent. Only peers inside these ranges are believed; everyone else is rate-limited on the
    # address they actually connected from.
    #
    # Defaults to loopback and the private ranges, which is where a reverse proxy lives in every
    # supported topology. Set it to [] if the app is exposed directly, with no proxy in front.
    trusted_proxy_cidrs: list[str] = [
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    ]

    # Private networks the server may fetch calendars from, e.g. ["192.168.1.0/24"].
    #
    # Empty by default, which is the right posture for a hosted deployment: the SSRF guard refuses
    # every private address. But GhostCal is self-hostable, and a self-hoster's Nextcloud or
    # Radicale lives on their LAN, so under the default they could never connect their own
    # calendar. Naming a range here opens exactly that range and nothing else.
    #
    # It applies to CalDAV connections and ICS subscriptions only — never to webhooks, whose
    # target any org manager can set, and never to the link-local range, so the cloud-metadata
    # address (169.254.169.254) stays unreachable however this is configured.
    calendar_allowed_private_cidrs: list[str] = []

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

    # Database connection pool, per process. The app, the Celery worker and beat each hold their
    # own, so the ceiling is (pool + overflow) x processes — size it against Postgres
    # `max_connections` (100 by default) rather than discovering the limit under load.
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Hard limits on how long one statement, or one idle transaction, may hold a connection.
    # Without these a single pathological query pins a connection until someone notices, and the
    # first real load event becomes an outage instead of a slowdown. Generous enough that no
    # legitimate query is near them.
    db_statement_timeout_ms: int = 15_000
    db_idle_in_transaction_timeout_ms: int = 30_000

    # How long computed availability is cached (seconds). Short, so freshly-taken slots clear fast.
    availability_cache_ttl_seconds: int = 45

    # Check new passwords against the Have I Been Pwned breach corpus.
    #
    # Uses the k-anonymity range API: five hex characters of the password's SHA-1 leave this
    # server, nothing else — no account identifier, no cookies — and the comparison happens here
    # among the several hundred hashes sharing that prefix. Small, but not nothing, which is why
    # it is a switch: set false for a deployment that must make no third-party calls at all.
    # The check fails open, so an unreachable HIBP never blocks a registration.
    password_breach_check_enabled: bool = True

    # Port the Celery worker serves its Prometheus metrics on. Counters incremented in a worker
    # are invisible to the API's /metrics — a different process, a different registry — so the
    # worker exposes its own. Set 0 to disable.
    metrics_port: int = 9101

    # Celery task limits. Soft raises an exception the task can unwind from; hard kills it.
    # Nothing in this app should legitimately run for minutes.
    task_soft_time_limit_seconds: int = 300  # 5 min
    task_time_limit_seconds: int = 360  # 6 min

    # How many times a network-bound task retries, and the first backoff step (doubling, jittered).
    task_max_retries: int = 3
    task_retry_backoff_seconds: int = 10

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
    def _parse_allowed_private_cidrs(self) -> Settings:
        # Fail fast: a typo'd CIDR would otherwise surface as a calendar that silently never
        # connects, which is indistinguishable from the guard doing its job.
        for cidr in self.calendar_allowed_private_cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(
                    f"calendar_allowed_private_cidrs: {cidr!r} is not a network"
                ) from exc
            if network.is_link_local:
                raise ValueError(
                    f"calendar_allowed_private_cidrs: {cidr!r} is link-local, which the egress "
                    "guard never opens (it holds the cloud-metadata address)"
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
