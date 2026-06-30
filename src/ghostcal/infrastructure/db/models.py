"""SQLAlchemy ORM models — Phase 1 schema.

Tenancy: every business object carries ``organization_id`` and is protected by Row-Level
Security (see the initial migration). ``users``/``identities``/``user_credentials`` are global
identity tables (a user may belong to several organizations) and are reached only through
org-scoped ``memberships``.

Enum-like columns use plain strings plus CHECK constraints (defined in the migration) to keep
schema changes simple; allowed values are exposed here as constants.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ghostcal.infrastructure.db.base import Base, TimestampMixin
from ghostcal.infrastructure.db.types import EncryptedString, EncryptedStringList

# Allowed string-enum values.
MEMBERSHIP_ROLES = ("owner", "admin", "member")
IDENTITY_PROVIDERS = ("google", "microsoft", "oidc")
BOOKING_STATUSES = ("confirmed", "cancelled", "rescheduled")
# How an event type assigns hosts: the owner (solo), one host picked from a pool (round_robin),
# every pooled host required (collective), or many invitees per slot up to capacity (group).
EVENT_KINDS = ("solo", "round_robin", "collective", "group")
POLL_STATUSES = ("open", "finalized", "cancelled")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    # Base64 X25519 public key invitees seal their answers to (zero-knowledge). The matching
    # private key is never stored server-side; only per-member wrapped copies live in
    # ``org_member_keys``. NULL only for legacy orgs created before zero-knowledge.
    zk_public_key: Mapped[str | None] = mapped_column(Text)


class OrgMemberKey(TimestampMixin, Base):
    """A member's wrapped copy of their organization's zero-knowledge private key.

    The org private key is wrapped (libsodium secretbox) under a key derived from the member's
    password via Argon2id, and a second time under their one-time recovery phrase. The server
    stores only these wrapped blobs and the KDF salts — never the private key or any derived key,
    so it can never decrypt invitee answers.
    """

    __tablename__ = "org_member_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    wrapped_private_key: Mapped[str] = mapped_column(Text)
    wrap_salt: Mapped[str] = mapped_column(Text)
    recovery_wrapped_private_key: Mapped[str] = mapped_column(Text)
    recovery_salt: Mapped[str] = mapped_column(Text)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))


class Identity(TimestampMixin, Base):
    """Federated login identity (distinct from a calendar access grant)."""

    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("provider", "issuer", "subject"),
        CheckConstraint(f"provider IN {IDENTITY_PROVIDERS}", name="provider_allowed"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))


class EmailVerificationToken(TimestampMixin, Base):
    """Single-use email-verification token. Only the hash is stored."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(TimestampMixin, Base):
    """Rotating refresh token. Only the hash is stored; rotation revokes the previous one."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint(f"role IN {MEMBERSHIP_ROLES}", name="role_allowed"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="member")


class OrganizationInvitation(TimestampMixin, Base):
    """Pending invitation to join an organization. Only the token hash is stored."""

    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint(f"role IN {MEMBERSHIP_ROLES}", name="invitation_role_allowed"),
        Index(
            "uq_pending_invitation_per_email",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20), default="member")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class EventType(TimestampMixin, Base):
    __tablename__ = "event_types"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug"),
        CheckConstraint("duration_min > 0", name="duration_positive"),
        CheckConstraint("slot_interval_min > 0", name="slot_interval_positive"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # The availability schedule this event type uses. Null falls back to the owner's first
    # schedule (kept for backwards compatibility and simple single-schedule setups).
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("availability_schedules.id", ondelete="SET NULL")
    )
    slug: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    buffer_before_min: Mapped[int] = mapped_column(SmallInteger, default=0)
    buffer_after_min: Mapped[int] = mapped_column(SmallInteger, default=0)
    min_notice_min: Mapped[int] = mapped_column(default=0)
    slot_interval_min: Mapped[int] = mapped_column(SmallInteger, default=15)
    date_window_days: Mapped[int] = mapped_column(SmallInteger, default=60)
    max_per_day: Mapped[int | None] = mapped_column(SmallInteger)
    location_type: Mapped[str] = mapped_column(String(20), default="google_meet")
    # Host-assignment strategy. "solo" uses the owner; "round_robin" picks from event_type_hosts.
    kind: Mapped[str] = mapped_column(String(20), default="solo", server_default="solo")
    # Max invitees per slot (group event types). 1 for everything else.
    capacity: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    # Optional URL to send the invitee to after a successful booking.
    redirect_url: Mapped[str | None] = mapped_column(String(2048))
    price_cents: Mapped[int | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(default=True)
    # Custom questions asked of the invitee at booking time: [{id,label,type,required,options}].
    booking_questions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class EventTypeHost(TimestampMixin, Base):
    """A host in a round-robin (or future collective) event type's pool."""

    __tablename__ = "event_type_hosts"
    __table_args__ = (UniqueConstraint("event_type_id", "user_id"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    event_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_types.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class AvailabilitySchedule(TimestampMixin, Base):
    __tablename__ = "availability_schedules"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64))

    rules: Mapped[list[AvailabilityRule]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )
    overrides: Mapped[list[AvailabilityOverride]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class AvailabilityRule(Base):
    """Weekly recurring local-time window (e.g. Monday 09:00-18:00)."""

    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("start_time < end_time", name="rule_time_order"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("availability_schedules.id", ondelete="CASCADE")
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    schedule: Mapped[AvailabilitySchedule] = relationship(back_populates="rules")


class AvailabilityOverride(Base):
    """One-off change for a specific date (holiday, or different hours)."""

    __tablename__ = "availability_overrides"
    __table_args__ = (UniqueConstraint("schedule_id", "date"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("availability_schedules.id", ondelete="CASCADE")
    )
    date: Mapped[date] = mapped_column(Date)
    is_available: Mapped[bool] = mapped_column(default=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)

    schedule: Mapped[AvailabilitySchedule] = relationship(back_populates="overrides")


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(f"status IN {BOOKING_STATUSES}", name="status_allowed"),
        CheckConstraint("start_at < end_at", name="booking_time_order"),
        # No two confirmed *blocking* bookings for the same host may overlap. The real guarantee.
        # Group bookings set blocks_host=false so many invitees can share one slot (capacity).
        ExcludeConstraint(
            ("host_id", "="),
            ("period", "&&"),
            using="gist",
            where=text("status = 'confirmed' AND blocks_host"),
            name="no_overlap_per_host",
        ),
        Index("ix_bookings_org_period", "organization_id", "period", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    event_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_types.id", ondelete="RESTRICT")
    )
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Zero-knowledge: the invitee's name lives in the sealed ``invitee_private`` blob, never here.
    # The column stays only for legacy/None — the server never receives a name through booking.
    invitee_name: Mapped[str | None] = mapped_column(String(200))
    # Encrypted at rest (the server still needs it to send confirmation/reminder emails).
    invitee_email: Mapped[str] = mapped_column(EncryptedString)
    invitee_timezone: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period: Mapped[object] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(start_at, end_at, '[)')", persisted=True),
    )
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    # Encrypted at rest (they appear in confirmation/reminder emails and the host's calendar).
    location: Mapped[str | None] = mapped_column(EncryptedString)
    meeting_url: Mapped[str | None] = mapped_column(EncryptedString)
    # Collective bookings insert one row per required host, all sharing this id (so cancel/manage
    # act on the whole meeting). NULL for solo/round-robin/group bookings.
    collective_group_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    # Whether this booking occupies the host exclusively (the no-overlap guarantee). Group bookings
    # set this false so a slot can hold up to the event type's capacity.
    blocks_host: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Additional guest emails — encrypted at rest (the server emails them, so it holds the key).
    guest_emails: Mapped[list[str]] = mapped_column(EncryptedStringList, default=list)
    # The invitee's answers to the custom questions plus the free-text notes, sealed to the
    # organization's zk_public_key (libsodium sealed box, base64). The server stores this opaque
    # blob and can never read it; only the host decrypts it in-browser. NULL when the event type
    # asks nothing and no notes were left.
    invitee_private: Mapped[str | None] = mapped_column(Text)
    # Identifiers of the event mirrored onto the host's external (CalDAV) calendar, if any.
    external_event_uid: Mapped[str | None] = mapped_column(String(512))
    external_event_url: Mapped[str | None] = mapped_column(String(2048))


class CaldavConnection(TimestampMixin, Base):
    """A host's link to an external CalDAV calendar (one per member for now)."""

    __tablename__ = "caldav_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint("status IN ('active', 'needs_reauth')", name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    server_url: Mapped[str] = mapped_column(String(2048))
    username: Mapped[str] = mapped_column(String(320))
    password_encrypted: Mapped[str] = mapped_column(Text)
    calendar_url: Mapped[str] = mapped_column(String(2048))
    calendar_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalBusy(Base):
    """Busy intervals pulled from a host's external calendar (cache for the engine)."""

    __tablename__ = "external_busy"
    __table_args__ = (
        Index("ix_external_busy_org_period", "organization_id", "period", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caldav_connections.id", ondelete="CASCADE")
    )
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period: Mapped[object] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(start_at, end_at, '[)')", persisted=True),
    )


# Tenant-scoped tables that receive Row-Level Security (column carrying the tenant id).
class BookingReminder(TimestampMixin, Base):
    """One row per reminder sent for a booking (idempotency for the periodic reminder task)."""

    __tablename__ = "booking_reminders"
    __table_args__ = (UniqueConstraint("booking_id", "minutes_before"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    minutes_before: Mapped[int] = mapped_column()
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Poll(TimestampMixin, Base):
    """A meeting poll: the host proposes several times; invitees vote; the host finalizes one."""

    __tablename__ = "polls"
    __table_args__ = (
        UniqueConstraint("slug"),
        CheckConstraint(f"status IN {POLL_STATUSES}", name="poll_status_allowed"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    location_type: Mapped[str] = mapped_column(String(20), default="google_meet")
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    finalized_option_id: Mapped[uuid.UUID | None] = mapped_column()


class PollOption(TimestampMixin, Base):
    __tablename__ = "poll_options"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    poll_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PollVote(TimestampMixin, Base):
    __tablename__ = "poll_votes"
    __table_args__ = (UniqueConstraint("option_id", "voter_email"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    poll_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"))
    option_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("poll_options.id", ondelete="CASCADE"))
    voter_name: Mapped[str] = mapped_column(String(200))
    voter_email: Mapped[str] = mapped_column(String(320))


class WebhookEndpoint(TimestampMixin, Base):
    """An outbound webhook: GhostCal POSTs signed event payloads to ``url``."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(String(2048))
    secret: Mapped[str] = mapped_column(String(80))
    event_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


RLS_TABLES: dict[str, str] = {
    "organizations": "id",
    "memberships": "organization_id",
    "organization_invitations": "organization_id",
    "event_types": "organization_id",
    "event_type_hosts": "organization_id",
    "availability_schedules": "organization_id",
    "availability_rules": "organization_id",
    "availability_overrides": "organization_id",
    "bookings": "organization_id",
    "booking_reminders": "organization_id",
    "polls": "organization_id",
    "poll_options": "organization_id",
    "poll_votes": "organization_id",
    "webhook_endpoints": "organization_id",
    "caldav_connections": "organization_id",
    "external_busy": "organization_id",
}

# server-side timestamp default helper kept importable for migrations/tests
NOW = func.now()
