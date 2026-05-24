# Dimensional/url_validation.py
# SSRF (Server-Side Request Forgery) prevention utilities.
#
# Validates that outbound HTTP request targets are safe: only HTTPS to
# public, non-reserved hosts.  Blocks requests to private networks,
# link-local addresses, loopback, cloud metadata endpoints, and other
# internal surfaces that an attacker could probe via SSRF.
#
# Usage:
#   from Dimensional.url_validation import validate_webhook_url, SSRFError
#
#   validate_webhook_url(url)          # raises SSRFError if unsafe
#   safe_url = sanitize_and_validate_url(url)  # returns parsed URL or raises

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFError(ValueError):
    """Raised when a URL fails SSRF safety validation."""


# ---------------------------------------------------------------------------
# Private / reserved IP ranges that must never be reached via SSRF
# ---------------------------------------------------------------------------

_PRIVATE_NETWORKS: list[ipaddress._BaseNetwork] = [
    # RFC 1918 — private use
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # RFC 4193 — IPv6 unique-local
    ipaddress.ip_network("fc00::/7"),
    # Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    # Link-local
    ipaddress.ip_network("169.254.0.0/16"),  # cloud metadata (AWS, GCP, Azure)
    ipaddress.ip_network("fe80::/10"),
    # Carrier-grade NAT
    ipaddress.ip_network("100.64.0.0/10"),
    # Benchmarking
    ipaddress.ip_network("198.18.0.0/15"),
    # Documentation
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    # IPv6 documentation
    ipaddress.ip_network("2001:db8::/32"),
    # IETF protocol assignments
    ipaddress.ip_network("192.0.0.0/24"),
    # AS112 direct return
    ipaddress.ip_network("192.31.196.0/24"),
    # Shared address space
    ipaddress.ip_network("100.64.0.0/10"),
    # Multicast
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
    # Reserved
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("0.0.0.0/8"),
]

# Hostnames that are always blocked (cloud metadata, internal services)
_BLOCKED_HOSTNAMES: set[str] = {
    "metadata.google.internal",
    "metadata.google",
    "instance-data",
    "localhost",
    "localhost.localdomain",
}

# Regex to detect hostname patterns that look like internal/metadata endpoints
_BLOCKED_HOSTNAME_PATTERN = re.compile(
    r"(?:^|\.)"
    r"(?:internal|intranet|local|localhost|meta-data|metadata|consul|vault|etcd|kubernetes)"
    r"(?:\.|$)",
    re.IGNORECASE,
)

# Allowed URL schemes for outbound requests
_ALLOWED_SCHEMES: set[str] = {"https"}

# Maximum URL length to prevent buffer-based attacks
_MAX_URL_LENGTH = 2048


def _is_ip_private(ip_str: str) -> bool:
    """Return True if the IP address falls in a private/reserved range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # If we can't parse it, treat as unsafe

    for network in _PRIVATE_NETWORKS:
        if addr in network:
            return True

    return False


def _is_hostname_blocked(hostname: str) -> bool:
    """Return True if the hostname matches blocked internal/metadata patterns."""
    lower = hostname.lower().rstrip(".")

    # Check exact blocked hostnames
    if lower in _BLOCKED_HOSTNAMES:
        return True

    # Check pattern-based blocking (e.g., *.internal, *.local)
    if _BLOCKED_HOSTNAME_PATTERN.search(lower):
        return True

    return False


def validate_url(
    url: str,
    *,
    allowed_schemes: Optional[set[str]] = None,
    blocked_networks: Optional[list[ipaddress._BaseNetwork]] = None,
) -> str:
    """Validate that *url* is safe for server-side outbound HTTP requests.

    This function enforces SSRF protections by:
      1. Requiring HTTPS scheme (prevents cleartext interception)
      2. Blocking private, loopback, link-local, and reserved IP addresses
      3. Blocking known internal/metadata hostnames
      4. Blocking URL-encoded or decimal/octal IP representations
      5. Enforcing maximum URL length

    Args:
        url: The URL to validate.
        allowed_schemes: Override the set of permitted URL schemes.
            Defaults to {"https"}.  Use {"https", "http"} only for
            development/testing — never in production.
        blocked_networks: Additional IP networks to block beyond the
            built-in private/reserved ranges.

    Returns:
        The validated URL string (unchanged).

    Raises:
        SSRFError: If the URL fails any safety check.
    """
    if not url:
        raise SSRFError("URL must not be empty")

    if len(url) > _MAX_URL_LENGTH:
        raise SSRFError(f"URL exceeds maximum length of {_MAX_URL_LENGTH} characters")

    schemes = allowed_schemes or _ALLOWED_SCHEMES

    parsed = urlparse(url)

    # --- Scheme check ---
    if parsed.scheme.lower() not in schemes:
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' is not allowed. Permitted schemes: {sorted(schemes)}"
        )

    # --- Hostname check ---
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL must contain a valid hostname")

    # Block known internal/metadata hostnames
    if _is_hostname_blocked(hostname):
        raise SSRFError(f"Hostname '{hostname}' is blocked (internal/metadata endpoint)")

    # --- IP address checks ---
    # Try to resolve and check if the hostname is a direct IP address.
    # We check the hostname string directly for IP representations (decimal,
    # octal, hex) that resolve to private IPs.
    import socket

    try:
        # socket.getaddrinfo will resolve the hostname to IP addresses.
        # We check ALL resolved addresses (including AAAA records for IPv6).
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        for _family, _type, _proto, _canonname, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            if _is_ip_private(ip_str):
                raise SSRFError(
                    f"URL resolves to private/reserved IP address: {ip_str} (hostname: {hostname})"
                )
    except socket.gaierror:
        # DNS resolution failure — treat as invalid rather than risk
        # a later resolution to an internal IP
        raise SSRFError(
            f"Could not resolve hostname '{hostname}'. "
            "Unresolvable hostnames are rejected to prevent DNS rebinding attacks."
        ) from None

    # Also check additional blocked networks if provided
    if blocked_networks:
        try:
            addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
            for _family, _type, _proto, _canonname, sockaddr in addr_infos:
                ip_str = sockaddr[0]
                addr = ipaddress.ip_address(ip_str)
                for network in blocked_networks:
                    if addr in network:
                        raise SSRFError(f"URL resolves to blocked IP range: {ip_str} in {network}")
        except socket.gaierror:
            pass  # Already handled above

    return url


def validate_webhook_url(url: str) -> str:
    """Validate that *url* is a safe target for webhook dispatch.

    Convenience wrapper around :func:`validate_url` with production
    defaults (HTTPS-only, full private-network blocking).

    Args:
        url: The webhook URL to validate.

    Returns:
        The validated URL string.

    Raises:
        SSRFError: If the URL fails SSRF safety checks.
    """
    return validate_url(url)
