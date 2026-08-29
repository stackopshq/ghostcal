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
    InvitationInvalid,
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
from tests.integration.conftest import ZK_PLACEHOLDER

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
        user_id = await _auth(s, mailer).register(
            email=email, name=name, password=PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
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
        #
        # This assertion is the guard for the whole invitation flow, and it was always
        # written correctly — what lied was the environment it ran in. `db_session()`
        # binds no tenant, exactly like the unauthenticated request an invitee makes, so
        # under FORCE ROW LEVEL SECURITY the SECURITY DEFINER function sees nothing
        # unless a policy grants it sight. It passed anyway for as long as CI owned the
        # schema with the cluster's bootstrap superuser, which bypasses RLS outright. Run
        # this against a plain owner and it fails without migration d1f4a72b98c0 — which
        # is what every invitee got.
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


async def test_invitation_rejects_mismatched_email(admin_engine: AsyncEngine) -> None:
    """A leaked invitation link cannot be redeemed by an account with a different email.

    Defence against link leakage: ``accept_organization_invitation`` binds acceptance to the
    invited address (pentest finding), so only the verified owner of that email may join.
    """
    mailer = CapturingMailer()
    suffix = uuid.uuid4().hex[:8]
    owner_id = invited_id = attacker_id = None
    try:
        owner_id = await _register_verified(mailer, f"mowner-{suffix}@example.test", "Owner")
        invited_id = await _register_verified(mailer, f"minvited-{suffix}@example.test", "Invited")
        attacker_id = await _register_verified(
            mailer, f"mattacker-{suffix}@example.test", "Mallory"
        )

        async with db_session() as s:
            membership = await primary_membership(s, owner_id)
        assert membership is not None
        org_id, _ = membership
        owner = OrgActor(organization_id=org_id, user_id=owner_id, role="owner")

        # Owner invites the legitimate address as an admin (a juicy target if leaked).
        async with org_session(org_id) as s:
            await _org(s, org_id, mailer).invite(
                owner, email=f"minvited-{suffix}@example.test", role="admin"
            )
        token = mailer.invite_token()

        # The attacker (different email) intercepts the link — acceptance must be refused.
        with pytest.raises(InvitationInvalid):
            async with db_session() as s:
                await accept_invitation(SqlInvitationGateway(s), token=token, user_id=attacker_id)

        # The intended recipient can still accept.
        async with db_session() as s:
            joined = await accept_invitation(
                SqlInvitationGateway(s), token=token, user_id=invited_id
            )
        assert joined == org_id
    finally:
        for uid in (attacker_id, invited_id, owner_id):
            if uid is not None:
                await _delete_user(admin_engine, uid)


async def test_team_key_grant_flow(admin_engine: AsyncEngine) -> None:
    """Invite carries a wrapped org key; the joiner can store their re-wrapped copy; get_zk_keys
    then returns the joined org's key (zero-knowledge team sharing, ADR-0003)."""
    mailer = CapturingMailer()
    suffix = uuid.uuid4().hex[:8]
    owner_id = invitee_id = None
    try:
        owner_id = await _register_verified(mailer, f"kowner-{suffix}@example.test", "Owner")
        invitee_id = await _register_verified(mailer, f"kinvitee-{suffix}@example.test", "Invitee")

        async with db_session() as s:
            membership = await primary_membership(s, owner_id)
        assert membership is not None
        org_id, _ = membership
        owner = OrgActor(organization_id=org_id, user_id=owner_id, role="owner")

        # Invite with the org key sealed under the link-fragment grant key.
        async with org_session(org_id) as s:
            invitation = await _org(s, org_id, mailer).invite(
                owner,
                email=f"kinvitee-{suffix}@example.test",
                role="member",
                wrapped_org_key="WRAPPED-ORG-KEY-BLOB",
            )
        assert invitation.token is not None  # returned so the inviter can build the secure link
        token = mailer.invite_token()

        # The preview exposes the wrapped org key to the accept page.
        async with db_session() as s:
            preview = await preview_invitation(SqlInvitationGateway(s), token=token)
        assert preview.wrapped_org_key == "WRAPPED-ORG-KEY-BLOB"

        # Accept, then store the member's re-wrapped copy.
        async with db_session() as s:
            await accept_invitation(SqlInvitationGateway(s), token=token, user_id=invitee_id)
        async with db_session() as s:
            await SqlInvitationGateway(s).store_member_key(
                org_id, invitee_id, wrapped_private_key="MEMBER-WRAPPED", wrap_salt="MEMBER-SALT"
            )

        # The joiner's keys now include the joined org's key, with no recovery copy.
        async with db_session() as s:
            keys = await SqlAuthRepository(s).get_zk_keys(invitee_id)
        joined = next((k for k in keys if k.organization_id == org_id), None)
        assert joined is not None
        assert joined.wrapped_private_key == "MEMBER-WRAPPED"
        assert joined.recovery_wrapped_private_key is None
    finally:
        for uid in (invitee_id, owner_id):
            if uid is not None:
                await _delete_user(admin_engine, uid)
