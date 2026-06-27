"""Organization management use cases: members, roles, invitations.

Two surfaces:
- ``OrganizationService`` — org-scoped management (list/invite/role/remove), guarded by the actor's
  role. Constructed with an ``OrgRepository`` bound to an org-scoped session.
- ``preview_invitation`` / ``accept_invitation`` — token-based, used by an invitee who may not be a
  member yet, so they go through SECURITY DEFINER functions on a non-tenant ``InvitationGateway``.

Role model: ``owner`` > ``admin`` > ``member``. Managers (owner/admin) manage the team; only an
owner may grant or touch admin/owner roles; the last owner can never be demoted or removed.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from ghostcal.application.ports.clock import Clock
from ghostcal.application.ports.email import EmailSender

MEMBER_ROLES = ("owner", "admin", "member")
MANAGER_ROLES = frozenset({"owner", "admin"})


class OrgError(Exception):
    """Base class for organization-management errors."""


class NotAuthorized(OrgError):
    pass


class MemberNotFound(OrgError):
    pass


class LastOwner(OrgError):
    pass


class AlreadyMember(OrgError):
    pass


class InvitationExists(OrgError):
    pass


class InvalidRole(OrgError):
    pass


class InvitationInvalid(OrgError):
    pass


@dataclass(frozen=True, slots=True)
class OrgActor:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class OrgMember:
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class PendingInvitation:
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class InvitationPreview:
    organization_id: uuid.UUID
    organization_name: str
    email: str
    role: str


class OrgRepository:
    """Org-scoped persistence (runs under an org_session, so RLS also applies)."""

    async def list_members(self, org_id: uuid.UUID) -> list[OrgMember]:
        raise NotImplementedError

    async def count_owners(self, org_id: uuid.UUID) -> int:
        raise NotImplementedError

    async def member_role(self, org_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        raise NotImplementedError

    async def email_is_member(self, org_id: uuid.UUID, email: str) -> bool:
        raise NotImplementedError

    async def update_member_role(self, org_id: uuid.UUID, user_id: uuid.UUID, role: str) -> bool:
        raise NotImplementedError

    async def remove_member(self, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def has_pending_invitation(self, org_id: uuid.UUID, email: str) -> bool:
        raise NotImplementedError

    async def create_invitation(
        self,
        org_id: uuid.UUID,
        *,
        email: str,
        role: str,
        token_hash: str,
        invited_by: uuid.UUID,
        expires_at: datetime,
    ) -> PendingInvitation:
        raise NotImplementedError

    async def list_invitations(self, org_id: uuid.UUID) -> list[PendingInvitation]:
        raise NotImplementedError

    async def revoke_invitation(self, org_id: uuid.UUID, invitation_id: uuid.UUID) -> bool:
        raise NotImplementedError


class InvitationGateway:
    """Token-based, non-tenant access via SECURITY DEFINER functions."""

    async def preview(self, token_hash: str) -> InvitationPreview | None:
        raise NotImplementedError

    async def accept(self, token_hash: str, user_id: uuid.UUID) -> uuid.UUID | None:
        raise NotImplementedError


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def _can_manage(actor_role: str, target_role: str) -> bool:
    """Owners manage everyone; admins manage only plain members."""
    if actor_role == "owner":
        return True
    if actor_role == "admin":
        return target_role == "member"
    return False


class OrganizationService:
    def __init__(
        self,
        repo: OrgRepository,
        mailer: EmailSender,
        clock: Clock,
        *,
        frontend_base_url: str,
        invitation_ttl: timedelta,
    ) -> None:
        self._repo = repo
        self._mailer = mailer
        self._clock = clock
        self._frontend_base_url = frontend_base_url.rstrip("/")
        self._invitation_ttl = invitation_ttl

    async def list_members(self, actor: OrgActor) -> list[OrgMember]:
        return await self._repo.list_members(actor.organization_id)

    async def list_invitations(self, actor: OrgActor) -> list[PendingInvitation]:
        self._require_manager(actor)
        return await self._repo.list_invitations(actor.organization_id)

    async def invite(self, actor: OrgActor, *, email: str, role: str) -> PendingInvitation:
        self._require_manager(actor)
        if role not in MEMBER_ROLES:
            raise InvalidRole(f"unknown role: {role}")
        self._require_can_assign(actor.role, role)
        email = email.strip().lower()
        org_id = actor.organization_id
        if await self._repo.email_is_member(org_id, email):
            raise AlreadyMember(email)
        if await self._repo.has_pending_invitation(org_id, email):
            raise InvitationExists(email)

        plain = secrets.token_urlsafe(32)
        expires_at = self._clock.now() + self._invitation_ttl
        invitation = await self._repo.create_invitation(
            org_id,
            email=email,
            role=role,
            token_hash=_hash_token(plain),
            invited_by=actor.user_id,
            expires_at=expires_at,
        )
        link = f"{self._frontend_base_url}/invitations/{plain}"
        await self._mailer.send(
            to=email,
            subject="You've been invited to a GhostCal team",
            html=(
                "<p>You've been invited to join a team on GhostCal.</p>"
                f'<p><a href="{link}">Accept the invitation</a></p>'
            ),
        )
        return invitation

    async def revoke_invitation(self, actor: OrgActor, *, invitation_id: uuid.UUID) -> None:
        self._require_manager(actor)
        if not await self._repo.revoke_invitation(actor.organization_id, invitation_id):
            raise InvitationInvalid("unknown invitation")

    async def change_role(self, actor: OrgActor, *, target_user_id: uuid.UUID, role: str) -> None:
        self._require_manager(actor)
        if role not in MEMBER_ROLES:
            raise InvalidRole(f"unknown role: {role}")
        org_id = actor.organization_id
        target_role = await self._repo.member_role(org_id, target_user_id)
        if target_role is None:
            raise MemberNotFound(str(target_user_id))
        if not _can_manage(actor.role, target_role):
            raise NotAuthorized("cannot manage this member")
        self._require_can_assign(actor.role, role)
        if target_role == "owner" and role != "owner":
            await self._guard_last_owner(org_id)
        await self._repo.update_member_role(org_id, target_user_id, role)

    async def remove_member(self, actor: OrgActor, *, target_user_id: uuid.UUID) -> None:
        self._require_manager(actor)
        org_id = actor.organization_id
        target_role = await self._repo.member_role(org_id, target_user_id)
        if target_role is None:
            raise MemberNotFound(str(target_user_id))
        # Members may remove themselves (leave); managing others follows the role rules.
        if target_user_id != actor.user_id and not _can_manage(actor.role, target_role):
            raise NotAuthorized("cannot remove this member")
        if target_role == "owner":
            await self._guard_last_owner(org_id)
        await self._repo.remove_member(org_id, target_user_id)

    async def _guard_last_owner(self, org_id: uuid.UUID) -> None:
        if await self._repo.count_owners(org_id) <= 1:
            raise LastOwner("an organization must keep at least one owner")

    def _require_manager(self, actor: OrgActor) -> None:
        if actor.role not in MANAGER_ROLES:
            raise NotAuthorized("requires owner or admin")

    def _require_can_assign(self, actor_role: str, new_role: str) -> None:
        # Only an owner may grant admin or owner.
        if new_role in ("owner", "admin") and actor_role != "owner":
            raise NotAuthorized("only an owner can grant admin or owner")


async def preview_invitation(gateway: InvitationGateway, *, token: str) -> InvitationPreview:
    preview = await gateway.preview(_hash_token(token))
    if preview is None:
        raise InvitationInvalid("invalid or expired invitation")
    return preview


async def accept_invitation(
    gateway: InvitationGateway, *, token: str, user_id: uuid.UUID
) -> uuid.UUID:
    org_id = await gateway.accept(_hash_token(token), user_id)
    if org_id is None:
        raise InvitationInvalid("invalid or expired invitation")
    return org_id
