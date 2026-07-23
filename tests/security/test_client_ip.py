"""Which address the rate limiter counts against (no DB, no Redis).

The limiter is only as good as its identifier. If a client can choose it, the auth limiter — whose
job is to stop credential stuffing and to cap Argon2 CPU burn — becomes decoration, because every
request lands in a fresh bucket. These tests pin the rule that stops that.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ghostcal.infrastructure.ratelimit import _client_ip, _trusted_networks


@dataclass
class _Client:
    host: str


class _Request:
    """Enough of a Starlette request for `_client_ip`: a peer address and headers."""

    def __init__(self, peer: str | None, forwarded: str | None = None) -> None:
        self.client = _Client(peer) if peer else None
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _trusted_networks.cache_clear()


def test_a_direct_client_cannot_choose_its_own_bucket() -> None:
    # The peer is a public address, so it is not a proxy and its header is worth nothing.
    request = _Request("203.0.113.9", forwarded="1.2.3.4")
    assert _client_ip(request) == "203.0.113.9"


def test_a_trusted_proxy_is_believed() -> None:
    # The normal topology: the Next proxy connects from a private address and reports the client.
    request = _Request("172.17.0.5", forwarded="203.0.113.9")
    assert _client_ip(request) == "203.0.113.9"


def test_a_client_cannot_prepend_a_forged_hop_through_a_trusted_proxy() -> None:
    # A client may send its own X-Forwarded-For; the proxy appends what it actually saw. Reading
    # left-to-right would take the value the *client* chose, which is the bypass this guards.
    request = _Request("172.17.0.5", forwarded="1.2.3.4, 203.0.113.9")
    assert _client_ip(request) == "203.0.113.9"


def test_a_chain_of_proxies_resolves_to_the_last_real_client() -> None:
    request = _Request("127.0.0.1", forwarded="203.0.113.9, 10.0.0.7, 172.17.0.5")
    assert _client_ip(request) == "203.0.113.9"


def test_garbage_in_the_header_falls_back_to_the_peer() -> None:
    for junk in ("not-an-ip", "", "   ,  "):
        assert _client_ip(_Request("127.0.0.1", forwarded=junk)) == "127.0.0.1"


def test_no_peer_at_all_is_a_single_shared_bucket() -> None:
    # Better one shared bucket than a per-request one: unknown must not become a bypass.
    assert _client_ip(_Request(None, forwarded="1.2.3.4")) == "unknown"
