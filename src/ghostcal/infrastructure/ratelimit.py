"""Redis fixed-window rate limiting for public endpoints.

Fail-open: if Redis is unreachable the request is allowed (availability over strictness). Used as
a FastAPI dependency on abuse-prone public routes (booking creation, poll voting).
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from ghostcal.config import get_settings

logger = logging.getLogger("ghostcal.ratelimit")

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

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


@lru_cache(maxsize=1)
def _trusted_networks() -> tuple[IpNetwork, ...]:
    return tuple(
        ipaddress.ip_network(cidr, strict=False) for cidr in get_settings().trusted_proxy_cidrs
    )


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_trusted_proxy(ip: str) -> bool:
    addr = _parse_ip(ip)
    return addr is not None and any(addr in network for network in _trusted_networks())


def _client_ip(request: Request) -> str:
    """The address to rate-limit on: the real client, and never one it can choose for itself.

    Behind the same-origin Next proxy the socket peer is the proxy, so the client is in
    X-Forwarded-For. That header is client-controlled, so it is believed only when the peer is a
    configured proxy — otherwise anyone gets a fresh bucket per request by inventing a header, and
    both the credential-stuffing guard and the Argon2 CPU-DoS guard stop meaning anything.

    Even from a trusted proxy the *leftmost* entry is not the client: a client may send its own
    X-Forwarded-For, and the proxy appends the address it really saw, giving `spoofed, real`. So
    walk from the right and take the first hop that is not itself a proxy.
    """
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    if not _is_trusted_proxy(peer):
        return peer
    hops = [hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",")]
    for hop in reversed(hops):
        # Must parse as an address. An unparseable hop is not "some other client" — it is an
        # arbitrary string the caller chose, and returning it would hand them a bucket key per
        # request, which is the bypass this function exists to close.
        addr = _parse_ip(hop)
        if addr is not None and not _is_trusted_proxy(hop):
            return str(addr)
    return peer


def rate_limit(bucket: str, limit: int, window: int = 60) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency: at most ``limit`` requests per ``window`` seconds per client IP."""

    async def dependency(request: Request) -> None:
        if not await _allow(bucket, _client_ip(request), limit, window):
            raise HTTPException(status_code=429, detail="too many requests, slow down")

    return dependency
