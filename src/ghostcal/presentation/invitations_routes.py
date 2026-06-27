"""Invitation accept/preview endpoints — reached by token, before the invitee is a member."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ghostcal.application.organizations import (
    InvitationInvalid,
    accept_invitation,
    preview_invitation,
)
from ghostcal.infrastructure.db.org_repository import SqlInvitationGateway
from ghostcal.infrastructure.db.session import db_session
from ghostcal.presentation.auth_routes import CurrentUser
from ghostcal.presentation.schemas import AcceptInvitationOut, InvitationPreviewOut

router = APIRouter(prefix="/v1/invitations", tags=["invitations"])


@router.get("/{token}", response_model=InvitationPreviewOut)
async def preview(token: str) -> InvitationPreviewOut:
    async with db_session() as session:
        try:
            result = await preview_invitation(SqlInvitationGateway(session), token=token)
        except InvitationInvalid as exc:
            raise HTTPException(status_code=404, detail="invalid or expired invitation") from exc
    return InvitationPreviewOut(
        organization_id=result.organization_id,
        organization_name=result.organization_name,
        email=result.email,
        role=result.role,
    )


@router.post("/{token}/accept", response_model=AcceptInvitationOut)
async def accept(token: str, user: CurrentUser) -> AcceptInvitationOut:
    async with db_session() as session:
        try:
            org_id = await accept_invitation(
                SqlInvitationGateway(session), token=token, user_id=user.id
            )
        except InvitationInvalid as exc:
            raise HTTPException(status_code=404, detail="invalid or expired invitation") from exc
    return AcceptInvitationOut(organization_id=org_id)
