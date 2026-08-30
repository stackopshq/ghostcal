"""Signup must bind the tenant it is about to create, whoever owns the schema.

`provision_account` inserts the row that *defines* a tenant into a table carrying FORCE
ROW LEVEL SECURITY, whose policy is checked against an id that does not exist until that
insert runs. It only passes because the function sets `app.current_org_id` to the id it
generated. Remove that and every password registration returns 500.

**A plain registration test cannot guard this, and that is the whole lesson here.**
SECURITY DEFINER runs the body as the function's owner; `compose.yaml` and CI make that
owner the cluster's bootstrap superuser, and a superuser is exempt from RLS outright.
`test_auth.py::test_full_auth_flow` therefore passes with or without the fix on every
development stack. Its OIDC twin was corrected on 2026-08-13 and this path was not — for
a year the suite was green either way, which is precisely how the defect survived.

So the test does not rely on the ownership it happens to run under. It flips the function
to SECURITY INVOKER inside a transaction it rolls back, drops into a role that RLS
applies to, and calls it there. DDL is transactional in PostgreSQL, so the flip never
outlives the test. What is measured is the property that was lost — the function binds
the tenant before inserting — and it is measured the same way on a superuser-owned CI
schema and on a production-shaped one.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ghostcal.config import get_settings

pytestmark = pytest.mark.integration

_SIGNATURE = "provision_account(text, text, text, text, text)"
_SAFE_ROLE = re.compile(r"\A[a-z_][a-z0-9_]*\Z")
_IS_EXEMPT = "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = :role"


def _application_role() -> str:
    """The role the app connects as — non-superuser and NOBYPASSRLS by construction.

    Read from the URL rather than hard-coded, so a deployment that renames the role does
    not get a test quietly measuring a role that no longer exists.
    """
    role = urlsplit(str(get_settings().database_url)).username
    assert role and _SAFE_ROLE.match(role), f"unusable role name in the app URL: {role!r}"
    return role


async def test_signup_binds_its_tenant_before_inserting(admin_engine: AsyncEngine) -> None:
    suffix = uuid.uuid4().hex[:8]

    async with admin_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text(f"ALTER FUNCTION {_SIGNATURE} SECURITY INVOKER"))

            caller = (await conn.execute(text("SELECT current_user"))).scalar_one()
            if (await conn.execute(text(_IS_EXEMPT), {"role": caller})).scalar_one():
                await conn.execute(text(f"SET LOCAL ROLE {_application_role()}"))
                caller = (await conn.execute(text("SELECT current_user"))).scalar_one()

            # Without this the test would exercise a role RLS never applies to, and would
            # pass against a broken function while proving nothing at all — the same way
            # the registration test has been passing since the defect was introduced.
            assert not (await conn.execute(text(_IS_EXEMPT), {"role": caller})).scalar_one(), (
                f"{caller!r} is exempt from row-level security, so this test cannot "
                "observe the policy it exists to check"
            )

            await conn.execute(
                text(
                    "SELECT user_id FROM provision_account("
                    ":email, :name, :password_hash, :org_name, :org_slug)"
                ),
                {
                    "email": f"rls-{suffix}@example.test",
                    "name": "RLS Witness",
                    "password_hash": "not-a-real-hash",
                    "org_name": "RLS Witness",
                    "org_slug": f"rls-witness-{suffix}",
                },
            )
        finally:
            # Rolls back the row *and* the SECURITY INVOKER flip: both are transactional.
            await transaction.rollback()
