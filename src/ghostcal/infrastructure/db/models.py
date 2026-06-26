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
from sqlalchemy.dialects.postgresql import TSTZRANGE, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ghostcal.infrastructure.db.base import Base, TimestampMixin

# Allowed string-enum values.
MEMBERSHIP_ROLES = ("owner", "admin", "member")
IDENTITY_PROVIDERS = ("google", "microsoft", "oidc")
LOCATION_TYPES = ("google_meet", "ms_teams", "zoom", "in_person", "phone", "custom")
BOOKING_STATUSES = ("confirmed", "cancelled", "rescheduled")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)


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
    price_cents: Mapped[int | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(default=True)


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
        # No two confirmed bookings for the same host may overlap. The real guarantee.
        ExcludeConstraint(
            ("host_id", "="),
            ("period", "&&"),
            using="gist",
            where=text("status = 'confirmed'"),
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
    invitee_name: Mapped[str] = mapped_column(String(200))
    invitee_email: Mapped[str] = mapped_column(String(320))
    invitee_timezone: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period: Mapped[object] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(start_at, end_at, '[)')", persisted=True),
    )
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    location: Mapped[str | None] = mapped_column(String(500))
    meeting_url: Mapped[str | None] = mapped_column(String(2048))


# Tenant-scoped tables that receive Row-Level Security (column carrying the tenant id).
RLS_TABLES: dict[str, str] = {
    "organizations": "id",
    "memberships": "organization_id",
    "event_types": "organization_id",
    "availability_schedules": "organization_id",
    "availability_rules": "organization_id",
    "availability_overrides": "organization_id",
    "bookings": "organization_id",
}

# server-side timestamp default helper kept importable for migrations/tests
NOW = func.now()
