"""SQL implementations of the organization-management ports.

``SqlOrgRepository`` runs under an org-scoped session (RLS applies). ``SqlInvitationGateway`` runs
on a plain session and reaches invitations by token through SECURITY DEFINER functions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.organizations import (
    InvitationExists,
    InvitationGateway,
    InvitationPreview,
    OrgMember,
    OrgRepository,
    PendingInvitation,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_org, bind_user


class SqlOrgRepository(OrgRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_members(self, org_id: uuid.UUID) -> list[OrgMember]:
        rows = (
            await self._session.execute(
                select(
                    models.Membership.user_id,
                    models.User.name,
                    models.User.email,
                    models.Membership.role,
                    models.Membership.created_at,
                )
                .join(models.User, models.User.id == models.Membership.user_id)
                .where(models.Membership.organization_id == org_id)
                .order_by(models.Membership.created_at)
            )
        ).all()
        return [
            OrgMember(
                user_id=r.user_id,
                name=r.name,
                email=r.email,
                role=r.role,
                joined_at=r.created_at,
            )
            for r in rows
        ]

    async def count_owners(self, org_id: uuid.UUID) -> int:
        return (
            await self._session.execute(
                select(func.count())
                .select_from(models.Membership)
                .where(
                    models.Membership.organization_id == org_id,
                    models.Membership.role == "owner",
                )
            )
        ).scalar_one()

    async def member_role(self, org_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        return (
            await self._session.execute(
                select(models.Membership.role).where(
                    models.Membership.organization_id == org_id,
                    models.Membership.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def email_is_member(self, org_id: uuid.UUID, email: str) -> bool:
        result = (
            await self._session.execute(
                select(models.Membership.user_id)
                .join(models.User, models.User.id == models.Membership.user_id)
                .where(
                    models.Membership.organization_id == org_id,
                    func.lower(models.User.email) == email.lower(),
                )
            )
        ).first()
        return result is not None

    async def update_member_role(self, org_id: uuid.UUID, user_id: uuid.UUID, role: str) -> bool:
        result = await self._session.execute(
            update(models.Membership)
            .where(
                models.Membership.organization_id == org_id,
                models.Membership.user_id == user_id,
            )
            .values(role=role)
            .returning(models.Membership.id)
        )
        return result.first() is not None

    async def remove_member(self, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.Membership)
            .where(
                models.Membership.organization_id == org_id,
                models.Membership.user_id == user_id,
            )
            .returning(models.Membership.id)
        )
        return result.first() is not None

    async def has_pending_invitation(self, org_id: uuid.UUID, email: str) -> bool:
        result = (
            await self._session.execute(
                select(models.OrganizationInvitation.id).where(
                    models.OrganizationInvitation.organization_id == org_id,
                    func.lower(models.OrganizationInvitation.email) == email.lower(),
                    models.OrganizationInvitation.accepted_at.is_(None),
                )
            )
        ).first()
        return result is not None

    async def create_invitation(
        self,
        org_id: uuid.UUID,
        *,
        email: str,
        role: str,
        token_hash: str,
        invited_by: uuid.UUID,
        expires_at: datetime,
        wrapped_org_key: str | None = None,
    ) -> PendingInvitation:
        try:
            row = (
                await self._session.execute(
                    insert(models.OrganizationInvitation)
                    .values(
                        organization_id=org_id,
                        email=email,
                        role=role,
                        token_hash=token_hash,
                        invited_by_user_id=invited_by,
                        expires_at=expires_at,
                        wrapped_org_key=wrapped_org_key,
                    )
                    .returning(
                        models.OrganizationInvitation.id,
                        models.OrganizationInvitation.created_at,
                    )
                )
            ).one()
        except IntegrityError as exc:
            raise InvitationExists(email) from exc
        return PendingInvitation(
            id=row.id, email=email, role=role, created_at=row.created_at, expires_at=expires_at
        )

    async def list_invitations(self, org_id: uuid.UUID) -> list[PendingInvitation]:
        rows = (
            (
                await self._session.execute(
                    select(models.OrganizationInvitation)
                    .where(
                        models.OrganizationInvitation.organization_id == org_id,
                        models.OrganizationInvitation.accepted_at.is_(None),
                    )
                    .order_by(models.OrganizationInvitation.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [
            PendingInvitation(
                id=r.id,
                email=r.email,
                role=r.role,
                created_at=r.created_at,
                expires_at=r.expires_at,
            )
            for r in rows
        ]

    async def revoke_invitation(self, org_id: uuid.UUID, invitation_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.OrganizationInvitation)
            .where(
                models.OrganizationInvitation.organization_id == org_id,
                models.OrganizationInvitation.id == invitation_id,
                models.OrganizationInvitation.accepted_at.is_(None),
            )
            .returning(models.OrganizationInvitation.id)
        )
        return result.first() is not None


class SqlInvitationGateway(InvitationGateway):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def preview(self, token_hash: str) -> InvitationPreview | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT organization_id, organization_name, email, role, wrapped_org_key "
                    "FROM organization_invitation_preview(:h)"
                ),
                {"h": token_hash},
            )
        ).first()
        if row is None:
            return None
        return InvitationPreview(
            organization_id=row.organization_id,
            organization_name=row.organization_name,
            email=row.email,
            role=row.role,
            wrapped_org_key=row.wrapped_org_key,
        )

    async def accept(self, token_hash: str, user_id: uuid.UUID) -> uuid.UUID | None:
        return (  # type: ignore[no-any-return]
            await self._session.execute(
                text("SELECT accept_organization_invitation(:h, :u) AS org"),
                {"h": token_hash, "u": str(user_id)},
            )
        ).scalar_one()

    async def store_member_key(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        wrapped_private_key: str,
        wrap_salt: str,
    ) -> None:
        # Declare both contexts before the definer function runs, exactly as
        # `_bind_user_and_org` does in the auth repository, and for the same reason: SECURITY
        # DEFINER changes the role a function runs as, never the session it runs in. Under FORCE
        # ROW LEVEL SECURITY it therefore inherits no sight of its own.
        #
        # The user GUC opens the self-read policy on `memberships`, which is what the function's
        # own membership check reads; the org GUC opens `tenant_isolation` on `org_member_keys`,
        # which is what it writes. Without the first it refused with "user X is not a member of
        # organization Y" — a false refusal, the membership being right there — and with only the
        # first it got past that and was refused by the policy on the insert instead.
        #
        # Binding an organization the caller does not belong to grants nothing: the membership
        # check inside the function is the gate, and it runs after these declarations. Same trust
        # model as everywhere else here — the application declares, the policies enforce, row by
        # row, with no bypass.
        await bind_user(self._session, user_id)
        await bind_org(self._session, org_id)
        await self._session.execute(
            text("SELECT store_member_org_key(:o, :u, :w, :s)"),
            {"o": str(org_id), "u": str(user_id), "w": wrapped_private_key, "s": wrap_salt},
        )
