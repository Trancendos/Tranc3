#!/usr/bin/env python3
"""Register the EA workbook's anchor services with health-aggregator.

Reads docs/architecture/ea-workbook/02_service_inventory.csv and POSTs each
row to health-aggregator's dynamic registry (POST /services), so the CMDB's
HealthCheckPath/HealthCheckInterval columns actually drive live monitoring
instead of sitting next to the code as documentation only.

Usage:
    python scripts/register_ea_workbook_services.py \
        --health-aggregator-url http://health-aggregator:8029

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

# ServiceID -> docker-compose.production.yml service key, for building a
# health_url reachable via Docker DNS on tranc3-net (the network
# health-aggregator itself runs on). --host overrides this per-run for the
# rare case you're probing from outside that network via published ports.
# SRV-WORKSHOP-001 has no entry: Forgejo runs in a separate compose project
# (deploy/forgejo/docker-compose.yml) that is not part of tranc3-net, so it
# has no compose-DNS-resolvable name from health-aggregator's perspective.
SERVICE_ID_TO_COMPOSE_NAME: dict[str, str] = {
    "SRV-SPARK-001": "tranc3-backend",  # Spark is mounted inside tranc3-backend
    "SRV-GRID-001": "workflow-engine-service",
    "SRV-INF-001": "infinity-auth",
    "SRV-VOID-001": "vault-service",
    "SRV-OBS-001": "observatory",
}


def load_rows() -> list[dict[str, str]]:
    with open(WORKBOOK_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health-aggregator-url",
        default=os.environ.get("HEALTH_AGGREGATOR_URL", "http://health-aggregator:8029"),
    )
    parser.add_argument(
        "--host",
        default=None,
        help=(
            "Override host for every registered service's health_url (e.g. localhost "
            "when every worker port is published to the same host). Default: resolve "
            "each anchor's compose service name from SERVICE_ID_TO_COMPOSE_NAME "
            "(Docker DNS on tranc3-net) — matches how health-aggregator itself is "
            "deployed, so registered checks are actually reachable from it."
        ),
    )
    parser.add_argument(
        "--internal-secret",
        default=os.environ.get("INTERNAL_SECRET", ""),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = load_rows()
    headers = {"X-Internal-Secret": args.internal_secret} if args.internal_secret else {}

    registered, skipped, failed = 0, 0, 0
    # Known-limitation skips (e.g. SRV-WORKSHOP-001 not being on tranc3-net)
    # are an expected, permanent condition, not a data-quality problem —
    # tracked separately so they don't flip the exit code to failure on
    # every normal run.
    known_limitation_skipped = 0
    for row in rows:
        service_id = row.get("ServiceID", "?")
        notes = row.get("Notes", "")
        # csv.DictReader yields "" for an empty cell, not None, so a plain
        # .get(..., default) doesn't fall back — an empty HealthCheckInterval
        # would otherwise crash int() below, and a path missing its leading
        # slash would silently build a malformed URL.
        health_path = row.get("HealthCheckPath", "").strip() or "/health"
        if not health_path.startswith("/"):
            health_path = f"/{health_path}"
        interval = row.get("HealthCheckInterval", "").strip() or "30"

        m = PORT_RE.search(notes)
        if not m:
            print(f"SKIP {service_id}: no port found in Notes ({notes!r})")
            skipped += 1
            continue
        port = m.group(1)
        name = row.get("ServiceName", service_id)

        if args.host is not None:
            host = args.host
        else:
            host = SERVICE_ID_TO_COMPOSE_NAME.get(service_id)
            if host is None:
                print(
                    f"SKIP {service_id}: no compose service name known (not on tranc3-net, "
                    f"or SERVICE_ID_TO_COMPOSE_NAME needs an entry) — pass --host to force one"
                )
                known_limitation_skipped += 1
                continue
        url = f"http://{host}:{port}{health_path}"

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
            failed += 1

    print(
        f"\n{registered} registered, {skipped} skipped, "
        f"{known_limitation_skipped} skipped (known limitation), {failed} failed."
    )
    return 0 if skipped == 0 and failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
