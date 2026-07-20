"""Breach check against Have I Been Pwned, using its k-anonymity range API.

What leaves this server is the **first five hex characters** of the SHA-1 of the password, and
nothing else. HIBP answers with every suffix under that prefix — several hundred to a few thousand
hashes — and the comparison happens here. So the service learns a prefix shared by an enormous
number of passwords, and cannot tell which one was asked about, nor whose it was. No account
identifier is sent, and the request carries no cookies.

That is a real privacy cost, not a zero one: the operator is telling a third party that *somebody*
set a password under some prefix, at some time. It is small enough to be worth the protection, and
it is switchable, which is why this is a setting rather than a hard-coded call.

SHA-1 is not a security choice here — it is the protocol HIBP speaks. The hash is never stored;
passwords are stored as Argon2id (see ``passwords.py``).
"""

from __future__ import annotations

import hashlib
import logging

import httpx

logger = logging.getLogger("ghostcal.hibp")

_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
_TIMEOUT = 3.0


class HibpBreachedPasswordChecker:
    """Checks a password against HIBP. Fails open on any error."""

    def __init__(
        self, *, enabled: bool = True, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._enabled = enabled
        # Injectable so tests can drive this without reaching the real service — a test that
        # depends on a third party fails on someone else's outage.
        self._transport = transport

    async def is_breached(self, password: str) -> bool:
        if not self._enabled:
            return False

        digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, transport=self._transport) as client:
                response = await client.get(
                    _RANGE_URL.format(prefix=prefix),
                    # Ask for padded responses: HIBP then returns a variable number of fake
                    # entries, so the size of the reply leaks nothing about how many real hashes
                    # share the prefix.
                    headers={"Add-Padding": "true", "User-Agent": "GhostCal"},
                )
            if response.status_code != 200:
                logger.warning("hibp range lookup returned %s (allowing)", response.status_code)
                return False
        except httpx.HTTPError:
            # Fail open, deliberately. Refusing registrations because a third party is unreachable
            # trades a real outage for an advisory.
            logger.warning("hibp range lookup failed (allowing)")
            return False

        for line in response.text.splitlines():
            candidate, _, count = line.partition(":")
            # Padding entries are returned with a count of 0 and must not be treated as hits.
            if candidate.strip().upper() == suffix and count.strip() not in ("", "0"):
                return True
        return False
