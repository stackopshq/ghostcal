"""Tiny Redis JSON cache with a short TTL. Fail-open: cache errors never break a request."""

from __future__ import annotations

import json
import logging

from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from ghostcal.config import get_settings

logger = logging.getLogger("ghostcal.cache")

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = redis_from_url(str(get_settings().redis_url))  # type: ignore[no-untyped-call]
    return _redis


async def get_json(key: str) -> object | None:
    try:
        raw = await _client().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def set_json(key: str, value: object, ttl_seconds: int) -> None:
    try:
        await _client().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        logger.warning("cache set failed for key=%s", key)
