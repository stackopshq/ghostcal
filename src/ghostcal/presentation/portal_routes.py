"""Ghostboard portal integration: the app manifest and the widget ``data_url`` endpoints.

The portal calls these on a user's behalf, forwarding that user's GhostAuth access token. The token
is validated as a resource server (``infrastructure/security/resource_server.py``) — a separate
system from GhostCal's own session bearer, which these routes do not accept and which does not work
here.

**What a zero-knowledge app can put on a dashboard.** Nothing it cannot read. GhostCal's server
holds event titles, task titles and invitee answers as ciphertext sealed to an org key it does not
have, so a "your next meetings" list is not a widget it is choosing not to build — it is one it
*cannot* build, and any design that seems to allow one is a design where the encryption has quietly
stopped being real. What is left is what the server legitimately knows: **times, and therefore
counts**. So these are ``stat`` widgets, and they will stay ``stat`` widgets.

A valid token whose subject has never signed into GhostCal resolves to no local user; the widget
then returns an empty payload and the portal tile quietly removes itself. There is no just-in-time
provisioning here — accounts are made by logging in, not by a background widget fetch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.membership import primary_organization
from ghostcal.infrastructure.db.session import bind_org, db_session
from ghostcal.infrastructure.security.resource_server import (
    ResourceServerNotConfigured,
    TokenValidationError,
    get_ghostauth_validator,
)

router = APIRouter(tags=["portal"])

ENTITLEMENT = "ghostsuite:ghostcal"

_MANIFEST = Path(__file__).with_name("static") / "ghostapp.yaml"


def _claim_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value in (None, ""):
        return []
    return [str(value)]


@dataclass(frozen=True)
class PortalContext:
    subject: str
    user_id: uuid.UUID | None
    organization_id: uuid.UUID | None


async def require_portal_token(request: Request) -> PortalContext:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        validator = get_ghostauth_validator()
    except ResourceServerNotConfigured as exc:
        # No OIDC on this deployment — the portal integration is simply off, not broken.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="portal integration is not configured",
        ) from exc

    try:
        claims = await validator.verify(token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # The entitlement may arrive as an OAuth scope or in the groups claim — the same union that
    # ghostboard itself applies, so an app cannot be reachable through one and not the other.
    entitlements = set(str(claims.get("scope", "")).split()) | set(
        _claim_values(claims.get("groups"))
    )
    if ENTITLEMENT not in entitlements:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not entitled")

    subject = str(claims.get("sub", ""))
    if not subject:
        return PortalContext(subject="", user_id=None, organization_id=None)

    async with db_session() as session:
        user_id = (
            await session.execute(
                select(models.Identity.user_id).where(
                    models.Identity.provider == "oidc",
                    models.Identity.subject == subject,
                )
            )
        ).scalar_one_or_none()
        organization_id = (
            await primary_organization(session, user_id) if user_id is not None else None
        )
    return PortalContext(subject=subject, user_id=user_id, organization_id=organization_id)


PortalToken = Annotated[PortalContext, Depends(require_portal_token)]


@router.get("/.well-known/ghostapp.yaml", response_class=PlainTextResponse)
async def manifest() -> str:
    """The app manifest ghostboard reads. Public, by design — it declares no secret."""
    return _MANIFEST.read_text(encoding="utf-8")


@router.get("/v1/widgets/upcoming")
async def upcoming_widget(portal: PortalToken) -> dict[str, Any]:
    """Stat: how many confirmed meetings the user has ahead of them.

    A count, not a list. The server cannot read what any of them are about.
    """
    if portal.user_id is None or portal.organization_id is None:
        return {"value": "—", "label": "not signed in", "trend": "flat"}

    async with db_session() as session:
        await bind_org(session, portal.organization_id)
        count = (
            await session.execute(
                select(func.count())
                .select_from(models.Booking)
                .where(
                    models.Booking.host_id == portal.user_id,
                    models.Booking.status == "confirmed",
                    models.Booking.start_at > datetime.now(UTC),
                )
            )
        ).scalar_one()
    return {
        "value": count,
        "label": "upcoming meetings",
        "trend": "up" if count else "flat",
    }


@router.get("/v1/widgets/tasks")
async def tasks_widget(portal: PortalToken) -> dict[str, Any]:
    """Stat: how many to-dos are still open. Their titles are sealed; only the count is knowable."""
    if portal.user_id is None or portal.organization_id is None:
        return {"value": "—", "label": "not signed in", "trend": "flat"}

    async with db_session() as session:
        await bind_org(session, portal.organization_id)
        count = (
            await session.execute(
                select(func.count())
                .select_from(models.Task)
                .where(
                    models.Task.owner_id == portal.user_id,
                    models.Task.completed.is_(False),
                )
            )
        ).scalar_one()
    return {
        "value": count,
        "label": "open tasks",
        "trend": "flat",
    }
