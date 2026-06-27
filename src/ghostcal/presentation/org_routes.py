"""Organization management endpoints (members, roles, invitations). Org-scoped, role-guarded."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.organizations import (
    AlreadyMember,
    InvalidRole,
    InvitationExists,
    InvitationInvalid,
    LastOwner,
    MemberNotFound,
    NotAuthorized,
    OrgActor,
    OrganizationService,
    PendingInvitation,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.org_repository import SqlOrgRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    InvitationOut,
    InviteIn,
    MemberOut,
    RoleUpdateIn,
)

router = APIRouter(prefix="/v1/me/organization", tags=["organization"])

_settings = get_settings()
_mailer = build_email_sender(_settings)
_clock = SystemClock()
_INVITATION_TTL = timedelta(seconds=_settings.invitation_ttl_seconds)


def _actor(member: Member) -> OrgActor:
    return OrgActor(
        organization_id=member.organization_id, user_id=member.user.id, role=member.role
    )


def _make(session: object, member: Member) -> OrganizationService:
    return OrganizationService(
        SqlOrgRepository(session, member.organization_id),  # type: ignore[arg-type]
        _mailer,
        _clock,
        frontend_base_url=_settings.frontend_base_url,
        invitation_ttl=_INVITATION_TTL,
    )


def _invitation_out(invitation: PendingInvitation) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
    )


@router.get("/members", response_model=list[MemberOut])
async def list_members(member: Member = Depends(current_member)) -> list[MemberOut]:
    async with org_session(member.organization_id) as session:
        members = await _make(session, member).list_members(_actor(member))
    return [
        MemberOut(user_id=m.user_id, name=m.name, email=m.email, role=m.role, joined_at=m.joined_at)
        for m in members
    ]


@router.patch("/members/{user_id}", response_model=list[MemberOut])
async def change_role(
    user_id: uuid.UUID, payload: RoleUpdateIn, member: Member = Depends(current_member)
) -> list[MemberOut]:
    async with org_session(member.organization_id) as session:
        service = _make(session, member)
        try:
            await service.change_role(_actor(member), target_user_id=user_id, role=payload.role)
        except NotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except MemberNotFound as exc:
            raise HTTPException(status_code=404, detail="member not found") from exc
        except LastOwner as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidRole as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        members = await service.list_members(_actor(member))
    return [
        MemberOut(user_id=m.user_id, name=m.name, email=m.email, role=m.role, joined_at=m.joined_at)
        for m in members
    ]


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(user_id: uuid.UUID, member: Member = Depends(current_member)) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await _make(session, member).remove_member(_actor(member), target_user_id=user_id)
        except NotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except MemberNotFound as exc:
            raise HTTPException(status_code=404, detail="member not found") from exc
        except LastOwner as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(member: Member = Depends(current_member)) -> list[InvitationOut]:
    async with org_session(member.organization_id) as session:
        try:
            invitations = await _make(session, member).list_invitations(_actor(member))
        except NotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_invitation_out(i) for i in invitations]


@router.post("/invitations", response_model=InvitationOut, status_code=201)
async def invite(payload: InviteIn, member: Member = Depends(current_member)) -> InvitationOut:
    async with org_session(member.organization_id) as session:
        try:
            invitation = await _make(session, member).invite(
                _actor(member), email=payload.email, role=payload.role
            )
        except NotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InvalidRole as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AlreadyMember as exc:
            raise HTTPException(status_code=409, detail="already a member") from exc
        except InvitationExists as exc:
            raise HTTPException(status_code=409, detail="already invited") from exc
    return _invitation_out(invitation)


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await _make(session, member).revoke_invitation(
                _actor(member), invitation_id=invitation_id
            )
        except NotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InvitationInvalid as exc:
            raise HTTPException(status_code=404, detail="invitation not found") from exc
