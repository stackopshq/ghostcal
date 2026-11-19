"""Instance administration settings: read at startup, refused when unreadable."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghostcal.application.administration import resolve_registration
from ghostcal.config import Settings

_BASE = {
    "database_url": "postgresql+asyncpg://u:p@localhost:5432/db",
    "redis_url": "redis://localhost:6379/0",
    "secret_key": "s" * 40,
    "token_encryption_key": "t" * 40,
}


def _settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **_BASE, **overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["close", "false", "no", "0", "opened", "fermé"])
def test_an_unknown_registration_value_stops_the_server(value: str) -> None:
    # Guessing a security switch from a typo is worse than not starting.
    with pytest.raises(ValidationError, match="registration"):
        _settings(registration=value)


@pytest.mark.parametrize(
    ("value", "fixed"),
    [("", None), ("open", "open"), ("closed", "closed"), (" CLOSED ", "closed")],
)
def test_registration_values_that_start(value: str, fixed: str | None) -> None:
    assert _settings(registration=value).registration_fixed == fixed


def test_admin_emails_are_normalised() -> None:
    settings = _settings(admin_emails=" Alice@Exemple.ch,bob@exemple.ch  carol@exemple.ch,,")
    assert settings.instance_admin_emails == {
        "alice@exemple.ch",
        "bob@exemple.ch",
        "carol@exemple.ch",
    }
    assert _settings().instance_admin_emails == frozenset()


@pytest.mark.parametrize(
    ("fixed", "stored", "is_open", "is_fixed"),
    [
        (None, None, True, False),  # never chosen: open, as before
        (None, "open", True, False),
        (None, "closed", False, False),
        (None, "garbage", False, False),  # unreadable at request time: closed
        ("closed", "open", False, True),  # the environment always wins
        ("open", "closed", True, True),
    ],
)
def test_resolve_registration(
    fixed: str | None, stored: str | None, is_open: bool, is_fixed: bool
) -> None:
    status = resolve_registration(fixed, stored)  # type: ignore[arg-type]
    assert (status.open, status.fixed) == (is_open, is_fixed)
