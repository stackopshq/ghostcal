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


class EventTypeOut(BaseModel):
    id: uuid.UUID
    title: str
    duration_min: int
    location_type: str
    host_name: str


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
