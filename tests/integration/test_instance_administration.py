"""Instance administration through the HTTP API, against PostgreSQL under FORCE RLS.

Every request runs as ``ghostcal_app``, as in production behind the policies: the listing and the
suspension only work because the ``users_instance_admin_*`` policies of migration b8e3f1a6c2d4
open the rows. The admin engine is used to seed (verify an address, add a membership) and to read
back what the API must not show.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.passwords import NoBreachCheck
from ghostcal.config import get_settings
from ghostcal.infrastructure import ratelimit
from ghostcal.presentation import auth_routes
from ghostcal.presentation.api import app
from tests.integration.conftest import ZK_PLACEHOLDER

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple-42"
ZK = {
    "public_key": ZK_PLACEHOLDER.public_key,
    "wrapped_private_key": ZK_PLACEHOLDER.wrapped_private_key,
    "wrap_salt": ZK_PLACEHOLDER.wrap_salt,
    "recovery_wrapped_private_key": ZK_PLACEHOLDER.recovery_wrapped_private_key,
    "recovery_salt": ZK_PLACEHOLDER.recovery_salt,
}


@dataclass
class Account:
    id: uuid.UUID
    email: str
    access: str
    refresh: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access}"}


class Instance:
    def __init__(self, client: AsyncClient, engine: AsyncEngine) -> None:
        self.client = client
        self.engine = engine
        self.created: list[uuid.UUID] = []

    async def sql(self, statement: str, **params: object) -> object:
        async with async_sessionmaker(self.engine)() as s:
            result = await s.execute(text(statement), params)
            await s.commit()
            return result

    async def scalar(self, statement: str, **params: object) -> object:
        async with async_sessionmaker(self.engine)() as s:
            return (await s.execute(text(statement), params)).scalar()

    async def register(self, email: str) -> uuid.UUID:
        response = await self.client.post(
            "/v1/auth/register",
            json={"email": email, "name": email.split("@")[0], "password": PASSWORD, "zk_keys": ZK},
        )
        assert response.status_code == 201, response.text
        user_id = uuid.UUID(response.json()["user_id"])
        self.created.append(user_id)
        return user_id

    async def account(self, tag: str) -> Account:
        email = f"{tag}-{uuid.uuid4().hex[:8]}@exemple-ghostcal.ch"
        user_id = await self.register(email)
        await self.sql("UPDATE users SET email_verified_at = now() WHERE id = :u", u=user_id)
        tokens = await self.login(email)
        assert tokens.status_code == 200, tokens.text
        body = tokens.json()
        return Account(user_id, email, body["access_token"], body["refresh_token"])

    async def login(self, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
        return await self.client.post("/v1/auth/login", json={"email": email, "password": password})


async def _always_allow(bucket: str, key: str, limit: int, window: int) -> bool:
    return True


@pytest_asyncio.fixture
async def instance(
    admin_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Instance]:
    settings = get_settings()
    # One cached Settings object serves every router: set it once, restored after the test.
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "registration", "")
    # The real checker would call api.pwnedpasswords.com; the length policy still applies.
    monkeypatch.setattr(auth_routes, "_breach_checker", NoBreachCheck())
    # Every request here comes from the same test client: the per-IP auth throttle would answer
    # 429 halfway through a test. It is exercised in tests/security, not here.
    monkeypatch.setattr(ratelimit, "_allow", _always_allow)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inst = Instance(client, admin_engine)
        await inst.sql("DELETE FROM instance_settings")
        try:
            yield inst
        finally:
            await inst.sql("DELETE FROM instance_settings")
            for user_id in inst.created:
                await inst.sql(
                    "DELETE FROM organizations WHERE id IN "
                    "(SELECT organization_id FROM memberships WHERE user_id = :u)",
                    u=user_id,
                )
                await inst.sql("DELETE FROM users WHERE id = :u", u=user_id)


def _make_admin(monkeypatch: pytest.MonkeyPatch, *accounts: Account) -> None:
    # Upper case and a stray space on purpose: the list is normalised.
    value = ", ".join(f" {a.email.upper()}" for a in accounts)
    monkeypatch.setattr(get_settings(), "admin_emails", value)


def _code(response) -> str:  # type: ignore[no-untyped-def]
    return response.json()["detail"]["code"]  # type: ignore[no-any-return]


async def test_an_ordinary_account_does_not_see_the_view(instance: Instance) -> None:
    user = await instance.account("user")
    client = instance.client
    some_id = uuid.uuid4()
    assert (await client.get("/v1/admin/accounts", headers=user.auth)).status_code == 404
    assert (await client.get("/v1/admin/registration", headers=user.auth)).status_code == 404
    put = await client.put("/v1/admin/registration", json={"open": False}, headers=user.auth)
    assert put.status_code == 404
    assert (
        await client.post(f"/v1/admin/accounts/{some_id}/suspend", headers=user.auth)
    ).status_code == 404
    me = await client.get("/v1/auth/me", headers=user.auth)
    assert me.json()["is_instance_admin"] is False


async def test_the_list_shows_metadata_and_nothing_sealed(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await instance.account("admin")
    user = await instance.account("user")
    _make_admin(monkeypatch, admin)

    me = await instance.client.get("/v1/auth/me", headers=admin.auth)
    assert me.json()["is_instance_admin"] is True

    response = await instance.client.get("/v1/admin/accounts", headers=admin.auth)
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()}
    assert {str(admin.id), str(user.id)} <= rows.keys()

    row = rows[str(user.id)]
    assert set(row) == {
        "id",
        "email",
        "name",
        "created_at",
        "email_verified",
        "last_login_at",
        "two_factor_enabled",
        "suspended_at",
        "is_admin",
    }
    assert row["email"] == user.email
    assert row["last_login_at"] is not None  # stamped by the sign-in in `account()`
    assert row["two_factor_enabled"] is False
    assert row["suspended_at"] is None
    assert row["is_admin"] is False
    assert rows[str(admin.id)]["is_admin"] is True

    # Nothing the server stores sealed or secret may appear, under any name.
    body = response.text.lower()
    for forbidden in ("password", "hash", "zk_", "wrapped", "salt", "secret", "public_key"):
        assert forbidden not in body, forbidden
    assert ZK_PLACEHOLDER.wrapped_private_key.lower() not in body


async def test_closing_registration_from_the_view(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await instance.account("admin")
    _make_admin(monkeypatch, admin)
    client = instance.client

    # Never chosen: open, as every instance was before this existed.
    assert (await client.get("/v1/auth/registration")).json() == {"open": True}
    state = await client.get("/v1/admin/registration", headers=admin.auth)
    assert state.json() == {"open": True, "fixed": False}

    closed = await client.put("/v1/admin/registration", json={"open": False}, headers=admin.auth)
    assert closed.json() == {"open": False, "fixed": False}
    assert (await client.get("/v1/auth/registration")).json() == {"open": False}

    refused = await client.post(
        "/v1/auth/register",
        json={
            "email": "late@exemple-ghostcal.ch",
            "name": "Late",
            "password": PASSWORD,
            "zk_keys": ZK,
        },
    )
    assert refused.status_code == 403
    assert _code(refused) == "registration_closed"
    assert (
        await instance.scalar("SELECT count(*) FROM users WHERE email = 'late@exemple-ghostcal.ch'")
        == 0
    )

    logged = await instance.scalar(
        "SELECT details->>'state' FROM audit_events WHERE action = 'admin.registration.changed' "
        "AND actor_user_id = :a ORDER BY created_at DESC LIMIT 1",
        a=admin.id,
    )
    assert logged == "closed"

    await client.put("/v1/admin/registration", json={"open": True}, headers=admin.auth)
    assert (await client.get("/v1/auth/registration")).json() == {"open": True}


async def test_the_environment_wins_over_the_view(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await instance.account("admin")
    _make_admin(monkeypatch, admin)
    client = instance.client
    # A choice made earlier from the view does not survive a pinned environment.
    await client.put("/v1/admin/registration", json={"open": True}, headers=admin.auth)
    monkeypatch.setattr(get_settings(), "registration", "closed")

    state = await client.get("/v1/admin/registration", headers=admin.auth)
    assert state.json() == {"open": False, "fixed": True}
    change = await client.put("/v1/admin/registration", json={"open": True}, headers=admin.auth)
    assert change.status_code == 409
    assert _code(change) == "registration_fixed"
    refused = await client.post(
        "/v1/auth/register",
        json={
            "email": "pinned@exemple-ghostcal.ch",
            "name": "P",
            "password": PASSWORD,
            "zk_keys": ZK,
        },
    )
    assert _code(refused) == "registration_closed"


async def test_an_unreadable_stored_value_reads_as_closed(instance: Instance) -> None:
    await instance.sql("INSERT INTO instance_settings (key, value) VALUES ('registration', 'nope')")
    assert (await instance.client.get("/v1/auth/registration")).json() == {"open": False}


async def test_suspension_closes_every_door(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await instance.account("admin")
    user = await instance.account("user")
    _make_admin(monkeypatch, admin)
    client = instance.client

    done = await client.post(f"/v1/admin/accounts/{user.id}/suspend", headers=admin.auth)
    assert done.status_code == 204

    # The access token is still signed and unexpired; it stops working on the next request.
    me = await client.get("/v1/auth/me", headers=user.auth)
    assert me.status_code == 403
    assert _code(me) == "account_suspended"
    # Every session ended: the refresh token is revoked.
    refreshed = await client.post("/v1/auth/refresh", json={"refresh_token": user.refresh})
    assert refreshed.status_code == 401
    # The right password says "suspended"; a wrong one says nothing about it.
    right = await instance.login(user.email)
    assert right.status_code == 403
    assert _code(right) == "account_suspended"
    wrong = await instance.login(user.email, "not-the-password-at-all")
    assert wrong.status_code == 401
    assert "suspended" not in wrong.text

    listed = await client.get("/v1/admin/accounts", headers=admin.auth)
    row = next(r for r in listed.json() if r["id"] == str(user.id))
    assert row["suspended_at"] is not None
    assert (
        await instance.scalar(
            "SELECT count(*) FROM audit_events "
            "WHERE action = 'admin.account.suspended' AND target = :t",
            t=str(user.id),
        )
        == 1
    )

    back = await client.post(f"/v1/admin/accounts/{user.id}/reactivate", headers=admin.auth)
    assert back.status_code == 204
    assert (await instance.login(user.email)).status_code == 200


async def test_an_administrator_is_out_of_reach_of_the_view(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await instance.account("admin1")
    second = await instance.account("admin2")
    _make_admin(monkeypatch, first, second)
    client = instance.client

    suspend = await client.post(f"/v1/admin/accounts/{second.id}/suspend", headers=first.auth)
    assert suspend.status_code == 409
    assert _code(suspend) == "account_is_admin"
    delete = await client.request(
        "DELETE",
        f"/v1/admin/accounts/{second.id}",
        json={"email_confirmation": second.email},
        headers=first.auth,
    )
    assert delete.status_code == 409
    assert _code(delete) == "account_is_admin"
    # Oneself included.
    self_suspend = await client.post(f"/v1/admin/accounts/{first.id}/suspend", headers=first.auth)
    assert self_suspend.status_code == 409


async def test_erasing_an_account(instance: Instance, monkeypatch: pytest.MonkeyPatch) -> None:
    admin = await instance.account("admin")
    user = await instance.account("user")
    _make_admin(monkeypatch, admin)
    client = instance.client
    url = f"/v1/admin/accounts/{user.id}"

    mismatch = await client.request(
        "DELETE", url, json={"email_confirmation": "someone@else.ch"}, headers=admin.auth
    )
    assert mismatch.status_code == 400
    assert await instance.scalar("SELECT count(*) FROM users WHERE id = :u", u=user.id) == 1

    erased = await client.request(
        "DELETE", url, json={"email_confirmation": user.email.upper()}, headers=admin.auth
    )
    assert erased.status_code == 204
    assert await instance.scalar("SELECT count(*) FROM users WHERE id = :u", u=user.id) == 0
    # The log keeps that an account went, not which one.
    row = (
        await instance.sql(
            "SELECT target, details FROM audit_events WHERE action = 'account.deleted' "
            "AND actor_user_id = :a",
            a=admin.id,
        )
    ).one()  # type: ignore[attr-defined]
    assert row.target is None
    assert user.email not in str(row.details) and str(user.id) not in str(row.details)

    gone = await client.request(
        "DELETE", url, json={"email_confirmation": user.email}, headers=admin.auth
    )
    assert gone.status_code == 404


async def test_the_tombstone_is_not_an_account(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row erased accounts' shared records point to: invisible, and out of reach."""
    admin = await instance.account("admin")
    _make_admin(monkeypatch, admin)
    client = instance.client
    tombstone = "00000000-0000-0000-0000-000000000001"
    listed = await client.get("/v1/admin/accounts", headers=admin.auth)
    assert tombstone not in {row["id"] for row in listed.json()}
    suspend = await client.post(f"/v1/admin/accounts/{tombstone}/suspend", headers=admin.auth)
    assert suspend.status_code == 404
    erase = await client.request(
        "DELETE",
        f"/v1/admin/accounts/{tombstone}",
        json={"email_confirmation": "deleted-user@ghostcal.invalid"},
        headers=admin.auth,
    )
    assert erase.status_code == 404
    assert await instance.scalar("SELECT count(*) FROM users WHERE id = :u", u=tombstone) == 1


async def test_the_last_owner_of_a_shared_organization_stays(
    instance: Instance, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await instance.account("admin")
    owner = await instance.account("owner")
    member = await instance.account("member")
    _make_admin(monkeypatch, admin)
    await instance.sql(
        "INSERT INTO memberships (id, organization_id, user_id, role) "
        "SELECT gen_random_uuid(), organization_id, :m, 'member' "
        "FROM memberships WHERE user_id = :o",
        m=member.id,
        o=owner.id,
    )
    refused = await instance.client.request(
        "DELETE",
        f"/v1/admin/accounts/{owner.id}",
        json={"email_confirmation": owner.email},
        headers=admin.auth,
    )
    assert refused.status_code == 409
    assert _code(refused) == "sole_owner"
    assert await instance.scalar("SELECT count(*) FROM users WHERE id = :u", u=owner.id) == 1
