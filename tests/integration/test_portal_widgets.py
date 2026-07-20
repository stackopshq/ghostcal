"""Ghostboard widget endpoints against a live PostgreSQL.

The token plumbing is covered in ``tests/security/test_resource_server.py``; here the dependency is
overridden so what is exercised is what the widgets actually *say* — which, for a zero-knowledge
app, is the interesting part: counts, and never a title.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import yaml
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db import models
from ghostcal.presentation.api import create_app
from ghostcal.presentation.portal_routes import PortalContext, require_portal_token

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
SECRET_TITLE = "Oncologist appointment"


@dataclass
class Fixture:
    org: uuid.UUID
    user: uuid.UUID


@pytest_asyncio.fixture
async def org_with_activity(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """A user with two upcoming meetings, one past one, and two open tasks (plus one done)."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"pw-{suffix}")
        user = models.User(email=f"pw-{suffix}@example.com", name="Host", timezone="UTC")
        s.add_all([org, user])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        event_type = models.EventType(
            organization_id=org.id,
            owner_id=user.id,
            slug=f"intro-{suffix}",
            title="Intro",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event_type)
        await s.flush()

        for offset, status in ((2, "confirmed"), (5, "confirmed"), (-3, "confirmed")):
            start = NOW + timedelta(days=offset)
            s.add(
                models.Booking(
                    organization_id=org.id,
                    event_type_id=event_type.id,
                    host_id=user.id,
                    invitee_email="invitee@example.com",
                    invitee_timezone="UTC",
                    start_at=start,
                    end_at=start + timedelta(minutes=30),
                    status=status,
                )
            )
        # A cancelled meeting in the future is not an upcoming meeting.
        cancelled_start = NOW + timedelta(days=3)
        s.add(
            models.Booking(
                organization_id=org.id,
                event_type_id=event_type.id,
                host_id=user.id,
                invitee_email="invitee@example.com",
                invitee_timezone="UTC",
                start_at=cancelled_start,
                end_at=cancelled_start + timedelta(minutes=30),
                status="cancelled",
            )
        )
        s.add_all(
            [
                models.Task(organization_id=org.id, owner_id=user.id, content="sealed-1"),
                models.Task(organization_id=org.id, owner_id=user.id, content="sealed-2"),
                models.Task(
                    organization_id=org.id,
                    owner_id=user.id,
                    content="sealed-3",
                    completed=True,
                    completed_at=NOW,
                ),
            ]
        )
        await s.commit()
        fixture = Fixture(org=org.id, user=user.id)
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM bookings WHERE organization_id = :o"), {"o": org.id})
            await s.execute(
                text("DELETE FROM event_types WHERE organization_id = :o"), {"o": org.id}
            )
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org.id})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": fixture.user})
            await s.commit()


def _client(context: PortalContext) -> AsyncClient:
    """The widgets hit the database, so they must run on the *test's* event loop — the cached async
    engine is bound to it. TestClient spins up a loop of its own, which is a different one."""
    app = create_app()
    app.dependency_overrides[require_portal_token] = lambda: context
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_widgets_report_counts_and_nothing_else(org_with_activity: Fixture) -> None:
    async with _client(
        PortalContext(
            subject="sub-1",
            user_id=org_with_activity.user,
            organization_id=org_with_activity.org,
        )
    ) as client:
        upcoming = (await client.get("/v1/widgets/upcoming")).json()
        tasks = (await client.get("/v1/widgets/tasks")).json()

    assert upcoming["value"] == 2  # the past one and the cancelled one are not upcoming
    assert upcoming["label"] == "upcoming meetings"
    assert tasks["value"] == 2  # the completed one is not open

    # The zero-knowledge invariant, at the wire: a stat carries a number and a label, and there is
    # nowhere in it for a title to hide — which is exactly why this app serves stats and not lists.
    for payload in (upcoming, tasks):
        assert set(payload) <= {"value", "label", "delta", "trend"}
        assert SECRET_TITLE not in str(payload)


async def test_a_subject_who_never_signed_in_gets_an_empty_tile(org_with_activity: Fixture) -> None:
    """No just-in-time provisioning: an unknown subject is not an account, it is a blank tile."""
    async with _client(
        PortalContext(subject="stranger", user_id=None, organization_id=None)
    ) as client:
        for path in ("/v1/widgets/upcoming", "/v1/widgets/tasks"):
            payload = (await client.get(path)).json()
            assert payload["value"] == "—"
            assert payload["trend"] == "flat"


def test_the_manifest_is_public_and_served_verbatim() -> None:
    """ghostboard fetches this without a token — it must, to discover the app in the first place."""
    with TestClient(create_app()) as client:
        response = client.get("/.well-known/ghostapp.yaml")

    assert response.status_code == 200
    body = response.text
    assert "id: ghostcal" in body
    assert "ghostsuite:ghostcal" in body
    assert "kind: list" not in body  # a zero-knowledge app has no titles to list


def test_the_manifest_only_declares_paths_the_app_serves() -> None:
    """The manifest is a contract with the portal, and nothing was checking it against reality.

    It declared `health_endpoint: /healthz`, which this app has never served (it serves `/health`
    and `/readyz`). Nothing broke, because ghostboard reads that field and does not call it — a
    promise that happens to go unaudited. The widget `data_url`s carry the same risk, and those the
    portal really does fetch.

    Declared paths are frontend-origin paths: the Next rewrite `/api/:path*` -> backend `/:path*`
    is what puts them in front of this app, so strip that prefix before matching.
    """
    app = create_app()
    with TestClient(app) as client:
        manifest = yaml.safe_load(client.get("/.well-known/ghostapp.yaml").text)

    # Read the paths from the OpenAPI schema, not `app.routes`: included routers appear there
    # unflattened, with no `path` at all, so walking `app.routes` silently finds nothing.
    routes = set(app.openapi()["paths"])
    declared = [manifest["spec"]["health_endpoint"]]
    declared += [widget["data_url"] for widget in manifest["spec"]["widgets"]]

    for path in declared:
        assert path.startswith("/api/"), f"{path} is not reachable through the frontend rewrite"
        served = path.removeprefix("/api")
        assert served in routes, f"manifest declares {path}, which nothing serves"


def test_widgets_refuse_a_request_with_no_token() -> None:
    """The portal endpoints take a GhostAuth token — GhostCal's own session bearer is not one."""
    with TestClient(create_app()) as client:
        response = client.get("/v1/widgets/upcoming")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
