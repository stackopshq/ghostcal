"""Request/response models for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

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


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    timezone: str
    email_verified: bool


class ProfileUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=1, max_length=64)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


RoleName = Literal["owner", "admin", "member"]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    joined_at: datetime


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    expires_at: datetime


class InviteIn(BaseModel):
    email: EmailStr
    role: RoleName = "member"


class RoleUpdateIn(BaseModel):
    role: RoleName


class InvitationPreviewOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    email: str
    role: str


class AcceptInvitationOut(BaseModel):
    organization_id: uuid.UUID


class PollCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    duration_min: int = Field(gt=0, le=1440)
    location_type: str = "google_meet"
    option_starts: list[datetime] = Field(min_length=2, max_length=25)


class PollOptionOut(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    votes: int


class VoterOut(BaseModel):
    name: str
    email: str
    option_ids: list[uuid.UUID]


class PollOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    duration_min: int
    location_type: str
    status: str
    owner_name: str
    finalized_option_id: uuid.UUID | None
    options: list[PollOptionOut]
    voters: list[VoterOut] = Field(default_factory=list)


class PublicPollOut(BaseModel):
    slug: str
    title: str
    duration_min: int
    location_type: str
    status: str
    owner_name: str
    finalized_option_id: uuid.UUID | None
    options: list[PollOptionOut]


class PollSummaryOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    status: str
    option_count: int
    vote_count: int


class VoteIn(BaseModel):
    voter_name: str = Field(min_length=1, max_length=200)
    voter_email: EmailStr
    option_ids: list[uuid.UUID] = Field(min_length=1, max_length=25)


class FinalizeIn(BaseModel):
    option_id: uuid.UUID


class WebhookCreateIn(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    event_types: list[str] = Field(min_length=1, max_length=20)


class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    active: bool
    created_at: datetime


class WebhookCreatedOut(BaseModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    secret: str


class EventTypeCountOut(BaseModel):
    title: str
    count: int


class DayCountOut(BaseModel):
    day: str
    count: int


class AnalyticsOut(BaseModel):
    total_bookings: int
    upcoming_bookings: int
    bookings_last_30_days: int
    cancellations_last_30_days: int
    by_event_type: list[EventTypeCountOut]
    daily: list[DayCountOut]


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


class BookingQuestionSchema(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    type: Literal["text", "textarea", "phone", "select", "checkbox"] = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=50)


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
    questions: list[BookingQuestionSchema] = Field(default_factory=list, max_length=30)
    kind: Literal["solo", "round_robin", "collective", "group"] = "solo"
    host_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    capacity: int = Field(default=1, ge=1, le=1000)


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
    questions: list[BookingQuestionSchema] = Field(default_factory=list)
    kind: str = "solo"
    host_ids: list[uuid.UUID] = Field(default_factory=list)
    capacity: int = 1


class EventTypeOut(BaseModel):
    id: uuid.UUID
    title: str
    duration_min: int
    location_type: str
    host_name: str
    questions: list[BookingQuestionSchema] = Field(default_factory=list)


class PublicEventTypeOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    duration_min: int
    location_type: str
    questions: list[BookingQuestionSchema] = Field(default_factory=list)


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
    guest_emails: list[EmailStr] = Field(default_factory=list, max_length=10)
    answers: dict[str, str] = Field(default_factory=dict)


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
