"""User profile use cases: read profile, update name/timezone, change password.

Profile data lives in the global ``users`` / ``user_credentials`` tables (not org-scoped), so this
reuses ``AuthRepository`` on a plain (non-tenant) session.
"""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ghostcal.application.auth import AuthRepository, AuthUserRecord, InvalidCredentials
from ghostcal.application.ports.clock import Clock, SystemClock
from ghostcal.application.ports.security import PasswordHasher


class ProfileError(Exception):
    """Base class for profile errors."""


class UnknownUser(ProfileError):
    pass


class InvalidTimezone(ProfileError):
    pass


class ProfileService:
    def __init__(
        self, repo: AuthRepository, hasher: PasswordHasher, clock: Clock | None = None
    ) -> None:
        self._repo = repo
        self._hasher = hasher
        self._clock = clock or SystemClock()

    async def get(self, user_id: uuid.UUID) -> AuthUserRecord:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UnknownUser("unknown user")
        return user

    async def update(
        self, user_id: uuid.UUID, *, name: str, timezone: str, avatar_url: str | None = None
    ) -> AuthUserRecord:
        name = name.strip()
        if not name:
            raise ProfileError("name is required")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise InvalidTimezone(f"unknown timezone: {timezone}") from exc
        avatar = (avatar_url or "").strip() or None
        if avatar and not avatar.startswith(("http://", "https://")):
            raise ProfileError("avatar URL must be an absolute http(s) URL")
        await self._repo.update_profile(user_id, name=name, timezone=timezone, avatar_url=avatar)
        return await self.get(user_id)

    async def change_password(
        self, user_id: uuid.UUID, *, current_password: str, new_password: str
    ) -> int:
        """Change the password and end every existing session. Returns how many were ended.

        Revoking is the point, not a bonus. People change their password *because* they think
        someone else has it, and a refresh token lives for 30 days — so leaving sessions alone
        would hand the attacker a month of access starting from the moment the user acted to lock
        them out. The user's own other devices are signed out too; that is the correct trade, and
        it is what "change my password" is understood to mean.
        """
        user = await self.get(user_id)
        if user.password_hash is None or not self._hasher.verify(
            user.password_hash, current_password
        ):
            raise InvalidCredentials("current password is incorrect")
        await self._repo.set_password_hash(user_id, self._hasher.hash(new_password))
        return await self._repo.revoke_all_refresh_tokens(user_id, self._clock.now())
