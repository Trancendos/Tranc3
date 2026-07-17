#!/usr/bin/env python3
"""Terminal health check for P0/P1 workers (used by make monitor)."""

from __future__ import annotations

import asyncio
import sys

import httpx

WORKERS = [
    ("tranc3-backend", "http://localhost:8000/health"),
    ("tranc3-ai", "http://localhost:8001/health"),
    ("infinity-void", "http://localhost:8002/health"),
    ("api-gateway", "http://localhost:8003/health"),
    ("infinity-ws", "http://localhost:8004/health"),
    ("infinity-auth", "http://localhost:8005/health"),
    ("users-svc", "http://localhost:8006/health"),
    ("monitoring", "http://localhost:8007/health"),
    ("notifications", "http://localhost:8008/health"),
    ("infinity-ai", "http://localhost:8009/health"),
    ("infinity-admin", "http://localhost:8044/health"),
    ("swarm-coordinator-service", "http://localhost:8109/health"),
]


async def check() -> int:
    failures = 0
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, url in WORKERS:
            try:
                response = await client.get(url)
                status = "UP  " if response.status_code == 200 else f"ERR {response.status_code}"
                if response.status_code != 200:
                    failures += 1
            except Exception as exc:
                status = f"DOWN ({type(exc).__name__})"
                failures += 1
            print(f"  {status}  {name} ({url})")
    return failures


def main() -> int:
    print("Monitoring P0/P1 workers...")
    return asyncio.run(check())


if __name__ == "__main__":
    sys.exit(main())
