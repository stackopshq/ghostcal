"""Request/response models for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
