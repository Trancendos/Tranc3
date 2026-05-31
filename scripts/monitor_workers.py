#!/usr/bin/env python3
"""Check health endpoints for core platform workers."""

from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import urlopen

WORKERS = [
    ("infinity-ws", "http://localhost:8004/health"),
    ("infinity-auth", "http://localhost:8005/health"),
    ("users-svc", "http://localhost:8006/health"),
    ("monitoring", "http://localhost:8007/health"),
    ("notifications", "http://localhost:8008/health"),
    ("infinity-ai", "http://localhost:8009/health"),
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
