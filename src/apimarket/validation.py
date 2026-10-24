"""Catalogue-only URL screening. Runtime connections require additional DNS/IP pinning,
redirect rejection and egress enforcement; registration NEVER authorises execution.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def validate_external_catalogue_url(value: str) -> None:
    """Reject obviously unsafe public provider URL declarations."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("Invalid provider URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid provider URL") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(ch.isspace() for ch in value)
        or port == 0
    ):
        raise ValueError("External provider URL must be a valid credential-free HTTPS URL")
    host = hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError("Local and internal provider hostnames cannot be registered externally")
    if "." not in host:
        raise ValueError("External provider hostname must be fully qualified")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if not ip.is_global:
        raise ValueError("Non-public provider IP address is forbidden")
