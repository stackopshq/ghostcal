"""SSRF guard for server-initiated outbound requests (webhooks, CalDAV).

Before the server connects to any user-supplied URL, validate it: require an http(s) scheme and
resolve the host to its IP addresses, rejecting loopback, link-local (incl. the 169.254.169.254
cloud-metadata address), private/ULA, reserved, multicast and unspecified ranges. Callers must also
disable HTTP redirect-following (or re-validate each hop), since a redirect can otherwise bounce the
request to an internal address after this check.

Calendar fetches may pass ``allowed_private_networks`` to reach a self-hoster's own LAN server —
see ``Settings.calendar_allowed_private_cidrs``. That opens the named ranges and nothing else:
link-local, multicast, reserved and unspecified addresses stay blocked whatever is configured, so
no allow-list can expose the cloud-metadata endpoint. Webhook targets never pass it.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Sequence
from urllib.parse import urlparse

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class BlockedOutboundURL(Exception):
    """The URL is malformed or resolves to a non-public address (SSRF guard)."""


_ALLOWED_SCHEMES = ("http", "https")


def calendar_private_networks() -> tuple[IpNetwork, ...]:
    """The private ranges a self-hoster has opened for calendar fetches (empty by default).

    Read at call time rather than import time: the setting is validated at startup, and binding it
    to a module global would make the guard's behaviour depend on import order.
    """
    from ghostcal.config import get_settings

    return tuple(
        ipaddress.ip_network(cidr, strict=False)
        for cidr in get_settings().calendar_allowed_private_cidrs
    )


def _is_blocked_ip(ip: str, allowed: Sequence[IpNetwork] = ()) -> bool:
    addr = ipaddress.ip_address(ip)
    # An IPv4-mapped IPv6 address (::ffff:127.0.0.1) must be judged on its v4 form, or it would
    # slip past both the range checks and the allow-list.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _is_blocked_ip(str(addr.ipv4_mapped), allowed)

    # Never openable, checked before the allow-list: link-local carries the cloud-metadata
    # address, and the rest cannot host a calendar server anyone means to reach.
    if addr.is_link_local or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
        return True

    # An operator naming a range is a deliberate act; it wins over the blanket private/loopback
    # refusal, and only for the addresses inside it.
    if any(addr in network for network in allowed):
        return False

    return addr.is_private or addr.is_loopback


def assert_public_url(url: str, *, allowed_private_networks: Sequence[IpNetwork] = ()) -> None:
    """Raise ``BlockedOutboundURL`` unless ``url`` is an http(s) URL whose host resolves only to
    public addresses, plus any address inside ``allowed_private_networks``. Call this immediately
    before issuing the request."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise BlockedOutboundURL("url must use http or https")
    host = parsed.hostname
    if not host:
        raise BlockedOutboundURL("url has no host")

    # A bare IP literal: validate it directly (no DNS).
    try:
        ipaddress.ip_address(host)
        if _is_blocked_ip(host, allowed_private_networks):
            raise BlockedOutboundURL(f"host {host} is not a public address")
        return
    except ValueError:
        pass  # not an IP literal — resolve the name below

    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise BlockedOutboundURL(f"could not resolve host {host}") from exc
    if not infos:
        raise BlockedOutboundURL(f"could not resolve host {host}")
    for info in infos:
        ip = str(info[4][0])
        if _is_blocked_ip(ip, allowed_private_networks):
            raise BlockedOutboundURL(f"host {host} resolves to a non-public address")
