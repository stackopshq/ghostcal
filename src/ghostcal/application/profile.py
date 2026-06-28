"""User profile use cases: read profile, update name/timezone, change password.

Profile data lives in the global ``users`` / ``user_credentials`` tables (not org-scoped), so this
reuses ``AuthRepository`` on a plain (non-tenant) session.
"""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ghostcal.application.auth import AuthRepository, AuthUserRecord, InvalidCredentials
from ghostcal.application.ports.security import PasswordHasher


class ProfileError(Exception):
    """Base class for profile errors."""


class UnknownUser(ProfileError):
    pass


class InvalidTimezone(ProfileError):
    pass


class ProfileService:
    def __init__(self, repo: AuthRepository, hasher: PasswordHasher) -> None:
        self._repo = repo
        self._hasher = hasher

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
    ) -> None:
        user = await self.get(user_id)
        if user.password_hash is None or not self._hasher.verify(
            user.password_hash, current_password
        ):
            raise InvalidCredentials("current password is incorrect")
        await self._repo.set_password_hash(user_id, self._hasher.hash(new_password))
