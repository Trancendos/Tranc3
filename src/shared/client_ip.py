"""
Shared client-IP resolution — X-Forwarded-For aware, Traefik-proxy safe.

request.client.host is the direct TCP peer — in the production Docker stack that's
Traefik's own container IP, not the original caller, since Traefik proxies the
connection. Any middleware that blocks or strike-tracks by "client IP" must resolve
it the same way every other one does, or a block set by one check (e.g. the MCP
injection guard) silently never matches what another check (e.g. GovernanceMiddleware's
is_blocked() gate) looks up — see docs/governance/SECURITY-POSTURE-MATRIX.md §6.

Trusting X-Forwarded-For here depends on infra/traefik/traefik.yml *not* setting
entryPoints.*.forwardedHeaders.insecure=true or a trustedIPs allowlist that admits
the public internet — neither is set today, so Traefik's documented default applies:
it discards any X-Forwarded-For the client sent and sets the header itself from the
real connection it observed, rather than trusting or appending to client input. If
that ever changes, this value becomes spoofable and this assumption needs re-checking
against the live Traefik config.
"""

from __future__ import annotations

from typing import Mapping, Optional


def resolve_client_ip(headers: Mapping[str, str], direct_peer: Optional[str]) -> Optional[str]:
    """Best-effort real client IP: X-Forwarded-For's first entry, else the direct peer."""
    forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return direct_peer
