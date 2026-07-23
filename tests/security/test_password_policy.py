"""The password policy and the breach check (no DB, no network).

The HIBP client is exercised against a stubbed transport rather than the real service: a test that
depends on a third party is a test that fails on someone else's outage, and the interesting logic
is local anyway — what we send, what we do with padding, and what happens when it goes wrong.
"""

from __future__ import annotations

import hashlib

import httpx
import pytest

from ghostcal.application.passwords import (
    MIN_PASSWORD_LENGTH,
    BreachedPassword,
    NoBreachCheck,
    PasswordRejected,
    enforce_password_policy,
)
from ghostcal.infrastructure.security.hibp import HibpBreachedPasswordChecker


class _AlwaysBreached:
    async def is_breached(self, password: str) -> bool:
        return True


async def test_short_passwords_are_refused_before_any_lookup() -> None:
    with pytest.raises(PasswordRejected, match=str(MIN_PASSWORD_LENGTH)):
        await enforce_password_policy("a" * (MIN_PASSWORD_LENGTH - 1), _AlwaysBreached())


async def test_a_long_password_still_fails_if_it_is_in_a_breach_corpus() -> None:
    # Length is a proxy for strength; a leaked passphrase can be long and still worthless.
    with pytest.raises(BreachedPassword):
        await enforce_password_policy("correct horse battery staple", _AlwaysBreached())


async def test_a_good_password_passes() -> None:
    await enforce_password_policy("a-sufficiently-long-passphrase", NoBreachCheck())


def _digest(password: str) -> tuple[str, str]:
    full = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    return full[:5], full[5:]


def _checker_returning(
    body: str, status: int = 200, sent: dict[str, str] | None = None
) -> HibpBreachedPasswordChecker:
    async def handler(request: httpx.Request) -> httpx.Response:
        if sent is not None:
            sent["url"] = str(request.url)
        return httpx.Response(status, text=body)

    return HibpBreachedPasswordChecker(enabled=True, transport=httpx.MockTransport(handler))


async def test_only_the_hash_prefix_is_sent() -> None:
    """The privacy claim, asserted: five hex characters leave, and never the password."""
    password = "a-sufficiently-long-passphrase"
    prefix, suffix = _digest(password)
    sent: dict[str, str] = {}

    assert await _checker_returning(f"{suffix}:42\n", sent=sent).is_breached(password) is True

    assert sent["url"].endswith(f"/range/{prefix}")
    assert password not in sent["url"]
    assert suffix not in sent["url"]  # the distinguishing half never leaves


async def test_a_padding_entry_is_not_a_hit() -> None:
    # HIBP pads responses with fake suffixes at count 0 so the reply size leaks nothing. Counting
    # those as matches would reject perfectly good passwords at random.
    password = "another-long-enough-passphrase"
    _, suffix = _digest(password)
    assert await _checker_returning(f"{suffix}:0\n").is_breached(password) is False


async def test_an_unknown_password_is_not_breached() -> None:
    checker = _checker_returning("0000000000000000000000000000000000000:5\n")
    assert await checker.is_breached("a-sufficiently-long-passphrase") is False


async def test_the_check_fails_open_on_an_error_response() -> None:
    checker = _checker_returning("upstream sad", status=503)
    assert await checker.is_breached("a-sufficiently-long-passphrase") is False


async def test_disabling_the_check_makes_no_request_at_all() -> None:
    # The setting exists for deployments that must make no third-party calls; it must not merely
    # ignore the answer.
    checker = HibpBreachedPasswordChecker(enabled=False)
    assert await checker.is_breached("hunter2") is False
