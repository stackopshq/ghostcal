"""declared-slug policy, so public booking pages resolve their organization

The public booking page is anonymous by design — a visitor follows
`/{org-slug}/{event-slug}` with no account. Resolving that slug to an
organization id is therefore a lookup with no user context, and under FORCE ROW
LEVEL SECURITY the definer function `organization_id_by_slug` sees nothing:
every shared booking link 404'd. Measured on 2026-08-13 on the deployed
instance, minutes after the first booking link was shared.

Same doctrine as the self-read policies (e8a1b3c5d7f9): **the caller declares,
the policy checks — row by row, no bypass.** Here the application declares the
slug it is resolving, via `app.public_lookup_slug`. Only the organization
carrying exactly that slug becomes visible, and only for SELECT.

What this deliberately does NOT allow: enumeration. A caller learns nothing it
did not already hold — it must present the slug, which is the URL itself. A
blanket `USING (true)` SELECT policy would have worked too and was rejected:
it would have let any tenant list every organization row.

Revision ID: a9c2e4f61b83
Revises: e8a1b3c5d7f9
"""

from __future__ import annotations

from alembic import op

revision = "a9c2e4f61b83"
down_revision = "e8a1b3c5d7f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY organizations_slug_lookup ON organizations
            FOR SELECT
            USING (slug = NULLIF(current_setting('app.public_lookup_slug', true), ''))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organizations_slug_lookup ON organizations")
