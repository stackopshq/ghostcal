"""Unit tests for booking-input validation (custom answers + guests)."""

from __future__ import annotations

import pytest

from ghostcal.application.event_types import BookingQuestion
from ghostcal.application.scheduling import (
    MAX_GUESTS,
    InvalidBookingInput,
    _clean_answers,
    _clean_guests,
)

QUESTIONS = (
    BookingQuestion(id="company", label="Company", type="text", required=True),
    BookingQuestion(id="notes", label="Notes", type="textarea", required=False),
)


def test_required_answer_missing_is_rejected() -> None:
    with pytest.raises(InvalidBookingInput):
        _clean_answers(QUESTIONS, {"notes": "hi"})


def test_required_answer_blank_is_rejected() -> None:
    with pytest.raises(InvalidBookingInput):
        _clean_answers(QUESTIONS, {"company": "   "})


def test_unknown_answers_are_dropped_and_known_kept() -> None:
    cleaned = _clean_answers(QUESTIONS, {"company": "Acme", "spam": "x", "notes": "later"})
    assert cleaned == {"company": "Acme", "notes": "later"}


def test_no_questions_accepts_empty() -> None:
    assert _clean_answers((), {}) == {}


def test_guests_are_normalized_and_deduped() -> None:
    assert _clean_guests((" A@X.com ", "a@x.com", "b@x.com")) == ("a@x.com", "b@x.com")


def test_too_many_guests_is_rejected() -> None:
    with pytest.raises(InvalidBookingInput):
        _clean_guests(tuple(f"g{i}@x.com" for i in range(MAX_GUESTS + 1)))
