"""
Shared client-IP resolution — X-Forwarded-For aware, Traefik-proxy safe.

request.client.host is the direct TCP peer — in the production Docker stack that's
Traefik's own container IP, not the original caller, since Traefik proxies the
connection. Any middleware that blocks or strike-tracks by "client IP" must resolve
it the same way every other one does, or a block set by one check (e.g. the MCP
injection guard) silently never matches what another check (e.g. GovernanceMiddleware's
is_blocked() gate) looks up — see docs/governance/SECURITY-POSTURE-MATRIX.md §6.

X-Forwarded-For is only trusted when the direct TCP peer is itself a private/loopback
address (Docker bridge networks are always RFC 1918 space, whatever subnet is actually
assigned). A caller reaching this service directly — bypassing Traefik entirely, e.g.
because a port was exposed without the proxy in front of it, or because the caller is
untrusted infrastructure inside the same network — would show up as a non-private peer
address in the normal case, or at minimum isn't the proxy hop this trust model assumes;
either way its self-reported X-Forwarded-For is not honoured, so it cannot frame an
arbitrary victim IP for a Cryptex block by simply setting the header (CodeRabbit-flagged,
Tranc3#493). This is a heuristic, not a proxy identity check — it does not defend against
a peer that is itself inside the trusted private network (e.g. a compromised sibling
container); a real fix for that class needs an explicit trusted-proxy allowlist wired to
the actual Docker network topology, which isn't configured today. See
docs/governance/SECURITY-POSTURE-MATRIX.md §6 for the fuller trace.

Separately, trusting X-Forwarded-For's *value* (once the peer itself is trusted) depends
on infra/traefik/traefik.yml *not* setting entryPoints.*.forwardedHeaders.insecure=true or
a trustedIPs allowlist that admits the public internet — neither is set today, so
Traefik's documented default applies: it discards any X-Forwarded-For the client sent and
sets the header itself from the real connection it observed.
"""

from __future__ import annotations

import ipaddress
from typing import Mapping, Optional


def _is_private_or_loopback(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback


def resolve_client_ip(headers: Mapping[str, str], direct_peer: Optional[str]) -> Optional[str]:
    """
    Best-effort real client IP: X-Forwarded-For's first entry when the direct peer is a
    trusted (private/loopback) address, else the direct peer itself.
    """
    if direct_peer and not _is_private_or_loopback(direct_peer):
        return direct_peer
    forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return direct_peer
