#!/usr/bin/env python3
"""Register the EA workbook's anchor services with health-aggregator.

Reads docs/architecture/ea-workbook/02_service_inventory.csv and POSTs each
row to health-aggregator's dynamic registry (POST /services), so the CMDB's
HealthCheckPath/HealthCheckInterval columns actually drive live monitoring
instead of sitting next to the code as documentation only.

Usage:
    python scripts/register_ea_workbook_services.py \
        --health-aggregator-url http://localhost:8029 \
        --host localhost

Each row's port is extracted from its free-text Notes column (e.g. "port 8034"),
since 02_service_inventory.csv doesn't have a dedicated Port column. Rows whose
Notes don't contain a recognizable port are skipped with a warning rather than
failing the whole run.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

import httpx

WORKBOOK_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "architecture",
    "ea-workbook",
    "02_service_inventory.csv",
)

PORT_RE = re.compile(r"\bport\s+(\d{4,5})\b", re.IGNORECASE)


def load_rows() -> list[dict[str, str]]:
    with open(WORKBOOK_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health-aggregator-url",
        default=os.environ.get("HEALTH_AGGREGATOR_URL", "http://localhost:8029"),
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host the anchor services are reachable at (default: localhost)",
    )
    parser.add_argument(
        "--internal-secret",
        default=os.environ.get("INTERNAL_SECRET", ""),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = load_rows()
    headers = {"X-Internal-Secret": args.internal_secret} if args.internal_secret else {}

    registered, skipped = 0, 0
    for row in rows:
        service_id = row.get("ServiceID", "?")
        notes = row.get("Notes", "")
        health_path = row.get("HealthCheckPath", "/health")
        interval = row.get("HealthCheckInterval", "30")

        m = PORT_RE.search(notes)
        if not m:
            print(f"SKIP {service_id}: no port found in Notes ({notes!r})")
            skipped += 1
            continue
        port = m.group(1)
        url = f"http://{args.host}:{port}{health_path}"
        name = row.get("ServiceName", service_id)

        if args.dry_run:
            print(f"[dry-run] would register {name} -> {url} (every {interval}s)")
            registered += 1
            continue

        try:
            resp = httpx.post(
                f"{args.health_aggregator_url}/services",
                json={"name": name, "url": url, "interval_seconds": int(interval)},
                headers=headers,
                timeout=5.0,
            )
            resp.raise_for_status()
            print(f"OK   {name} -> {url}")
            registered += 1
        except httpx.HTTPError as e:
            print(f"FAIL {name} -> {url}: {e}")

    print(f"\n{registered} registered, {skipped} skipped (no port in Notes).")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
