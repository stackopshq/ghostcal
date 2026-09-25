"""a member can read their own org keys, in every organization they belong to

Joining a second organization worked up to the moment of using it. `get_zk_keys` binds the caller's
PRIMARY organization (`_bind_user_and_org` → `user_primary_organization`), and `org_member_keys`
carried only `tenant_isolation` — organization_id = the bound org. So a member of two organizations
saw the keys of exactly one, and the one they had just been granted was invisible.

Measured on 2026-08-31 against a schema owned by a plain role, running the existing
`test_team_key_grant_flow`: the invitee accepts, their key is stored, and `get_zk_keys` returns no
row for the organization they just joined.

The policy added here is the third of a family that already exists for the same reason —
`memberships_self_read` and `organizations_member_read`, both added by e8a1b3c5d7f9 — and it has the
same shape: the application declares who it is acting for, the policy enforces row by row, and
nothing is bypassed.

**What it exposes is a user's own key envelopes, and nothing else.** The predicate is
`user_id = app.current_user_id`: no other member's row matches, in any organization. The rows
themselves are a private key wrapped under that user's password, and a copy wrapped under their
recovery phrase — both useless to whoever cannot supply one of the two. This is exactly what the
browser fetches at login and could already fetch for the primary organization; the change is that a
second organization stops being a blind spot.

`FOR SELECT` deliberately. Writing a member key stays the business of `store_member_org_key`, which
checks membership before it writes; a permissive write policy here would let a caller create key
rows in an organization the function would have refused.

Revision ID: f2a9c41e73b6
Revises: d5c1a83f04e6
"""

from __future__ import annotations

from alembic import op

revision = "f2a9c41e73b6"
down_revision = "d5c1a83f04e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY org_member_keys_self_read ON org_member_keys
        FOR SELECT
        USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_member_keys_self_read ON org_member_keys")
