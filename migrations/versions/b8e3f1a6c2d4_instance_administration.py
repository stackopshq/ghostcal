"""instance administration: suspension, last sign-in, instance settings

An instance now has administrators (``GHOSTCAL_ADMIN_EMAILS``) who can see every account, suspend
or erase one, and open or close sign-up. Three things in the database follow from that:

- ``users.suspended_at``: a suspended account keeps its data and cannot sign in. NULL means active.
- ``users.last_login_at``: written on a password or SSO sign-in, not on a token refresh; it is what
  the administration view shows as "last sign-in".
- ``instance_settings``: key/value rows for choices made from the view. Only ``registration`` for
  now. Global, like ``refresh_tokens``: it belongs to no organization and carries no RLS.

``users`` is under FORCE ROW LEVEL SECURITY and its policies only ever open the caller's own row
(or the members of the current organization). An instance administrator needs every row, so two
policies open them when the transaction declares ``app.instance_admin = 'on'``. Same trust model as
``app.current_user_id`` and ``app.retention_scan``: the application declares, after checking the
caller against ``GHOSTCAL_ADMIN_EMAILS``, and only ``bind_instance_admin`` sets it. Transaction
local, so it cannot outlive the request on a pooled connection.

Revision ID: b8e3f1a6c2d4
Revises: a7c2e9d41b38
Create Date: 2026-11-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e3f1a6c2d4"
down_revision: str | Sequence[str] | None = "a7c2e9d41b38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADMIN_GUC = "NULLIF(current_setting('app.instance_admin', true), '') = 'on'"


def upgrade() -> None:
    op.add_column("users", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "instance_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.execute(f"CREATE POLICY users_instance_admin_read ON users FOR SELECT USING ({_ADMIN_GUC})")
    op.execute(
        "CREATE POLICY users_instance_admin_update ON users FOR UPDATE "
        f"USING ({_ADMIN_GUC}) WITH CHECK ({_ADMIN_GUC})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_instance_admin_update ON users")
    op.execute("DROP POLICY IF EXISTS users_instance_admin_read ON users")
    op.drop_table("instance_settings")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "suspended_at")
