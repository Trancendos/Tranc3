#!/usr/bin/env python3
"""Feed a pytest run into The Chaos Party.

The Chaos Party is the platform's testing Location: suites, runs, batch runs,
chaos experiments, and the trend analysis built on top of them. Until now
nothing fed it. CI ran pytest directly, so the platform's own test intelligence
never saw the platform's own tests -- the Location was built, deployed and
reachable, and received nothing.

`conftest.py` already writes one JSON line per test to `logs/test_results.jsonl`.
This script turns those lines into `POST /runs/batch` calls, which is also the
route that forwards to The Observatory, so a reported run lights up both legs.

Configuration, and what happens when it is missing:

    CHAOS_PARTY_URL    base URL of the worker. Unset -> this script does
                       nothing and exits 0.
    INTERNAL_SECRET    shared secret for the X-Internal-Secret header. Required
                       whenever CHAOS_PARTY_URL is set; missing -> exit 2.

The unset-URL case exits 0 on purpose: GitHub-hosted runners cannot reach a
compose-internal worker, and a step that always fails there would train people
to ignore it. But once the URL *is* configured, every failure is a real failure
and this script exits non-zero. Reporting must not be the kind of control that
runs, reports, and never blocks -- the exact defect this whole exercise exists
to find. Silence here means "not configured", never "posted successfully".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = REPO / "logs" / "test_results.jsonl"

# pytest outcomes -> Chaos Party run statuses. Anything unrecognised is
# reported verbatim rather than coerced into "passed".
_STATUS = {
    "passed": "passed",
    "failed": "failed",
    "error": "failed",
    "skipped": "skipped",
    "xfailed": "skipped",
    "xpassed": "passed",
}


def read_results(path: Path) -> list[dict[str, Any]]:
    """Parse the JSONL result log, skipping malformed lines."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("test"):
            rows.append(row)
    return rows


def to_runs(rows: list[dict[str, Any]], ran_by: str) -> list[dict[str, Any]]:
    """Map result rows onto the worker's TestRunIn shape."""
    runs = []
    for row in rows:
        outcome = str(row.get("outcome", "")).lower()
        duration = row.get("duration_ms")
        runs.append(
            {
                "name": row["test"],
                "status": _STATUS.get(outcome, outcome or "unknown"),
                "duration_ms": int(duration) if isinstance(duration, (int, float)) else None,
                "error_msg": (row.get("reason") or None),
                "ran_by": ran_by,
                "metadata": {
                    "commit": row.get("commit"),
                    "run_id": row.get("run_id"),
                    "ts": row.get("ts"),
                },
            }
        )
    return runs


def chunked(runs: list[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(runs), size):
        yield runs[start : start + size]


def post_batch(
    base_url: str, secret: str, batch: list[dict[str, Any]], suite_id: int | None, timeout: float
) -> dict[str, Any]:
    """POST one batch. Raises on any non-201 response or transport failure."""
    payload = {"runs": batch}
    if suite_id is not None:
        payload["suite_id"] = suite_id
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/runs/batch",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Internal-Secret": secret},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        if response.status != 201:
            raise RuntimeError(f"expected 201, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--suite-id", type=int, default=None)
    parser.add_argument("--ran-by", default="ci")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    base_url = os.getenv("CHAOS_PARTY_URL", "").strip()
    if not base_url:
        print("CHAOS_PARTY_URL is not set -- no test run reported to The Chaos Party.")
        return 0

    secret = os.getenv("INTERNAL_SECRET", "").strip()
    if not secret:
        print(
            "CHAOS_PARTY_URL is set but INTERNAL_SECRET is not. "
            "The worker rejects unauthenticated writes, so this would post nothing.",
            file=sys.stderr,
        )
        return 2

    rows = read_results(Path(args.results))
    if not rows:
        print(f"No test results found at {args.results} -- nothing to report.")
        return 0

    runs = to_runs(rows, args.ran_by)
    reported = 0
    for batch in chunked(runs, max(1, args.batch_size)):
        try:
            result = post_batch(base_url, secret, batch, args.suite_id, args.timeout)
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
            print(
                f"Failed to report {len(batch)} runs to The Chaos Party at {base_url}: {exc}",
                file=sys.stderr,
            )
            return 1
        reported += int(result.get("inserted", 0))

    failed = sum(1 for run in runs if run["status"] == "failed")
    print(f"Reported {reported} test runs to The Chaos Party ({failed} failed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
