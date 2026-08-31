"""Per-user keypair use cases (ADR-0007).

Each user holds an X25519 keypair. The **public** key is stored in the clear and readable by the
server and by their org's admins — an org key is sealed *to* it, which is what lets a key rotation
happen without the member lifting a finger. The **private** key arrives already wrapped under a key
derived from their password; the server stores the blob and can derive nothing from it.

The server never validates the crypto — it cannot. It stores opaque base64 and enforces exactly two
rules, which are the two ways a keypair store goes wrong:

- a keypair is **write-once**. Overwriting a public key would strand everything ever sealed to it.
  Re-wrapping is NOT that operation: the same keypair in a new envelope leaves `zk_public_key`
  identical, so nothing sealed to it is stranded. It has its own path, which never writes the
  public key and matches it instead — a caller must say which keypair it holds, and be right.
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


class KeypairNotRewrappable(KeypairError):
    """No keypair to re-wrap, or the caller's public key is not the one on file."""


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

    async def rewrap(
        self, user_id: uuid.UUID, *, public_key: str, wrapped_private_key: str, wrap_salt: str
    ) -> bool:
        """Replace the envelope of an existing keypair.

        False when `public_key` is not the one on file: the caller is re-wrapping something else.
        """
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

    async def rewrap(
        self, user_id: uuid.UUID, *, public_key: str, wrapped_private_key: str, wrap_salt: str
    ) -> None:
        """Store the same keypair under a new password.

        Called after a password change. Without it the stored envelope stays sealed under the OLD
        password and, because the keypair is write-once, it can never be opened again: the account
        keeps working, and every org key sealed to this keypair becomes unreadable — permanently,
        not until the next login.
        """
        if not await self._repo.rewrap(
            user_id,
            public_key=public_key,
            wrapped_private_key=wrapped_private_key,
            wrap_salt=wrap_salt,
        ):
            raise KeypairNotRewrappable("no keypair with that public key for this account")

    async def member_public_keys(self, organization_id: uuid.UUID) -> list[MemberPublicKey]:
        return await self._repo.member_public_keys(organization_id)
