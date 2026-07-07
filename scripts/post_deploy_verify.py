#!/usr/bin/env python3
"""Post-deploy verification — hits every Trancendos entity /health endpoint.

Covers all 43 platform entities across P0–P3 tiers + optional services.
Adaptive retry with exponential backoff. Hard-stop threshold: if >20 % of
P0/P1 workers are unhealthy after retries, exits 1 (blocks CI/deploy pipeline).
Reports to The Observatory audit log if reachable.

Usage:
    python scripts/post_deploy_verify.py [--base http://host] [--tier P0]
    python scripts/post_deploy_verify.py --all --report logs/deploy_verify.json
    python scripts/post_deploy_verify.py --soft   # warnings only, always exit 0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Entity registry — all 43 platform entities with health endpoint + tier
# ---------------------------------------------------------------------------

ALL_ENTITIES: list[dict] = [
    # ── Core / always-on ────────────────────────────────────────────────────
    {"name": "tranc3-backend", "port": 8000, "tier": "core", "path": "/health"},
    {"name": "nanoservices", "port": 8001, "tier": "core", "path": "/health"},
    # ── P0 ──────────────────────────────────────────────────────────────────
    {"name": "infinity-ws", "port": 8004, "tier": "P0", "path": "/health"},
    {"name": "infinity-auth", "port": 8005, "tier": "P0", "path": "/health"},
    # ── P1 ──────────────────────────────────────────────────────────────────
    {"name": "infinity-portal-service", "port": 8042, "tier": "P1", "path": "/health"},
    {"name": "infinity-one-service", "port": 8043, "tier": "P1", "path": "/health"},
    {"name": "infinity-admin-service", "port": 8044, "tier": "P1", "path": "/health"},
    {"name": "infinity-shards-service", "port": 8045, "tier": "P1", "path": "/health"},
    {"name": "infinity-bridge-service", "port": 8070, "tier": "P1", "path": "/health"},
    {"name": "cranbania", "port": 8071, "tier": "P1", "path": "/health"},
    {"name": "users-service", "port": 8006, "tier": "P1", "path": "/health"},
    {"name": "monitoring", "port": 8007, "tier": "P1", "path": "/health"},
    {"name": "notifications", "port": 8008, "tier": "P1", "path": "/health"},
    {"name": "infinity-ai", "port": 8009, "tier": "P1", "path": "/health"},
    # ── P2 ──────────────────────────────────────────────────────────────────
    {"name": "the-grid", "port": 8010, "tier": "P2", "path": "/health"},
    {"name": "products-service", "port": 8011, "tier": "P2", "path": "/health"},
    {"name": "orders-service", "port": 8012, "tier": "P2", "path": "/health"},
    {"name": "payments-service", "port": 8013, "tier": "P2", "path": "/health"},
    {"name": "files-service", "port": 8014, "tier": "P2", "path": "/health"},
    {"name": "identity-service", "port": 8015, "tier": "P2", "path": "/health"},
    # ── P3 ──────────────────────────────────────────────────────────────────
    {"name": "analytics-service", "port": 8016, "tier": "P3", "path": "/health"},
    {"name": "audit-service", "port": 8017, "tier": "P3", "path": "/health"},
    {"name": "cache-service", "port": 8018, "tier": "P3", "path": "/health"},
    {"name": "cdn-service", "port": 8019, "tier": "P3", "path": "/health"},
    {"name": "config-service", "port": 8020, "tier": "P3", "path": "/health"},
    {"name": "cron-service", "port": 8021, "tier": "P3", "path": "/health"},
    {"name": "email-service", "port": 8022, "tier": "P3", "path": "/health"},
    {"name": "geo-service", "port": 8023, "tier": "P3", "path": "/health"},
    {"name": "search-service", "port": 8024, "tier": "P3", "path": "/health"},
    {"name": "sms-service", "port": 8025, "tier": "P3", "path": "/health"},
    {"name": "storage-service", "port": 8026, "tier": "P3", "path": "/health"},
    {"name": "queue-service", "port": 8027, "tier": "P3", "path": "/health"},
    {"name": "rate-limit-service", "port": 8028, "tier": "P3", "path": "/health"},
    {"name": "health-aggregator", "port": 8029, "tier": "P3", "path": "/health"},
    {"name": "gbrain-bridge", "port": 8030, "tier": "P3", "path": "/health"},
    {"name": "topology-service", "port": 8031, "tier": "P3", "path": "/health"},
    {"name": "ledger-service", "port": 8032, "tier": "P3", "path": "/health"},
    {"name": "model-router-service", "port": 8033, "tier": "P3", "path": "/health"},
    {"name": "workflow-engine-service", "port": 8034, "tier": "P3", "path": "/health"},
    {"name": "skills-benchmark-service", "port": 8035, "tier": "P3", "path": "/health"},
    {"name": "langchain-integration", "port": 8036, "tier": "P3", "path": "/health"},
    {"name": "deepagents-orchestrator", "port": 8037, "tier": "P3", "path": "/health"},
    {"name": "vault-service", "port": 8038, "tier": "P3", "path": "/health"},
    {"name": "optional-services-health", "port": 8039, "tier": "P3", "path": "/health"},
    # ── Planned entities (18) ───────────────────────────────────────────────
    {"name": "the-academy", "port": 8040, "tier": "planned", "path": "/health"},
    {"name": "basement", "port": 8041, "tier": "planned", "path": "/health"},
    {"name": "the-studio", "port": 8050, "tier": "planned", "path": "/health"},
    {"name": "sashas-photo-studio", "port": 8051, "tier": "planned", "path": "/health"},
    {"name": "tranceflow", "port": 8059, "tier": "planned", "path": "/health"},
    {"name": "tateking", "port": 8053, "tier": "planned", "path": "/health"},
    {"name": "imaginarium", "port": 8054, "tier": "planned", "path": "/health"},
    {"name": "the-lab", "port": 8055, "tier": "planned", "path": "/health"},
    {"name": "warp-tunnel", "port": 8056, "tier": "planned", "path": "/health"},
    {"name": "warp-radio", "port": 8057, "tier": "planned", "path": "/health"},
    {"name": "the-dutchy", "port": 8058, "tier": "planned", "path": "/health"},
    {"name": "devocity", "port": 8059, "tier": "planned", "path": "/health"},
    {"name": "tranquility", "port": 8060, "tier": "planned", "path": "/health"},
    {"name": "imind", "port": 8061, "tier": "planned", "path": "/health"},
    {"name": "taimra", "port": 8062, "tier": "planned", "path": "/health"},
    {"name": "vrar3d", "port": 8063, "tier": "planned", "path": "/health"},
    {"name": "resonate", "port": 8064, "tier": "planned", "path": "/health"},
    {"name": "chaos-party", "port": 8065, "tier": "planned", "path": "/health"},
]

CRITICAL_TIERS = {"core", "P0", "P1"}
HARD_STOP_THRESHOLD = 0.80  # ≥80 % of core+P0+P1 must pass or exit 1


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class EntityResult:
    name: str
    port: int
    tier: str
    status: str  # "healthy" | "degraded" | "unreachable"
    http_code: int = 0
    latency_ms: int = 0
    error: str = ""
    attempts: int = 0


@dataclass
class VerifyReport:
    timestamp: float = field(default_factory=time.time)
    base_url: str = "http://127.0.0.1"
    results: list[EntityResult] = field(default_factory=list)
    overall: str = "unknown"
    critical_pass_rate: float = 0.0
    total_pass_rate: float = 0.0
    duration_s: float = 0.0


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def _probe(base: str, entity: dict, timeout: float = 5.0) -> tuple[str, int, int]:
    """Return (status, http_code, latency_ms)."""
    url = f"{base}:{entity['port']}{entity['path']}"
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "tranc3-deploy-verify/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = int((time.monotonic() - t0) * 1000)
            if resp.status < 300:
                return "healthy", resp.status, latency
            return "degraded", resp.status, latency
    except urllib.error.HTTPError as exc:
        latency = int((time.monotonic() - t0) * 1000)
        status = "degraded" if exc.code < 500 else "unhealthy"
        return status, exc.code, latency
    except Exception:  # noqa: BLE001
        latency = int((time.monotonic() - t0) * 1000)
        return "unreachable", 0, latency


def probe_with_retry(
    base: str,
    entity: dict,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    timeout: float = 5.0,
) -> EntityResult:
    last_status, last_code, last_latency = "unreachable", 0, 0
    for attempt in range(1, max_attempts + 1):
        last_status, last_code, last_latency = _probe(base, entity, timeout)
        if last_status == "healthy":
            return EntityResult(
                name=entity["name"],
                port=entity["port"],
                tier=entity["tier"],
                status="healthy",
                http_code=last_code,
                latency_ms=last_latency,
                attempts=attempt,
            )
        if attempt < max_attempts:
            time.sleep(backoff_base ** (attempt - 1))
    return EntityResult(
        name=entity["name"],
        port=entity["port"],
        tier=entity["tier"],
        status=last_status,
        http_code=last_code,
        latency_ms=last_latency,
        attempts=max_attempts,
    )


# ---------------------------------------------------------------------------
# Observatory reporting
# ---------------------------------------------------------------------------


def _report_to_observatory(base: str, report: VerifyReport) -> None:
    try:
        payload = json.dumps(
            {
                "source": "post-deploy-verify",
                "event": "deployment_verified",
                "overall": report.overall,
                "critical_pass_rate": report.critical_pass_rate,
                "total_pass_rate": report.total_pass_rate,
                "duration_s": report.duration_s,
                "timestamp": report.timestamp,
            }
        ).encode()
        req = urllib.request.Request(
            f"{base}:8007/events",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3.0)
    except Exception:
        pass  # Observatory may not be running — non-fatal


# ---------------------------------------------------------------------------
# Scorecard rendering
# ---------------------------------------------------------------------------

_TICK = "✓"
_CROSS = "✗"
_WARN = "~"

_TIER_ORDER = ["core", "P0", "P1", "P2", "P3", "planned"]
_TIER_COLOUR = {
    "core": "\033[96m",  # cyan
    "P0": "\033[91m",  # red
    "P1": "\033[93m",  # yellow
    "P2": "\033[94m",  # blue
    "P3": "\033[37m",  # light grey
    "planned": "\033[35m",  # magenta
}
_RESET = "\033[0m"
_GREEN = "\033[92m"
_RED = "\033[91m"


def _icon(r: EntityResult) -> str:
    if r.status == "healthy":
        return f"{_GREEN}{_TICK}{_RESET}"
    if r.status == "degraded":
        return f"\033[93m{_WARN}{_RESET}"
    return f"{_RED}{_CROSS}{_RESET}"


def print_scorecard(report: VerifyReport) -> None:
    by_tier: dict[str, list[EntityResult]] = {}
    for r in report.results:
        by_tier.setdefault(r.tier, []).append(r)

    print()
    print("═" * 70)
    print("  Trancendos Post-Deploy Verification Scorecard")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(report.timestamp))}")
    print("═" * 70)
    for tier in _TIER_ORDER:
        entities = by_tier.get(tier, [])
        if not entities:
            continue
        colour = _TIER_COLOUR.get(tier, "")
        healthy = sum(1 for e in entities if e.status == "healthy")
        print(f"\n  {colour}[{tier}]{_RESET}  {healthy}/{len(entities)} healthy")
        for r in sorted(entities, key=lambda x: x.port):
            icon = _icon(r)
            detail = f"{r.http_code}" if r.http_code else r.error[:30] if r.error else "no response"
            print(f"    {icon}  {r.name:<35} :{r.port}  {r.latency_ms:>5}ms  {detail}")

    print()
    cr_pct = int(report.critical_pass_rate * 100)
    tt_pct = int(report.total_pass_rate * 100)
    overall_colour = _GREEN if report.overall == "healthy" else _RED
    print(
        f"  Critical (core+P0+P1): {cr_pct}%   Total: {tt_pct}%   Duration: {report.duration_s:.1f}s"
    )
    print(f"  Overall: {overall_colour}{report.overall.upper()}{_RESET}")
    print("═" * 70)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy health verifier")
    parser.add_argument(
        "--base",
        default=os.environ.get("TRANC3_BASE_URL", "http://127.0.0.1"),
        help="Base URL of the host (default: http://127.0.0.1)",
    )
    parser.add_argument(
        "--tier",
        choices=["core", "P0", "P1", "P2", "P3", "planned", "all"],
        default="all",
        help="Filter to a single tier",
    )
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--report", default="", help="Write JSON report to this path")
    parser.add_argument(
        "--soft", action="store_true", help="Always exit 0 (warning-only mode, never blocks deploy)"
    )
    parser.add_argument("--no-observatory", action="store_true", help="Skip Observatory reporting")
    args = parser.parse_args()

    entities = (
        ALL_ENTITIES if args.tier == "all" else [e for e in ALL_ENTITIES if e["tier"] == args.tier]
    )

    print(f"\nProbing {len(entities)} entities against {args.base} …")
    t_start = time.monotonic()

    results: list[EntityResult] = []
    for entity in entities:
        r = probe_with_retry(args.base, entity, args.retries, timeout=args.timeout)
        results.append(r)
        icon = _icon(r)
        print(f"  {icon}  {r.name:<35} {r.status}")

    duration = time.monotonic() - t_start

    critical = [r for r in results if r.tier in CRITICAL_TIERS]
    critical_healthy = sum(1 for r in critical if r.status == "healthy")
    cr_rate = critical_healthy / len(critical) if critical else 1.0

    total_healthy = sum(1 for r in results if r.status == "healthy")
    tt_rate = total_healthy / len(results) if results else 1.0

    overall = "healthy" if cr_rate >= HARD_STOP_THRESHOLD else "degraded"

    report = VerifyReport(
        base_url=args.base,
        results=results,
        overall=overall,
        critical_pass_rate=cr_rate,
        total_pass_rate=tt_rate,
        duration_s=round(duration, 2),
    )

    print_scorecard(report)

    if not args.no_observatory:
        _report_to_observatory(args.base, report)

    # Write JSON report
    out_path = args.report or str(LOGS / "deploy_verify.json")
    Path(out_path).write_text(
        json.dumps(
            {
                "timestamp": report.timestamp,
                "base_url": report.base_url,
                "overall": report.overall,
                "critical_pass_rate": report.critical_pass_rate,
                "total_pass_rate": report.total_pass_rate,
                "duration_s": report.duration_s,
                "results": [asdict(r) for r in report.results],
            },
            indent=2,
        )
    )
    print(f"  Report saved → {out_path}\n")

    if args.soft:
        return 0

    # Hard stop: exit 1 if critical tier pass rate is below threshold
    if overall != "healthy":
        print(
            f"  HARD STOP: critical pass rate {int(cr_rate * 100)}% "
            f"< {int(HARD_STOP_THRESHOLD * 100)}% threshold",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
