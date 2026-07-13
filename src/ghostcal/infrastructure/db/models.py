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
# The single global user that carries records anonymized by account deletion (ADR-0006). It has no
# credentials, no identities and no memberships, so it can neither authenticate nor appear in a
# member list. Seeded by migration a1c7e94b52f0.
TOMBSTONE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
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
    # Which generation of the org keypair ``zk_public_key`` is (ADR-0007). Bumped by a rotation;
    # members keep their copy of every past generation so records not yet re-sealed still open.
    zk_key_generation: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # Opt-in retention: purge bookings that ended more than this many days ago. NULL = keep forever
    # (the default). Floored at MIN_RETENTION_DAYS by a check constraint — the purge is
    # irreversible, so a fat-fingered value must not be able to erase an organization's history.
    booking_retention_days: Mapped[int | None] = mapped_column(SmallInteger)


class OrgMemberKey(TimestampMixin, Base):
    """A member's copy of one generation of their organization's zero-knowledge private key.

    One row per (org, member, generation): a member keeps every org key the organization has ever
    had, so records sealed under an older generation and not yet re-sealed still open. A departed
    member already kept the old key, so retaining it for the remaining members costs nothing.

    Two ways in, exactly one per row (enforced by ck_org_member_keys_one_way_in):

    - **generation 0** — the key wrapped under an Argon2id key derived from the member's password
      (and a second time under their recovery phrase, for the founder). The original scheme.
    - **generation >= 1** — the key **sealed to the member's own public key** (ADR-0007). This is
      what lets an admin hand a member a rotated key without their password, and therefore what
      makes rotation possible at all.

    The server stores only opaque blobs; it can never decrypt any of it.
    """

    __tablename__ = "org_member_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, default=0, server_default="0"
    )
    # Sealed to the member's users.zk_public_key. Set from generation 1 on; NULL for generation 0.
    sealed_org_key: Mapped[str | None] = mapped_column(Text)
    wrapped_private_key: Mapped[str | None] = mapped_column(Text)
    wrap_salt: Mapped[str | None] = mapped_column(Text)
    # Recovery copy — present for the founder, NULL for members who received the key via an
    # invitation grant (their access is re-grantable rather than recoverable). See ADR-0003.
    recovery_wrapped_private_key: Mapped[str | None] = mapped_column(Text)
    recovery_salt: Mapped[str | None] = mapped_column(Text)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The user's own X25519 keypair (ADR-0007). The public key is readable by the server — an org
    # key can be sealed *to* it, which is what makes rotation invisible to the member. The private
    # key is wrapped under an Argon2id key derived from their password and never reaches the server
    # unwrapped. NULL until the user's next login: that is the only moment their password is in the
    # browser.
    zk_public_key: Mapped[str | None] = mapped_column(Text)
    zk_wrapped_private_key: Mapped[str | None] = mapped_column(Text)
    zk_wrap_salt: Mapped[str | None] = mapped_column(Text)


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
    # The org private key sealed under a random grant key carried in the invite link fragment
    # (zero-knowledge team key sharing). NULL when the inviter had no key unlocked. See ADR-0003.
    wrapped_org_key: Mapped[str | None] = mapped_column(Text)


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
    # Which generation of the org key sealed the blob above (ADR-0007). Stamped by a BEFORE
    # INSERT trigger, so every write path gets it. A row behind its org's current generation
    # is backlog waiting to be re-sealed.
    zk_generation: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
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
    # External event title, encrypted at rest (read from the user's own calendar during sync).
    summary: Mapped[str | None] = mapped_column(EncryptedString)
    period: Mapped[object] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(start_at, end_at, '[)')", persisted=True),
    )


class Calendar(TimestampMixin, Base):
    """A user's calendar collection (zero-knowledge personal calendar — see ADR-0004)."""

    __tablename__ = "calendars"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(20), default="#00f0ff")
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


