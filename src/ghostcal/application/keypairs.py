"""Per-user keypair use cases (ADR-0007).

Each user holds an X25519 keypair. The **public** key is stored in the clear and readable by the
server and by their org's admins — an org key is sealed *to* it, which is what lets a key rotation
happen without the member lifting a finger. The **private** key arrives already wrapped under a key
derived from their password; the server stores the blob and can derive nothing from it.

The server never validates the crypto — it cannot. It stores opaque base64 and enforces exactly two
rules, which are the two ways a keypair store goes wrong:

- a keypair is **write-once**. Overwriting a public key would strand everything ever sealed to it.
- a public key is only visible to someone who **shares an organization** with its owner. Public keys
  are not secret, but a directory of every user in the system is not something to hand out either.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


class KeypairError(Exception):
    """Base class for keypair errors."""


class KeypairAlreadySet(KeypairError):
    """The user already has a keypair. Replacing it would strand all that was sealed to it."""


class UnknownUser(KeypairError):
    pass


@dataclass(frozen=True)
class UserKeypair:
    """A user's own keypair, as the browser hands it over. All base64; all opaque to the server."""

    public_key: str
    wrapped_private_key: str
    wrap_salt: str


@dataclass(frozen=True)
class MemberPublicKey:
    """A fellow member's public key — what a rotating admin seals the new org key to."""

    user_id: uuid.UUID
    name: str
    email: str
    public_key: str | None


class KeypairRepository:
    async def get(self, user_id: uuid.UUID) -> UserKeypair | None:
        raise NotImplementedError

    async def set(self, user_id: uuid.UUID, keypair: UserKeypair) -> bool:
        """Store the keypair. Returns False if one was already there (nothing is overwritten)."""
        raise NotImplementedError

    async def member_public_keys(self, organization_id: uuid.UUID) -> list[MemberPublicKey]:
        """Every member of the organization, with their public key (None if they have none yet)."""
        raise NotImplementedError


class KeypairService:
    def __init__(self, repo: KeypairRepository) -> None:
        self._repo = repo

    async def get(self, user_id: uuid.UUID) -> UserKeypair | None:
        return await self._repo.get(user_id)

    async def set(self, user_id: uuid.UUID, keypair: UserKeypair) -> None:
        if not await self._repo.set(user_id, keypair):
            raise KeypairAlreadySet("this account already has a keypair")

    async def member_public_keys(self, organization_id: uuid.UUID) -> list[MemberPublicKey]:
        return await self._repo.member_public_keys(organization_id)
