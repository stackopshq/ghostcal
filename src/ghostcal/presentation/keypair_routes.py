"""Per-user keypair endpoints (ADR-0007).

The browser generates the keypair at login — the only moment the password is there to wrap the
private key with — and publishes it here. The server stores opaque base64: it cannot verify the
crypto, and does not try to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.audit import AuditLog
from ghostcal.application.keypairs import (
    KeypairAlreadySet,
    KeypairNotRewrappable,
    KeypairService,
    UserKeypair,
)
from ghostcal.application.rotation import (
    MembersLeftBehind,
    MembersWithoutKeypair,
    NotAMember,
    NotAuthorized,
    RotationService,
    SealedMemberKey,
)
from ghostcal.infrastructure.db.audit_repository import SqlAuditSink
from ghostcal.infrastructure.db.keypairs_repository import SqlKeypairRepository
from ghostcal.infrastructure.db.rotation_repository import SqlRotationRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.presentation.auth_routes import CurrentUser
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    MemberPublicKeyOut,
    RotateKeyIn,
    RotateKeyOut,
    UserKeypairIn,
    UserKeypairOut,
    UserKeypairRewrapIn,
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


@router.post("/keypair/rewrap", status_code=204)
async def rewrap_keypair(payload: UserKeypairRewrapIn, user: CurrentUser) -> None:
    """The same keypair, re-wrapped under a new password. Called right after a password change.

    Distinct from `PUT /keypair`, which is write-once. That rule exists to stop a public key being
    replaced, because everything sealed to it would be stranded. Re-wrapping strands nothing: the
    keypair does not change, only the envelope around its private half. So this route never writes
    `public_key` — it matches it, and refuses (404) when the caller names a keypair this account
    does not hold.

    Without it the envelope stayed sealed under the OLD password, and write-once meant it could
    never be re-sealed: the account went on working while every org key sealed to this keypair
    became unreadable. Permanently — the browser's own comment said the next login would fix it,
    and there was nothing for the next login to fix.
    """
    async with db_session() as session:
        try:
            await KeypairService(SqlKeypairRepository(session)).rewrap(
                user.id,
                public_key=payload.public_key,
                wrapped_private_key=payload.wrapped_private_key,
                wrap_salt=payload.wrap_salt,
            )
        except KeypairNotRewrappable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@router.post("/organization/rotate-key", response_model=RotateKeyOut)
async def rotate_key(
    payload: RotateKeyIn, member: Member = Depends(current_member)
) -> RotateKeyOut:
    """Rotate the organization's keypair — the act that makes removing a member revoke something.

    The new pair is minted in the admin's browser (the only place the current org key lives) and the
    new private key arrives already sealed to each member's public key. The server cannot check that
    crypto. It checks what it can: that the rotation is **complete** (no member left behind — a
    silent lockout is the failure mode that matters) and **closed** (no key for an outsider), and it
    advances the public key and inserts the new per-member keys in one transaction.

    It does NOT re-seal the existing records. Advancing the public key protects everything created
    from now on, which is the urgent half; the backlog is already readable by whoever left, so
    re-sealing it can proceed afterwards, progressively. See ADR-0007 §2.
    """
    # org_session, not db_session: the audit row is org-scoped, and `audit_events`' WITH CHECK
    # compares against the tenant GUC. On an unbound session the INSERT is refused by RLS — and
    # `AuditLog.record` swallows that by design, so the rotation would succeed while its audit
    # entry vanished silently. Rotation itself is unaffected either way; the log is the reason.
    async with org_session(member.organization_id) as session:
        service = RotationService(SqlRotationRepository(session), AuditLog(SqlAuditSink(session)))
        try:
            generation = await service.rotate(
                member.organization_id,
                member.user.id,
                public_key=payload.public_key,
                member_keys=[
                    SealedMemberKey(user_id=k.user_id, sealed_org_key=k.sealed_org_key)
                    for k in payload.member_keys
                ],
            )
        except NotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (MembersWithoutKeypair, MembersLeftBehind) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except NotAMember as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RotateKeyOut(generation=generation)
