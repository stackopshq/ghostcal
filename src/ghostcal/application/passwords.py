"""The password policy, in one place.

Registration and password change previously enforced only a Pydantic ``min_length``, separately.
Anything stricter belongs where both paths can share it, or the two drift and the weaker one
becomes the real policy.
"""

from __future__ import annotations

from ghostcal.application.ports.security import BreachedPasswordChecker

# 12, not 8. Eight characters is below current OWASP guidance and well inside the reach of an
# offline attack on a stolen hash — and for this product a password is not only the account, it is
# what wraps the private key that decrypts the calendar.
MIN_PASSWORD_LENGTH = 12


class NoBreachCheck:
    """Null object: the policy still applies, the corpus lookup does not.

    Lives here rather than in infrastructure so the application layer has a usable default without
    importing an adapter — the real HIBP client is injected from the edge.
    """

    async def is_breached(self, password: str) -> bool:
        return False


class PasswordRejected(Exception):
    """The password is unacceptable. The message is safe to show the user."""


class BreachedPassword(PasswordRejected):
    """The password appears in a public breach corpus."""


async def enforce_password_policy(password: str, checker: BreachedPasswordChecker) -> None:
    """Raise ``PasswordRejected`` if the password may not be used."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordRejected(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if await checker.is_breached(password):
        # Length is a proxy for strength; appearing in a breach corpus is direct evidence of
        # weakness, and no length requirement catches "Password123!" or a leaked passphrase.
        raise BreachedPassword(
            "this password has appeared in a public data breach — please choose another"
        )
