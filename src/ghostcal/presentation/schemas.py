"""Request/response models for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator

_TIMEZONES = available_timezones()
# RRULE frequencies finer than daily can expand to enormous occurrence counts — reject them.
_BLOCKED_FREQS = ("SECONDLY", "MINUTELY", "HOURLY")


def _validate_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("unknown IANA timezone")
    return value


def _validate_rrule(value: str | None) -> str | None:
    if value is None:
        return None
    upper = value.upper()
    if any(f"FREQ={f}" in upper for f in _BLOCKED_FREQS):
        raise ValueError("sub-daily recurrence frequencies are not allowed")
    return value


def _validate_iso_datetimes(values: list[str]) -> list[str]:
    for v in values:
        try:
            datetime.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"invalid ISO datetime in exdates: {v}") from exc
    return values


def _validate_http_url(value: str | None) -> str | None:
    if value is None:
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("url must be an http(s) URL")
    return value


class ZkKeyMaterialIn(BaseModel):
    """Zero-knowledge key material generated in the browser at sign-up (all base64). See ADR-0002.

    The server stores these verbatim and can derive nothing from them — no private key, no
    password- or recovery-derived key ever reaches it.
    """

    public_key: str = Field(min_length=1, max_length=512)
    wrapped_private_key: str = Field(min_length=1, max_length=2048)
    wrap_salt: str = Field(min_length=1, max_length=512)
    recovery_wrapped_private_key: str = Field(min_length=1, max_length=2048)
    recovery_salt: str = Field(min_length=1, max_length=512)


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    zk_keys: ZkKeyMaterialIn


class ZkKeysOut(BaseModel):
    organization_id: uuid.UUID
    public_key: str
    wrapped_private_key: str
    wrap_salt: str
    recovery_wrapped_private_key: str | None = None
    recovery_salt: str | None = None


class ZkRewrapIn(BaseModel):
    organization_id: uuid.UUID
    wrapped_private_key: str = Field(min_length=1, max_length=2048)
    wrap_salt: str = Field(min_length=1, max_length=512)


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
    avatar_url: str | None = None


class ProfileUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=1, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=2048)

    _v_tz = field_validator("timezone")(_validate_timezone)
    _v_avatar = field_validator("avatar_url")(_validate_http_url)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


RoleName = Literal["owner", "admin", "member"]


class OrgMembershipOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


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
    # The plaintext token, returned only when an invitation is created, so the inviter's browser can
    # build the secure accept link with the decryption-key fragment. Never set on listings.
    token: str | None = None


class InviteIn(BaseModel):
    email: EmailStr
    role: RoleName = "member"
    # The org private key sealed under the link-fragment grant key (zero-knowledge team sharing).
    wrapped_org_key: str | None = Field(default=None, max_length=4096)


class RoleUpdateIn(BaseModel):
    role: RoleName


class InvitationPreviewOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    email: str
    role: str
    wrapped_org_key: str | None = None


class StoreMemberKeyIn(BaseModel):
    organization_id: uuid.UUID
    wrapped_private_key: str = Field(min_length=1, max_length=2048)
    wrap_salt: str = Field(min_length=1, max_length=512)


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
    # Null for booking-page bookings — the dashboard decrypts the name from ``invitee_private``.
    invitee_name: str | None
    invitee_email: str
    invitee_timezone: str
    start_at: datetime
    end_at: datetime
    status: str
    location: str | None
    meeting_url: str | None
    # Sealed-box blob with the invitee's answers + notes; the host decrypts it in-browser. Null
    # when nothing private was submitted. The server never reads it.
    invitee_private: str | None = None


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
    redirect_url: str | None = Field(default=None, max_length=2048)

    _v_redirect = field_validator("redirect_url")(_validate_http_url)


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
    redirect_url: str | None = None


class EventTypeOut(BaseModel):
    id: uuid.UUID
    title: str
    duration_min: int
    location_type: str
    host_name: str
    questions: list[BookingQuestionSchema] = Field(default_factory=list)
    redirect_url: str | None = None
    # The organization's zero-knowledge public key; the booking page seals answers to it. Null
    # only for legacy orgs created before zero-knowledge.
    zk_public_key: str | None = None


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
    # No invitee_name: it is zero-knowledge — the booking page seals it into ``invitee_private``
    # and the server never receives it in cleartext.
    invitee_email: EmailStr
    invitee_timezone: str = Field(min_length=1, max_length=64)
    guest_emails: list[EmailStr] = Field(default_factory=list, max_length=10)
    # Sealed-box blob (base64) holding the answers + notes, encrypted in-browser to the org public
    # key. The server stores it as-is and never reads it. Null when nothing private was submitted.
    invitee_private: str | None = Field(default=None, max_length=8192)

    _v_tz = field_validator("invitee_timezone")(_validate_timezone)


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
    invitee_name: str | None
    invitee_timezone: str
    duration_min: int
    location_type: str
    start_at: datetime
    end_at: datetime
    status: str


class RescheduleIn(BaseModel):
    start_at: datetime


# --- Calendar (zero-knowledge personal calendar, ADR-0004) ----------------------------------------


class CalendarOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    is_default: bool
    is_shared: bool = False
    owner_name: str | None = None


class CalendarIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    color: str = Field(default="#00f0ff", max_length=20)


class EventIn(BaseModel):
    calendar_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    all_day: bool = False
    rrule: str | None = Field(default=None, max_length=1024)
    exdates: list[str] = Field(default_factory=list, max_length=512)
    # Sealed {title, description, location} — encrypted in the browser; the server never reads it.
    content: str | None = Field(default=None, max_length=16384)
    reminder_minutes: int | None = Field(default=None, ge=0, le=40320)

    _v_tz = field_validator("timezone")(_validate_timezone)
    _v_rrule = field_validator("rrule")(_validate_rrule)
    _v_exdates = field_validator("exdates")(_validate_iso_datetimes)


class EventOut(BaseModel):
    id: uuid.UUID
    calendar_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    timezone: str
    all_day: bool
    rrule: str | None
    exdates: list[str]
    content: str | None
    reminder_minutes: int | None


class AgendaItemOut(BaseModel):
    source: str
    start: datetime
    end: datetime
    all_day: bool = False
    calendar_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    content: str | None = None
    title: str | None = None
    read_only: bool = False


class ShareIn(BaseModel):
    user_id: uuid.UUID


class ShareOut(BaseModel):
    user_id: uuid.UUID
    name: str
