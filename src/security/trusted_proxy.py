# src/security/trusted_proxy.py
"""Trusted-proxy peer verification for Zero Trust client-supplied headers.

Residual gap this closes: X-Device-Posture and X-Client-Country
(src/auth/zero_trust.py's extract_context()) are still simple client-supplied
headers with no attestation or GeoIP behind them — that deeper gap is tracked
separately and is NOT what this module fixes. resolve_mfa_verified_header()
(src/security/middleware.py) closed the equivalent problem for X-MFA-Verified
by deriving it from a signed JWT claim instead of trusting the header; there
is no JWT claim to substitute for device posture or country, so the
next-best defense is restricting *who* is allowed to set them at all.

Every worker and Traefik share one Docker bridge network, tranc3-net
(172.28.0.0/16 — see docker-compose.production.yml's top-level `networks:`
block), with inter-container communication allowed by default. That means a
compromised sibling container can currently call another worker directly,
bypassing Traefik entirely, and simply set
`X-Device-Posture: healthy` / `X-Client-Country: <an allowed country>` to
escalate trust — the same header-spoofing class of bug the MFA fix closed,
just without a JWT to fall back on.

This module restricts those two headers to requests whose immediate TCP peer
is Traefik (the only legitimate ingress into tranc3-net) or an operator-
configured trusted address. Everything else has the headers stripped, which
degrades safely: src/auth/zero_trust.py's evaluate() treats an absent
country/device_posture as "no signal" rather than "trusted" — blocked/
allowed-country checks become no-ops (they already conferred no real
guarantee from an untrusted peer), MFA's `mfa_bypass_for_healthy` no longer
applies, and `healthy_device_routes` denies rather than allows. Fails closed,
not open.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket

logger = logging.getLogger("tranc3.security.trusted_proxy")

_DEVICE_POSTURE_KEYS = ("x-device-posture", "X-Device-Posture")
_CLIENT_COUNTRY_KEYS = ("x-client-country", "X-Client-Country")

_DEFAULT_TRUSTED_HOSTNAMES = "traefik,tranc3-traefik"


def _parse_cidrs(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            networks.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXY_CIDRS: ignoring invalid entry %r", chunk)
    return networks


def _resolve_hostnames(raw: str) -> set[str]:
    """Resolve configured hostnames to their current container IPs.

    Re-resolved on every call rather than cached: Docker container IPs on
    tranc3-net are assigned at container start (no static ipv4_address is
    reserved for Traefik in docker-compose.production.yml), so the address
    behind a given hostname can change across a redeploy/restart.
    """
    resolved: set[str] = set()
    for name in raw.split(","):
        name = name.strip()
        if not name:
            continue
        try:
            resolved.add(socket.gethostbyname(name))
        except OSError:
            # Not resolvable from this container (unit tests, non-Docker
            # dev, or the hostname simply isn't on this network) — not an
            # error, just no match from this candidate.
            continue
    return resolved


def is_trusted_proxy_peer(peer_ip: str | None) -> bool:
    """True if *peer_ip* is Traefik or an explicitly configured trusted peer.

    Fails closed: a missing/unparsable peer_ip, or one that matches neither
    TRUSTED_PROXY_CIDRS nor a resolved TRUSTED_PROXY_HOSTNAMES address, is
    NOT trusted.
    """
    if not peer_ip:
        return False
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False  # e.g. Starlette TestClient's "testclient" placeholder

    cidrs_raw = os.getenv("TRUSTED_PROXY_CIDRS", "")
    if cidrs_raw:
        for network in _parse_cidrs(cidrs_raw):
            if addr in network:
                return True

    hostnames_raw = os.getenv("TRUSTED_PROXY_HOSTNAMES", _DEFAULT_TRUSTED_HOSTNAMES)
    if peer_ip in _resolve_hostnames(hostnames_raw):
        return True

    return False


def sanitize_zero_trust_client_headers(
    headers: dict[str, str], peer_ip: str | None
) -> dict[str, str]:
    """Strip X-Device-Posture / X-Client-Country unless *peer_ip* is trusted.

    Mirrors resolve_mfa_verified_header()'s "never trust the raw client
    value" pattern. An untrusted peer's claimed posture/country becomes
    absent, same as if the header had never been sent — not substituted
    with anything, since there is no signed-claim equivalent to fall back
    on for these two fields.
    """
    if is_trusted_proxy_peer(peer_ip):
        return headers
    sanitized = dict(headers)
    for key in (*_DEVICE_POSTURE_KEYS, *_CLIENT_COUNTRY_KEYS):
        sanitized.pop(key, None)
    return sanitized
