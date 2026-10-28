"""Bounded, opt-in remote asset ingestion for VRAR3D.

Off by default. Hosts must be explicitly approved by the operator, and network
security groups must also enforce public-only egress to prevent DNS rebinding.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


class AssetIngestError(ValueError):
    """Rejected or unsuccessful asset import (no source content persisted)."""


def validate_asset_url(url: str, allowed_hosts: frozenset[str]) -> str:
    """Validate a public HTTPS source against an exact-name allowlist."""
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise AssetIngestError("Malformed asset URL") from exc
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.netloc
        or "\\" in url
        or any(ord(ch) < 32 for ch in url)
    ):
        raise AssetIngestError(
            "Only HTTPS asset URLs without credentials or custom ports are allowed"
        )
    if hostname not in allowed_hosts:
        raise AssetIngestError("Asset host is not in the configured allowlist")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise AssetIngestError("IP-literal asset hosts are prohibited")
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AssetIngestError("Asset host DNS resolution failed") from exc
    if not addresses:
        raise AssetIngestError("Asset host has no resolved addresses")
    for address in addresses:
        try:
            resolved_ip = ipaddress.ip_address(address[4][0])
        except ValueError as exc:
            raise AssetIngestError("Asset host returned an invalid address") from exc
        if not resolved_ip.is_global:
            raise AssetIngestError("Asset host resolves to a non-public address")
    return url


async def fetch_asset_bytes(
    url: str,
    *,
    allowed_hosts: frozenset[str],
    max_bytes: int = 20 * 1024 * 1024,
    timeout_s: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Download without redirects or proxy environment, rejecting oversized streams.

    DNS preflight is defence in depth, not DNS pinning. Restrict outbound traffic
    at the network layer and only allow trusted operator-managed hostnames.
    """
    validate_asset_url(url, allowed_hosts)
    try:
        async with httpx.AsyncClient(
            verify=True,
            follow_redirects=False,
            trust_env=False,
            timeout=timeout_s,
            transport=transport,
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise AssetIngestError(f"Asset host returned HTTP {response.status_code}")
                length = response.headers.get("content-length")
                if length:
                    try:
                        declared_length = int(length)
                    except ValueError as exc:
                        raise AssetIngestError("Invalid asset content length") from exc
                    if declared_length > max_bytes:
                        raise AssetIngestError("Asset exceeds size limit")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise AssetIngestError("Asset exceeds size limit")
                    chunks.append(chunk)
                if not size:
                    raise AssetIngestError("Asset response was empty")
                return b"".join(chunks)
    except httpx.HTTPError as exc:
        raise AssetIngestError("Asset download failed") from exc
