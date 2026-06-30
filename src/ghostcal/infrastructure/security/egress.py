"""SSRF guard for server-initiated outbound requests (webhooks, CalDAV).

Before the server connects to any user-supplied URL, validate it: require an http(s) scheme and
resolve the host to its IP addresses, rejecting loopback, link-local (incl. the 169.254.169.254
cloud-metadata address), private/ULA, reserved, multicast and unspecified ranges. Callers must also
disable HTTP redirect-following (or re-validate each hop), since a redirect can otherwise bounce the
request to an internal address after this check.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class BlockedOutboundURL(Exception):
    """The URL is malformed or resolves to a non-public address (SSRF guard)."""


_ALLOWED_SCHEMES = ("http", "https")


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    ):
        return True
    # An IPv4-mapped IPv6 address (::ffff:127.0.0.1) must be checked against the v4 ranges too.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _is_blocked_ip(str(addr.ipv4_mapped))
    return False


def assert_public_url(url: str) -> None:
    """Raise ``BlockedOutboundURL`` unless ``url`` is an http(s) URL whose host resolves only to
    public addresses. Call this immediately before issuing the request."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise BlockedOutboundURL("url must use http or https")
    host = parsed.hostname
    if not host:
        raise BlockedOutboundURL("url has no host")

    # A bare IP literal: validate it directly (no DNS).
    try:
        ipaddress.ip_address(host)
        if _is_blocked_ip(host):
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
        if _is_blocked_ip(ip):
            raise BlockedOutboundURL(f"host {host} resolves to a non-public address")
