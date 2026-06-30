"""Unit tests for booking-input validation (sealed answers presence + guests).

Answers are zero-knowledge: the server can no longer inspect their content, so per-field "required"
checks moved to the booking page. The server only enforces that *a* sealed blob is present when the
event type has any required question. See ADR-0002.
"""

from __future__ import annotations

import pytest

from ghostcal.application.event_types import BookingQuestion
from ghostcal.application.scheduling import (
    MAX_GUESTS,
    InvalidBookingInput,
    _clean_guests,
    _require_private,
)

QUESTIONS = (
    BookingQuestion(id="company", label="Company", type="text", required=True),
    BookingQuestion(id="notes", label="Notes", type="textarea", required=False),
)


def test_required_question_without_sealed_blob_is_rejected() -> None:
    with pytest.raises(InvalidBookingInput):
        _require_private(QUESTIONS, None)


def test_required_question_with_sealed_blob_is_accepted() -> None:
    blob = "c2VhbGVkLWNpcGhlcnRleHQ="
    assert _require_private(QUESTIONS, blob) == blob


def test_no_required_questions_accepts_missing_blob() -> None:
    optional = (BookingQuestion(id="notes", label="Notes", type="textarea", required=False),)
    assert _require_private(optional, None) is None
    assert _require_private((), None) is None


def test_guests_are_normalized_and_deduped() -> None:
    assert _clean_guests((" A@X.com ", "a@x.com", "b@x.com")) == ("a@x.com", "b@x.com")


def test_too_many_guests_is_rejected() -> None:
    with pytest.raises(InvalidBookingInput):
        _clean_guests(tuple(f"g{i}@x.com" for i in range(MAX_GUESTS + 1)))
