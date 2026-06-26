"""Seed a demo organization for local development / manual testing.

Uses the admin (privileged) connection to create one org, a host, a Mon-Fri 09:00-17:00 UTC
schedule and a 30-minute "intro" event type. Prints the org and event-type ids as JSON so they
can be fed to the public API.

    uv run python scripts/dev_seed.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ghostcal.config import get_settings
from ghostcal.infrastructure.db import models

DEMO_SLUG = "ghostcal-demo"
EVENT_SLUG = "intro"


async def main() -> None:
    settings = get_settings()
    admin_url = settings.database_admin_url or settings.database_url
    engine = create_async_engine(str(admin_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        org = (
            await s.execute(
                select(models.Organization).where(models.Organization.slug == DEMO_SLUG)
            )
        ).scalar_one_or_none()
        if org is None:
            org = models.Organization(name="GhostCal Demo", slug=DEMO_SLUG)
            host = models.User(email="demo-host@ghostcal.test", name="Demo Host", timezone="UTC")
            s.add_all([org, host])
            await s.flush()
            schedule = models.AvailabilitySchedule(
                organization_id=org.id, owner_id=host.id, name="Working hours", timezone="UTC"
            )
            s.add(schedule)
            await s.flush()
            s.add_all(
                models.AvailabilityRule(
                    organization_id=org.id,
                    schedule_id=schedule.id,
                    weekday=weekday,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                )
                for weekday in range(5)  # Monday..Friday
            )
            event = models.EventType(
                organization_id=org.id,
                owner_id=host.id,
                slug=EVENT_SLUG,
                title="Intro call",
                duration_min=30,
                slot_interval_min=30,
            )
            s.add(event)
            await s.commit()
        else:
            event = (
                await s.execute(
                    select(models.EventType).where(
                        models.EventType.organization_id == org.id,
                        models.EventType.slug == EVENT_SLUG,
                    )
                )
            ).scalar_one()

        print(json.dumps({"organization_id": str(org.id), "event_type_id": str(event.id)}))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
