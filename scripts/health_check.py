#!/usr/bin/env python3
"""
Trancendos Platform Health Check
==================================
Probes all services and infrastructure components, reports status.
Run from the repository root: python scripts/health_check.py

Exit codes:
  0 — all critical (P0) services healthy
  1 — one or more P0 services unhealthy
  2 — degraded (P1/P2 issues only, P0 OK)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False
    print("warning: httpx not installed — using urllib fallback", file=sys.stderr)
    import urllib.request
    import urllib.error


TIMEOUT = float(os.environ.get("HEALTH_TIMEOUT", "5"))
BASE = os.environ.get("TRANC3_BASE_URL", "http://localhost")

# Service registry: (name, port, health_path, priority)
SERVICES = [
    # P0 — critical
    ("tranc3-backend",    8000, "/health",  "P0"),
    ("tranc3-ai",         8001, "/health",  "P0"),
    ("api-gateway",       8003, "/health",  "P0"),
    ("infinity-ws",       8004, "/health",  "P0"),
    ("infinity-auth",     8005, "/health",  "P0"),
    # P1 — important
    ("users-service",     8006, "/health",  "P1"),
    ("monitoring",        8007, "/health",  "P1"),
    ("notifications",     8008, "/health",  "P1"),
    ("infinity-ai",       8009, "/health",  "P1"),
    # P2 — standard
    ("the-grid",          8010, "/health",  "P2"),
    ("products-service",  8011, "/health",  "P2"),
    ("orders-service",    8012, "/health",  "P2"),
    ("payments-service",  8013, "/health",  "P2"),
    ("files-service",     8014, "/health",  "P2"),
    ("identity-service",  8015, "/health",  "P2"),
    # Infrastructure
    ("qdrant",            6333, "/healthz", "INF"),
    ("nats",              8222, "/healthz", "INF"),
    ("woodpecker-server", 8100, "/healthz", "INF"),
    # Observability
    ("prometheus",        9090, "/-/healthy", "OBS"),
    ("grafana",           3000, "/api/health", "OBS"),
    ("victoriametrics",   8428, "/health", "OBS"),
    ("langfuse",          3002, "/api/public/health", "OBS"),
    ("signoz-frontend",   3301, "/", "OBS"),
    # Creative
    ("blender-worker",    8050, "/health",  "P3"),
    ("triposr-worker",    8051, "/health",  "P3"),
    ("ffmpeg-worker",     8052, "/health",  "P3"),
]


@dataclass
class ServiceResult:
    name: str
    port: int
    priority: str
    ok: bool
    status_code: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None
    detail: dict = field(default_factory=dict)


async def probe_httpx(name: str, url: str) -> tuple[bool, int, float, Optional[str], dict]:
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url)
            ms = (time.perf_counter() - start) * 1000
            detail: dict = {}
            try:
                detail = r.json()
            except Exception:
                pass
            return r.status_code < 400, r.status_code, ms, None, detail
    except Exception as exc:
        ms = (time.perf_counter() - start) * 1000
        return False, 0, ms, str(exc)[:120], {}


def probe_urllib(url: str) -> tuple[bool, int, float, Optional[str], dict]:
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tranc3-health-check/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ms = (time.perf_counter() - start) * 1000
            body = resp.read().decode("utf-8", errors="replace")
            detail: dict = {}
            try:
                detail = json.loads(body)
            except Exception:
                pass
            return resp.status < 400, resp.status, ms, None, detail
    except urllib.error.HTTPError as exc:
        ms = (time.perf_counter() - start) * 1000
        return exc.code < 400, exc.code, ms, str(exc), {}
    except Exception as exc:
        ms = (time.perf_counter() - start) * 1000
        return False, 0, ms, str(exc)[:120], {}


async def check_service(name: str, port: int, path: str, priority: str) -> ServiceResult:
    url = f"{BASE}:{port}{path}"
    if _HAS_HTTPX:
        ok, code, ms, err, detail = await probe_httpx(name, url)
    else:
        ok, code, ms, err, detail = await asyncio.get_event_loop().run_in_executor(
            None, probe_urllib, url
        )
    return ServiceResult(name=name, port=port, priority=priority,
                         ok=ok, status_code=code, latency_ms=ms,
                         error=err, detail=detail)


async def run_all() -> list[ServiceResult]:
    tasks = [check_service(n, p, h, pri) for n, p, h, pri in SERVICES]
    return await asyncio.gather(*tasks)


_COLORS = {
    "GREEN":  "\033[92m",
    "RED":    "\033[91m",
    "YELLOW": "\033[93m",
    "RESET":  "\033[0m",
    "BOLD":   "\033[1m",
    "DIM":    "\033[2m",
}


def _c(color: str, text: str) -> str:
    if sys.stdout.isatty():
        return f"{_COLORS.get(color, '')}{text}{_COLORS['RESET']}"
    return text


def print_report(results: list[ServiceResult]) -> int:
    print(f"\n{_c('BOLD', '═══ Trancendos Platform Health Check ═══')}")
    print(f"  {_c('DIM', time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))}\n")

    by_priority: dict[str, list[ServiceResult]] = {}
    for r in results:
        by_priority.setdefault(r.priority, []).append(r)

    p0_fail = 0
    p1_fail = 0

    for pri in ["P0", "P1", "P2", "P3", "INF", "OBS"]:
        group = by_priority.get(pri, [])
        if not group:
            continue
        label = {
            "P0": "Critical (P0)",
            "P1": "Important (P1)",
            "P2": "Standard (P2)",
            "P3": "Creative (P3)",
            "INF": "Infrastructure",
            "OBS": "Observability",
        }.get(pri, pri)
        print(f"  {_c('BOLD', label)}")
        for r in group:
            icon = _c("GREEN", "✓") if r.ok else _c("RED", "✗")
            lat = f"{r.latency_ms:5.0f}ms" if r.latency_ms else "      "
            err_str = f"  {_c('DIM', r.error)}" if r.error else ""
            code_str = f" [{r.status_code}]" if r.status_code else " [---]"
            print(f"    {icon} {r.name:<28} {lat}{code_str}{err_str}")
            if not r.ok:
                if pri == "P0":
                    p0_fail += 1
                elif pri == "P1":
                    p1_fail += 1
        print()

    healthy = sum(1 for r in results if r.ok)
    total = len(results)
    print(f"  {_c('BOLD', 'Summary:')} {_c('GREEN', str(healthy))} healthy, "
          f"{_c('RED', str(total - healthy))} unhealthy of {total} services\n")

    if p0_fail > 0:
        print(f"  {_c('RED', f'CRITICAL: {p0_fail} P0 service(s) down')}\n")
        return 1
    if p1_fail > 0:
        print(f"  {_c('YELLOW', f'DEGRADED: {p1_fail} P1 service(s) unhealthy')}\n")
        return 2
    return 0


def main() -> int:
    results = asyncio.run(run_all())

    # JSON output mode
    if "--json" in sys.argv:
        output = [
            {
                "name": r.name, "port": r.port, "priority": r.priority,
                "ok": r.ok, "status_code": r.status_code,
                "latency_ms": round(r.latency_ms, 1),
                "error": r.error,
            }
            for r in results
        ]
        print(json.dumps(output, indent=2))
        p0_failures = sum(1 for r in results if not r.ok and r.priority == "P0")
        return 1 if p0_failures else 0

    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
