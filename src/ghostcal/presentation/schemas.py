"""Request/response models for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=1)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    email_verified: bool


class RegisteredOut(BaseModel):
    user_id: uuid.UUID


class RuleSchema(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = Monday
    start: time
    end: time


class OverrideSchema(BaseModel):
    day: date
    is_available: bool = True
    start: time | None = None
    end: time | None = None


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(min_length=1, max_length=64)
    rules: list[RuleSchema] = Field(default_factory=list)
    overrides: list[OverrideSchema] = Field(default_factory=list)


class ScheduleOut(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str
    rules: list[RuleSchema]
    overrides: list[OverrideSchema]


class CreatedOut(BaseModel):
    id: uuid.UUID


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=3, max_length=100)


class CalendarCredentialsIn(BaseModel):
    server_url: str = Field(min_length=1, max_length=2048)
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class CalendarInfoOut(BaseModel):
    name: str
    url: str


class CalendarConnectIn(CalendarCredentialsIn):
    calendar_url: str = Field(min_length=1, max_length=2048)
    calendar_name: str | None = Field(default=None, max_length=255)


class CalendarStatusOut(BaseModel):
    connected: bool
    server_url: str | None = None
    username: str | None = None
    calendar_name: str | None = None
    status: str | None = None
    last_synced_at: datetime | None = None


class SyncResultOut(BaseModel):
    synced: int


class MeetingOut(BaseModel):
    id: uuid.UUID
    event_title: str
    invitee_name: str
    invitee_email: str
    invitee_timezone: str
    start_at: datetime
    end_at: datetime
    status: str
    location: str | None
    meeting_url: str | None


class EventTypeIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    duration_min: int = Field(gt=0, le=1440)
    slot_interval_min: int = Field(default=15, gt=0, le=1440)
    buffer_before_min: int = Field(default=0, ge=0, le=1440)
    buffer_after_min: int = Field(default=0, ge=0, le=1440)
    min_notice_min: int = Field(default=0, ge=0)
    date_window_days: int = Field(default=60, gt=0, le=365)
    max_per_day: int | None = Field(default=None, gt=0)
    location_type: str = "google_meet"
    active: bool = True


class EventTypeDetailOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_slug: str
    slug: str
    title: str
    description: str | None
    duration_min: int
    slot_interval_min: int
    buffer_before_min: int
    buffer_after_min: int
    min_notice_min: int
    date_window_days: int
    max_per_day: int | None
    location_type: str
    active: bool


class EventTypeOut(BaseModel):
    id: uuid.UUID
    title: str
    duration_min: int
    location_type: str
    host_name: str


class PublicEventTypeOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    duration_min: int
    location_type: str


class BookingPageOut(BaseModel):
    organization_name: str
    event_types: list[PublicEventTypeOut]


class SlotOut(BaseModel):
    start: datetime
    end: datetime


class AvailabilityOut(BaseModel):
    event_type_id: uuid.UUID
    slots: list[SlotOut]


class BookingIn(BaseModel):
    start_at: datetime
    invitee_name: str = Field(min_length=1, max_length=200)
    invitee_email: str = Field(min_length=3, max_length=320)
    invitee_timezone: str = Field(min_length=1, max_length=64)


class BookingOut(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: str = "confirmed"


class ManageBookingOut(BaseModel):
    event_title: str
    host_name: str
    organization_slug: str
    event_slug: str
    invitee_name: str
    invitee_timezone: str
    duration_min: int
    location_type: str
    start_at: datetime
    end_at: datetime
    status: str


class RescheduleIn(BaseModel):
    start_at: datetime
