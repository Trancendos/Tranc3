#!/usr/bin/env python3
"""Check health endpoints for core platform workers."""

from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import urlopen

WORKERS = [
    ("tranc3-backend", "http://localhost:8000/health"),
    ("nanoservices", "http://localhost:8001/health"),
    ("infinity-ws", "http://localhost:8004/health"),
    ("infinity-auth", "http://localhost:8005/health"),
    ("users-service", "http://localhost:8006/health"),
    ("monitoring", "http://localhost:8007/health"),
    ("notifications", "http://localhost:8008/health"),
    ("infinity-ai", "http://localhost:8009/health"),
    ("the-grid", "http://localhost:8010/health"),
    ("products-service", "http://localhost:8011/health"),
    ("orders-service", "http://localhost:8012/health"),
    ("payments-service", "http://localhost:8013/health"),
    ("files-service", "http://localhost:8014/health"),
    ("identity-service", "http://localhost:8015/health"),
    ("infinity-portal-service", "http://localhost:8042/health"),
    ("infinity-one-service", "http://localhost:8043/health"),
    ("infinity-admin-service", "http://localhost:8044/health"),
    ("infinity-shards-service", "http://localhost:8045/health"),
    ("infinity-bridge-service", "http://localhost:8070/health"),
    ("cranbania", "http://localhost:8071/health"),
]


def check_workers() -> None:
    """Print one-line health status for each worker endpoint."""
    for name, url in WORKERS:
        try:
            with urlopen(url, timeout=2.0) as response:  # nosec B310
                status_code = response.getcode()
            status = "UP  " if status_code == 200 else f"ERR {status_code}"
        except HTTPError as exc:
            status = f"ERR {exc.code}"
        except Exception as exc:  # noqa: BLE001
            status = f"DOWN ({type(exc).__name__})"
        print(f"  {status}  {name} ({url})")


def main() -> None:
    check_workers()


if __name__ == "__main__":
    main()