class CalendarEvent(TimestampMixin, Base):
    """A user's own calendar event. Scheduling fields are cleartext; ``content`` is a sealed blob
    ({title, description, location}) the server can never read."""

    __tablename__ = "calendar_events"
    __table_args__ = (Index("ix_calendar_events_org_start", "organization_id", "start_at"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    calendar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendars.id", ondelete="CASCADE"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    # RFC 5545 recurrence rule (e.g. "FREQ=WEEKLY;BYDAY=MO,WE") and excluded occurrence datetimes.
    rrule: Mapped[str | None] = mapped_column(Text)
    exdates: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    # Sealed {title, description, location} — encrypted to the org key, decrypted only in-browser.
    content: Mapped[str | None] = mapped_column(Text)
    # Which generation of the org key sealed the blob above (ADR-0007). Stamped by a BEFORE
    # INSERT trigger, so every write path gets it. A row behind its org's current generation
    # is backlog waiting to be re-sealed.
    zk_generation: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # Minutes before each occurrence to email the owner a content-less reminder; NULL = none.
    reminder_minutes: Mapped[int | None] = mapped_column()


class CalendarShare(TimestampMixin, Base):
    """A calendar shared (read-only) with another org member. See ADR-0005."""

    __tablename__ = "calendar_shares"
    __table_args__ = (
        UniqueConstraint("calendar_id", "shared_with_user_id"),
        Index("ix_calendar_shares_shared_with", "shared_with_user_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    calendar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendars.id", ondelete="CASCADE"))
    shared_with_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    can_edit: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


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


class CalendarSubscription(TimestampMixin, Base):
    """A subscribed public iCalendar (ICS) feed — holidays, a team's fixtures, etc. The server
    fetches the URL periodically (SSRF-guarded) and caches its events in ``subscription_events``.
    Read-only; shown as a coloured overlay in the calendar."""

    __tablename__ = "calendar_subscriptions"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2048))
    color: Mapped[str] = mapped_column(String(20), default="#00d68f")
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubscriptionEvent(Base):
    """A cached event from a subscribed ICS feed. Public data, but the summary is encrypted at rest
    (a dump shouldn't reveal what you follow)."""

    __tablename__ = "subscription_events"
    __table_args__ = (
        UniqueConstraint("subscription_id", "uid"),
        Index("ix_subscription_events_org_start", "organization_id", "start_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendar_subscriptions.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    uid: Mapped[str] = mapped_column(String(512))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    summary: Mapped[str | None] = mapped_column(EncryptedString)


ATTENDEE_STATUSES = ("needs_action", "accepted", "declined", "tentative")


class EventAttendee(TimestampMixin, Base):
    """A guest invited to a personal calendar event. Email + RSVP status are cleartext (the server
    needs them to send invitations and track responses); the event title/notes stay sealed. Inviting
    a guest is an explicit choice to share those details — the organiser's browser supplies the
    cleartext to build the ICS at send time, and the server never persists it."""

    __tablename__ = "event_attendees"
    __table_args__ = (
        UniqueConstraint("event_id", "email"),
        CheckConstraint(f"status IN {ATTENDEE_STATUSES}", name="attendee_status_allowed"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), default="needs_action", server_default="needs_action"
    )
    # SHA-256 of the random RSVP token carried in the invitation link (only the hash is stored).
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)


class Task(TimestampMixin, Base):
    """A zero-knowledge to-do item (Fantastical-style). ``content`` ({title, notes}) is sealed to
    the org key and never read by the server; the due date and completion state are cleartext so
    due lists and (later) reminders work."""

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_owner_due", "owner_id", "due_at"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Sealed {title, notes} — encrypted to the org key, decrypted only in-browser.
    content: Mapped[str | None] = mapped_column(Text)
    # Which generation of the org key sealed the blob above (ADR-0007). Stamped by a BEFORE
    # INSERT trigger, so every write path gets it. A row behind its org's current generation
    # is backlog waiting to be re-sealed.
    zk_generation: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Minutes before due_at to email the owner a content-less reminder; NULL = none.
    reminder_minutes: Mapped[int | None] = mapped_column()
    # Set when the reminder was sent (idempotency — a task reminds at most once).
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
