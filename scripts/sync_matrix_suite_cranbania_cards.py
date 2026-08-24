#!/usr/bin/env python3
"""
sync_matrix_suite_cranbania_cards.py — Matrix Suites Stage 7.4 CLI entrypoint.

Thin wrapper around src.compliance.matrix_suites_cranbania.sync_suite_review_cards()
for cron/manual invocation. See that module's docstring for the full design
(tags substituting for a CranBania "lane", idempotency, why this doesn't
duplicate Stage 7.2's overdue detection).

Usage:
    CRANBANIA_API_KEY=... python scripts/sync_matrix_suite_cranbania_cards.py
    CRANBANIA_API_KEY=... python scripts/sync_matrix_suite_cranbania_cards.py \
        --cranbania-url http://localhost:8071

Exit codes: 0 if every suite synced without error (created or skipped is
fine — only "error" outcomes fail the run), 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.compliance.matrix_suites_cranbania import sync_suite_review_cards


async def _run(cranbania_url: str | None, matrix_suites_path: str | None) -> int:
    summary = await sync_suite_review_cards(
        matrix_suites_path=matrix_suites_path, cranbania_url=cranbania_url
    )

    print("=" * 60)
    print("Matrix Suites — CranBania review-card sync")
    print("=" * 60)
    for result in summary.results:
        marker = {"created": "+", "error": "x"}.get(result.action, "-")
        detail = f" ({result.detail})" if result.detail else ""
        print(f"  [{marker}] {result.suite_id}: {result.action}{detail}")
    print(f"\ncreated={summary.created} skipped={summary.skipped} errors={summary.errors}")

    return 1 if summary.errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cranbania-url", default=None, help="Overrides CRANBANIA_URL env var")
    parser.add_argument(
        "--matrix-suites-path", default=None, help="Overrides MATRIX_SUITES_PATH env var"
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.cranbania_url, args.matrix_suites_path))


if __name__ == "__main__":
    sys.exit(main())
