"""Host endpoints to manage outbound webhook endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.webhooks import (
    WEBHOOK_EVENTS,
    InvalidWebhook,
    WebhookNotFound,
    create_webhook,
    delete_webhook,
    list_webhooks,
)
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.db.webhooks_repository import SqlWebhookRepository
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import WebhookCreatedOut, WebhookCreateIn, WebhookOut

router = APIRouter(prefix="/v1/me/webhooks", tags=["webhooks"])


@router.get("/events", response_model=list[str])
async def list_event_types() -> list[str]:
    return list(WEBHOOK_EVENTS)


@router.get("", response_model=list[WebhookOut])
async def list_my_webhooks(member: Member = Depends(current_member)) -> list[WebhookOut]:
    async with org_session(member.organization_id) as session:
        endpoints = await list_webhooks(SqlWebhookRepository(session, member.organization_id))
    return [
        WebhookOut(
            id=e.id,
            url=e.url,
            event_types=list(e.event_types),
            active=e.active,
            created_at=e.created_at,
        )
        for e in endpoints
    ]


@router.post("", response_model=WebhookCreatedOut, status_code=201)
async def create_my_webhook(
    payload: WebhookCreateIn, member: Member = Depends(current_member)
) -> WebhookCreatedOut:
    async with org_session(member.organization_id) as session:
        try:
            created = await create_webhook(
                SqlWebhookRepository(session, member.organization_id),
                url=payload.url,
                event_types=tuple(payload.event_types),
            )
        except InvalidWebhook as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WebhookCreatedOut(
        id=created.id,
        url=created.url,
        event_types=list(created.event_types),
        secret=created.secret,
    )


@router.delete("/{endpoint_id}", status_code=204)
async def delete_my_webhook(
    endpoint_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await delete_webhook(SqlWebhookRepository(session, member.organization_id), endpoint_id)
        except WebhookNotFound as exc:
            raise HTTPException(status_code=404, detail="webhook not found") from exc
