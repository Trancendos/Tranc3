#!/usr/bin/env python3
"""Read-only, stdlib-only Arcadia source-boundary audit.

This is a source evidence inventory, not a runtime health check or a security
scanner. It never makes network requests, loads service modules, or reads .env.
The source heuristics intentionally report potential risks for human review.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SERVICE_PATHS = {
    "exchange": "workers/orders-service/worker.py",
    "bank": "workers/payments-service/worker.py",
    "catalogue": "workers/products-service/worker.py",
}
PORT_RE = re.compile(r'WORKER_PORT\s*=\s*int\(os\.(?:getenv|environ\.get)\(["\']PORT["\']\)\s*or\s*["\'](\d+)["\']\)')
MONEY_FLOAT_RE = re.compile(
    r'\b(?:amount|balance|price_per_unit|total_price|initial_balance)\s*:\s*float\b'
    r'|\b(?:balance|total_price|price_per_unit|amount)\s+REAL\b', re.IGNORECASE
)
WILDCARD_CORS_RE = re.compile(r'CORS_ORIGINS["\']\s*,\s*["\']\*["\']')
ROUTER_GUARD_RE = re.compile(
    r'APIRouter\(\s*dependencies\s*=\s*\[\s*Depends\(require_internal_auth\)\s*\]', re.MULTILINE
)


def inspect(root: Path) -> dict:
    """Report only static file/regex findings, never credential values or absolute paths."""
    root = Path(root)
    findings: list[str] = []
    services: dict[str, dict] = {}
    for name, relative_path in SERVICE_PATHS.items():
        path = root / relative_path
        present = path.is_file()
        service = {
            "relative_path": relative_path,
            "source_present": present,
            "configured_port": None,
            "internal_auth_router_detected": False,
        }
        if not present:
            findings.append(f"missing_source:{name}")
        else:
            code = path.read_text(encoding="utf-8")
            port_match = PORT_RE.search(code)
            service["configured_port"] = int(port_match.group(1)) if port_match else None
            service["internal_auth_router_detected"] = bool(ROUTER_GUARD_RE.search(code))
            if not service["internal_auth_router_detected"]:
                findings.append(f"protected_router_not_detected:{name}")
            if MONEY_FLOAT_RE.search(code):
                findings.append(f"monetary_float_detected:{name}")
            if WILDCARD_CORS_RE.search(code):
                findings.append(f"wildcard_cors_default:{name}")
            if service["configured_port"] is None:
                findings.append(f"port_not_detected:{name}")
        services[name] = service
    portal_path = "web/src/AppRouter.tsx"
    if not (root / portal_path).is_file():
        findings.append("missing_source:portal")
    return {
        "schema_version": 1,
        "scope": "Arcadia-related Tranc3 source contracts, not live deployments",
        "status": "review_required",
        "portal": {"relative_path": portal_path, "source_present": (root / portal_path).is_file()},
        "services": services,
        "findings": sorted(findings),
        "limitations": [
            "Static source checks only; no repository history, auth flow, tests, runtime or Cloudflare verified",
            "Regex matches are triage indicators, not confirmed exploitable vulnerabilities",
            "Never use this report as authorisation to process real payments",
        ],
    }


def strict_exit_code(report: dict) -> int:
    """Exit 2 for an identified source-level finding; 0 otherwise."""
    return 2 if report["findings"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true", help="Exit 2 if findings exist (opt-in CI gate)")
    args = parser.parse_args()
    report = inspect(args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return strict_exit_code(report) if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
