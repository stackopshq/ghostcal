"""Per-user keypair endpoints (ADR-0007).

The browser generates the keypair at login — the only moment the password is there to wrap the
private key with — and publishes it here. The server stores opaque base64: it cannot verify the
crypto, and does not try to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.keypairs import (
    KeypairAlreadySet,
    KeypairService,
    UserKeypair,
)
from ghostcal.infrastructure.db.keypairs_repository import SqlKeypairRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.presentation.auth_routes import CurrentUser
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    MemberPublicKeyOut,
    UserKeypairIn,
    UserKeypairOut,
)

router = APIRouter(prefix="/v1/me", tags=["keypair"])


@router.get("/keypair", response_model=UserKeypairOut | None)
async def get_keypair(user: CurrentUser) -> UserKeypairOut | None:
    """The caller's own keypair, or null if they have none yet — the browser then makes one."""
    async with db_session() as session:
        keypair = await KeypairService(SqlKeypairRepository(session)).get(user.id)
    if keypair is None:
        return None
    return UserKeypairOut(
        public_key=keypair.public_key,
        wrapped_private_key=keypair.wrapped_private_key,
        wrap_salt=keypair.wrap_salt,
    )


@router.put("/keypair", status_code=204)
async def set_keypair(payload: UserKeypairIn, user: CurrentUser) -> None:
    """Publish the keypair generated in the browser. Write-once.

    Refused (409) if one already exists: replacing a public key would strand everything ever sealed
    to it — every org key a member holds, and every record sealed under those.
    """
    async with db_session() as session:
        try:
            await KeypairService(SqlKeypairRepository(session)).set(
                user.id,
                UserKeypair(
                    public_key=payload.public_key,
                    wrapped_private_key=payload.wrapped_private_key,
                    wrap_salt=payload.wrap_salt,
                ),
            )
        except KeypairAlreadySet as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/organization/member-keys", response_model=list[MemberPublicKeyOut])
async def member_public_keys(member: Member = Depends(current_member)) -> list[MemberPublicKeyOut]:
    """Public keys of everyone in the caller's organization — what a rotation seals the new key to.

    Public keys are not secret, but RLS still scopes this to the caller's own organization: a
    directory of every user in the system is not a thing to hand out.
    """
    async with db_session() as session:
        keys = await KeypairService(SqlKeypairRepository(session)).member_public_keys(
            member.organization_id
        )
    return [
        MemberPublicKeyOut(user_id=k.user_id, name=k.name, email=k.email, public_key=k.public_key)
        for k in keys
    ]
