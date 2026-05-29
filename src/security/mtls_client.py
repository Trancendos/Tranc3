"""
mtls_client.py — mTLS-aware HTTP client for inter-service communication
=======================================================================
Wraps httpx with the internal client certificate so any worker can call
another worker via the Traefik :8443 mTLS entry point without exposing
credentials in headers or environment variables.

Usage
-----
    from src.security.mtls_client import get_mtls_client, internal_get, internal_post

    # Sync variant
    resp = internal_get("https://infinity-auth.internal.trancendos.local:8443/health")

    # Async variant
    async with get_async_mtls_client() as client:
        resp = await client.get("https://users-service.internal.trancendos.local:8443/users/me")

Certificate paths are resolved from environment variables (with sensible
defaults for the Docker Compose layout):

    MTLS_CA_CERT      — path to internal CA certificate (default: /etc/traefik/certs/internal-ca.pem)
    MTLS_CLIENT_CERT  — path to this worker's client certificate
    MTLS_CLIENT_KEY   — path to this worker's client private key
    MTLS_VERIFY       — "true" | "false" — disable verification in local dev (default: true)

All environment variables are read once at import time and cached.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("tranc3.security.mtls")

# ---------------------------------------------------------------------------
# Certificate path resolution
# ---------------------------------------------------------------------------

_CERT_DIR = Path(os.getenv("MTLS_CERT_DIR", "/etc/traefik/certs"))

_CA_CERT = Path(os.getenv("MTLS_CA_CERT", str(_CERT_DIR / "internal-ca.pem")))

# Guard against empty env var resolving to Path(".") which is always present
_CLIENT_CERT_STR = os.getenv("MTLS_CLIENT_CERT", "")
_CLIENT_KEY_STR = os.getenv("MTLS_CLIENT_KEY", "")
_CLIENT_CERT: Optional[Path] = Path(_CLIENT_CERT_STR) if _CLIENT_CERT_STR else None
_CLIENT_KEY: Optional[Path] = Path(_CLIENT_KEY_STR) if _CLIENT_KEY_STR else None
_MTLS_VERIFY: bool = os.getenv("MTLS_VERIFY", "true").lower() not in ("false", "0", "no")


def _resolve_client_cert() -> Optional[tuple[str, str]]:
    """Return (cert_path, key_path) if both exist, else None."""
    if _CLIENT_CERT and _CLIENT_KEY and _CLIENT_CERT.exists() and _CLIENT_KEY.exists():
        return str(_CLIENT_CERT), str(_CLIENT_KEY)
    return None


def _resolve_ca() -> Optional[str]:
    """Return CA cert path if it exists, else None."""
    if _CA_CERT.exists():
        return str(_CA_CERT)
    return None


# ---------------------------------------------------------------------------
# Sync client (httpx.Client)
# ---------------------------------------------------------------------------


def get_mtls_client(**kwargs: Any):
    """
    Build a synchronous httpx.Client configured for internal mTLS.

    Falls back gracefully if httpx is unavailable (returns None).
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed — mTLS sync client unavailable")
        return None

    ssl_kwargs = _build_ssl_kwargs()
    return httpx.Client(
        verify=ssl_kwargs.get("verify", _MTLS_VERIFY),
        cert=ssl_kwargs.get("cert"),
        timeout=httpx.Timeout(10.0, connect=5.0),
        **kwargs,
    )


def get_async_mtls_client(**kwargs: Any):
    """
    Build an async httpx.AsyncClient configured for internal mTLS.

    Falls back gracefully if httpx is unavailable (returns None).
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed — mTLS async client unavailable")
        return None

    ssl_kwargs = _build_ssl_kwargs()
    return httpx.AsyncClient(
        verify=ssl_kwargs.get("verify", _MTLS_VERIFY),
        cert=ssl_kwargs.get("cert"),
        timeout=httpx.Timeout(10.0, connect=5.0),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Convenience helpers (sync)
# ---------------------------------------------------------------------------


def internal_get(url: str, **kwargs: Any) -> Any:
    """Perform a GET request to an internal service using mTLS."""
    client = get_mtls_client()
    if client is None:
        raise RuntimeError("httpx is required for mTLS inter-service calls")
    with client:
        return client.get(url, **kwargs)


def internal_post(url: str, **kwargs: Any) -> Any:
    """Perform a POST request to an internal service using mTLS."""
    client = get_mtls_client()
    if client is None:
        raise RuntimeError("httpx is required for mTLS inter-service calls")
    with client:
        return client.post(url, **kwargs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_ssl_kwargs() -> Dict[str, Any]:
    """Build SSL keyword arguments for httpx client construction."""
    kwargs: Dict[str, Any] = {}

    if not _MTLS_VERIFY:
        logger.warning("mTLS certificate verification disabled (MTLS_VERIFY=false)")
        kwargs["verify"] = False
        return kwargs

    ca = _resolve_ca()
    if ca:
        kwargs["verify"] = ca
    else:
        if _MTLS_VERIFY:
            logger.debug("Internal CA cert not found at %s — using system trust store", _CA_CERT)

    cert = _resolve_client_cert()
    if cert:
        kwargs["cert"] = cert
    else:
        logger.debug(
            "No client cert configured (MTLS_CLIENT_CERT / MTLS_CLIENT_KEY) — "
            "mTLS client auth will not be presented"
        )

    return kwargs


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def mtls_status() -> Dict[str, Any]:
    """Return a status dict for health-check / observability use."""
    ca = _resolve_ca()
    cert = _resolve_client_cert()
    return {
        "ca_cert_present": ca is not None,
        "client_cert_present": cert is not None,
        "verify_enabled": _MTLS_VERIFY,
        "ca_cert_path": str(_CA_CERT),
        "client_cert_path": str(_CLIENT_CERT) if _CLIENT_CERT else None,
    }
