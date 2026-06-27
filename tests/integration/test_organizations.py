"""Organization management against a live PostgreSQL: members, roles, invitations, authz."""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.organizations import (
    LastOwner,
    NotAuthorized,
    OrgActor,
    OrganizationService,
    accept_invitation,
    preview_invitation,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.org_repository import SqlInvitationGateway, SqlOrgRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec

pytestmark = pytest.mark.integration

PASSWORD = "s3cret-passw0rd"
_HASHER = Argon2PasswordHasher()
_CODEC = JwtAccessTokenCodec("test-secret-of-at-least-32-characters!", timedelta(minutes=15))
_CLOCK = SystemClock()
_CONFIG = AuthConfig(
    access_ttl=timedelta(minutes=15),
    refresh_ttl=timedelta(days=30),
    email_verification_ttl=timedelta(hours=24),
    frontend_base_url="http://localhost:3001",
)


class CapturingMailer:
    def __init__(self) -> None:
        self.last_html: str | None = None

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.last_html = html

    def verify_token(self) -> str:
        assert self.last_html is not None
        match = re.search(r"token=([^\"]+)", self.last_html)
        assert match is not None
        return match.group(1)

    def invite_token(self) -> str:
        assert self.last_html is not None
        match = re.search(r"/invitations/([^\"]+)", self.last_html)
        assert match is not None
        return match.group(1)


def _auth(session: object, mailer: CapturingMailer) -> AuthService:
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG)  # type: ignore[arg-type]


def _org(session: object, org_id: uuid.UUID, mailer: CapturingMailer) -> OrganizationService:
    return OrganizationService(
        SqlOrgRepository(session, org_id),  # type: ignore[arg-type]
        mailer,
        _CLOCK,
        frontend_base_url="http://localhost:3001",
        invitation_ttl=timedelta(days=7),
    )


async def _register_verified(mailer: CapturingMailer, email: str, name: str) -> uuid.UUID:
    async with db_session() as s:
        user_id = await _auth(s, mailer).register(email=email, name=name, password=PASSWORD)
    token = mailer.verify_token()
    async with db_session() as s:
        await _auth(s, mailer).verify_email(token=token)
    return user_id


async def _delete_user(engine: AsyncEngine, user_id: uuid.UUID) -> None:
    async with async_sessionmaker(engine)() as s:
        org_ids = (
            (
                await s.execute(
                    text("SELECT organization_id FROM memberships WHERE user_id = :u"),
                    {"u": user_id},
                )
            )
            .scalars()
            .all()
        )
        for org_id in org_ids:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
        await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await s.commit()


async def test_org_members_roles_and_invitations(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    suffix = uuid.uuid4().hex[:8]
    owner_id = invitee_id = None
    org_id: uuid.UUID | None = None
    try:
        owner_id = await _register_verified(mailer, f"owner-{suffix}@example.test", "Owner")
        invitee_id = await _register_verified(mailer, f"invitee-{suffix}@example.test", "Invitee")

        membership = None
        async with db_session() as s:
            membership = await primary_membership(s, owner_id)
        assert membership is not None
        org_id, owner_role = membership
        assert owner_role == "owner"
        owner = OrgActor(organization_id=org_id, user_id=owner_id, role="owner")

        # Owner sees themselves as the only member.
        async with org_session(org_id) as s:
            members = await _org(s, org_id, mailer).list_members(owner)
        assert len(members) == 1

        # Owner invites a member; the email carries an accept link.
        invitee_email = f"invitee-{suffix}@example.test"
        async with org_session(org_id) as s:
            await _org(s, org_id, mailer).invite(owner, email=invitee_email, role="member")
        invite_token = mailer.invite_token()

        async with org_session(org_id) as s:
            invitations = await _org(s, org_id, mailer).list_invitations(owner)
        assert len(invitations) == 1

        # Preview (token-based, non-tenant) shows org + role.
        async with db_session() as s:
            preview = await preview_invitation(SqlInvitationGateway(s), token=invite_token)
        assert preview.role == "member"
        assert preview.organization_id == org_id

        # The invitee accepts and becomes a member.
        async with db_session() as s:
            joined_org = await accept_invitation(
                SqlInvitationGateway(s), token=invite_token, user_id=invitee_id
            )
        assert joined_org == org_id
        async with org_session(org_id) as s:
            members = await _org(s, org_id, mailer).list_members(owner)
        assert len(members) == 2

        # The pending invitation is gone.
        async with org_session(org_id) as s:
            invitations = await _org(s, org_id, mailer).list_invitations(owner)
        assert invitations == []

        # Owner promotes the member to admin.
        async with org_session(org_id) as s:
            await _org(s, org_id, mailer).change_role(
                owner, target_user_id=invitee_id, role="admin"
            )

        # An admin cannot grant admin/owner (only owners can).
        admin_actor = OrgActor(organization_id=org_id, user_id=invitee_id, role="admin")
        with pytest.raises(NotAuthorized):
            async with org_session(org_id) as s:
                await _org(s, org_id, mailer).invite(
                    admin_actor, email=f"x-{suffix}@example.test", role="admin"
                )

        # The last owner can't be demoted.
        with pytest.raises(LastOwner):
            async with org_session(org_id) as s:
                await _org(s, org_id, mailer).change_role(
                    owner, target_user_id=owner_id, role="member"
                )

        # Owner removes the admin.
        async with org_session(org_id) as s:
            await _org(s, org_id, mailer).remove_member(owner, target_user_id=invitee_id)
        async with org_session(org_id) as s:
            members = await _org(s, org_id, mailer).list_members(owner)
        assert len(members) == 1
    finally:
        for uid in (invitee_id, owner_id):
            if uid is not None:
                await _delete_user(admin_engine, uid)
