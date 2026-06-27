"""Organization profile use cases (name + public handle/slug)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

_HANDLE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationError(Exception):
    pass


class OrganizationNotFound(OrganizationError):
    pass


class InvalidHandle(OrganizationError):
    pass


class HandleTaken(OrganizationError):
    pass


@dataclass(frozen=True, slots=True)
class OrganizationData:
    id: uuid.UUID
    name: str
    slug: str


class OrganizationRepository:
    async def get(self) -> OrganizationData | None:
        raise NotImplementedError

    async def update(self, *, name: str, slug: str) -> None:
        """Update the org name and handle. Raise ``HandleTaken`` if the slug is in use."""
        raise NotImplementedError


def _validate(name: str, slug: str) -> None:
    if not name.strip():
        raise InvalidHandle("name is required")
    if not (3 <= len(slug) <= 100) or not _HANDLE_RE.match(slug):
        raise InvalidHandle(
            "handle must be 3-100 characters: lowercase letters, digits and single hyphens"
        )


async def get_organization(repo: OrganizationRepository) -> OrganizationData:
    org = await repo.get()
    if org is None:
        raise OrganizationNotFound()
    return org


async def update_organization(
    repo: OrganizationRepository, *, name: str, slug: str
) -> OrganizationData:
    _validate(name, slug)
    await repo.update(name=name, slug=slug)
    return await get_organization(repo)
