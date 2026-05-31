#!/usr/bin/env python3
"""Wait until P0/P1 services respond on /health (used by deploy-live)."""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_SERVICES = [
    ("tranc3-backend", 8000),
    ("tranc3-ai", 8001),
    ("infinity-void", 8002),
    ("api-gateway", 8003),
    ("infinity-ws", 8004),
    ("infinity-auth", 8005),
    ("users-service", 8006),
    ("monitoring", 8007),
    ("notifications", 8008),
    ("infinity-ai", 8009),
    ("products-service", 8011),
    ("orders-service", 8012),
    ("payments-service", 8013),
    ("infinity-admin", 8044),
    ("swarm-coordinator", 8053),
]


def _probe(base: str, port: int, timeout: float) -> bool:
    url = f"{base}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 300
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=600, help="Max seconds to wait")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--base", default=os.environ.get("TRANC3_BASE_URL", "http://127.0.0.1"))
    args = parser.parse_args()

    pending = list(DEFAULT_SERVICES)
    deadline = time.time() + args.timeout
    while pending and time.time() < deadline:
        still: list[tuple[str, int]] = []
        for name, port in pending:
            if _probe(args.base, port, timeout=3.0):
                print(f"  UP   {name}:{port}")
            else:
                still.append((name, port))
        pending = still
        if pending:
            print(f"Waiting on {len(pending)} services...")
            time.sleep(args.interval)

    if pending:
        print("TIMEOUT — still down:", file=sys.stderr)
        for name, port in pending:
            print(f"  {name} http://127.0.0.1:{port}/health", file=sys.stderr)
        return 1

    print("All core services healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
