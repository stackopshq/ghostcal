"""Redis fixed-window rate limiting for public endpoints.

Fail-open: if Redis is unreachable the request is allowed (availability over strictness). Used as
a FastAPI dependency on abuse-prone public routes (booking creation, poll voting).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from ghostcal.config import get_settings

logger = logging.getLogger("ghostcal.ratelimit")

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = redis_from_url(str(get_settings().redis_url))  # type: ignore[no-untyped-call]
    return _redis


async def _allow(bucket: str, identifier: str, limit: int, window: int) -> bool:
    try:
        window_id = int(time.time()) // window
        key = f"rl:{bucket}:{identifier}:{window_id}"
        count: int = await _client().incr(key)
        if count == 1:
            await _client().expire(key, window)
        return count <= limit
    except Exception:
        logger.warning("rate-limit check failed (allowing) for bucket=%s", bucket)
        return True


def _client_ip(request: Request) -> str:
    # Behind the same-origin Next proxy the socket peer is the proxy, so honour the first hop in
    # X-Forwarded-For (the original client) when present; otherwise fall back to the socket peer.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit: int, window: int = 60) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency: at most ``limit`` requests per ``window`` seconds per client IP."""

    async def dependency(request: Request) -> None:
        if not await _allow(bucket, _client_ip(request), limit, window):
            raise HTTPException(status_code=429, detail="too many requests, slow down")

    return dependency
