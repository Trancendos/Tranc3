#!/usr/bin/env python3
"""
SOC 2 Type II Evidence Collector
=================================
Collects and snapshots evidence artefacts for the Trancendos SOC 2 Type II
audit period (2026-06-07 → 2026-12-07).

Run monthly from cron or CI:
    python scripts/soc2_evidence_collector.py --output /data/soc2_evidence

Outputs one JSON file per artefact category, named with YYYYMM or YYYYMMDD.
All artefacts are written to --output dir and a manifest (manifest.json) is
updated with SHA-256 hashes for chain-of-custody.

Artefacts collected:
  - audit_snapshot      : last N audit events from Observatory SQLite
  - access_review       : admin/moderator role holders from users-service DB
  - jwt_revocations     : revoked token count from infinity-auth DB
  - key_rotation_log    : last rotation timestamps from key_rotation DB
  - dependency_scan     : pip-audit + bandit JSON output
  - compliance_gate     : test_compliance.py result (pass/fail + score)
  - data_residency      : current region config + write enforcement status
  - health_snapshot     : /health/all from health-aggregator (if available)

Usage:
    python scripts/soc2_evidence_collector.py [--output DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("soc2")

NOW = datetime.now(timezone.utc)
YYYYMM = NOW.strftime("%Y%m")
YYYYMMDD = NOW.strftime("%Y%m%d")

# Paths — defaults match production Docker volume layout
OBSERVATORY_DB = os.environ.get("OBSERVATORY_DB_PATH", "/data/observatory_audit.db")
USERS_DB = os.environ.get("USERS_DB_PATH", "/data/users.db")
AUTH_DB = os.environ.get("AUTH_DB_PATH", "/data/infinity_auth.db")
KEY_ROTATION_DB = os.environ.get("KEY_ROTATION_DB_PATH", "/data/key_rotation.db")
HEALTH_URL = os.environ.get("HEALTH_AGGREGATOR_URL", "http://localhost:8029/health/all")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(output_dir: Path, name: str, data: dict, dry_run: bool) -> str:
    path = output_dir / name
    if not dry_run:
        path.write_text(json.dumps(data, indent=2, default=str))
        digest = _sha256(path)
        log.info("  wrote %s  sha256=%s", name, digest[:16] + "...")
        return digest
    log.info("  [dry-run] would write %s", name)
    return ""


def _sqlite_query(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    if not Path(db_path).exists():
        log.warning("DB not found: %s — skipping", db_path)
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    except Exception as exc:
        log.warning("Query failed on %s: %s", db_path, exc)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def collect_audit_snapshot(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """Last 10 000 events from Observatory SQLite, grouped by category/severity."""
    log.info("Collecting audit snapshot...")
    rows = _sqlite_query(
        OBSERVATORY_DB,
        """
        SELECT category, severity, COUNT(*) as count,
               MIN(timestamp) as earliest, MAX(timestamp) as latest
        FROM audit_events
        WHERE timestamp > strftime('%s', 'now', '-31 days')
        GROUP BY category, severity
        ORDER BY category, severity
        """,
    )
    # Also grab SECURITY events verbatim (always retained)
    security_events = _sqlite_query(
        OBSERVATORY_DB,
        """
        SELECT id, timestamp, event_type, actor, actor_ip, target, outcome, metadata
        FROM audit_events
        WHERE severity = 'security'
        ORDER BY timestamp DESC
        LIMIT 500
        """,
    )
    data = {
        "collected_at": NOW.isoformat(),
        "period_days": 31,
        "summary_by_category_severity": rows,
        "security_events": security_events,
        "db_path": OBSERVATORY_DB,
    }
    name = f"audit_snapshot_{YYYYMM}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_access_review(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """Admin and moderator role holders — monthly access review."""
    log.info("Collecting access review...")
    admins = _sqlite_query(
        USERS_DB,
        """
        SELECT user_id, username, email, role, infinity_role, is_active, last_login_at, created_at
        FROM users
        WHERE role IN ('admin', 'moderator') AND deleted_at IS NULL
        ORDER BY role, username
        """,
    )
    data = {
        "collected_at": NOW.isoformat(),
        "privileged_accounts": admins,
        "count": len(admins),
        "db_path": USERS_DB,
    }
    name = f"access_review_{YYYYMM}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_jwt_revocations(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """JWT revocation store summary from infinity-auth."""
    log.info("Collecting JWT revocation log...")
    summary = _sqlite_query(
        AUTH_DB,
        """
        SELECT COUNT(*) as total_revoked,
               SUM(CASE WHEN expires_at > strftime('%s','now') THEN 1 ELSE 0 END) as still_active,
               MIN(revoked_at) as earliest,
               MAX(revoked_at) as latest
        FROM revoked_tokens
        """,
    )
    recent = _sqlite_query(
        AUTH_DB,
        """
        SELECT jti, user_id, revoked_at, reason
        FROM revoked_tokens
        WHERE revoked_at > strftime('%s', 'now', '-31 days')
        ORDER BY revoked_at DESC
        LIMIT 200
        """,
    )
    data = {
        "collected_at": NOW.isoformat(),
        "summary": summary[0] if summary else {},
        "recent_revocations": recent,
    }
    name = f"jwt_revocations_{YYYYMM}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_key_rotation_log(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """Key rotation audit trail from key_rotation.db."""
    log.info("Collecting key rotation log...")
    log_rows = _sqlite_query(
        KEY_ROTATION_DB,
        """
        SELECT key_id, key_type, rotated_at, rotated_by, previous_key_fingerprint,
               new_key_fingerprint, success, notes
        FROM rotation_log
        ORDER BY rotated_at DESC
        LIMIT 100
        """,
    )
    status = _sqlite_query(
        KEY_ROTATION_DB,
        """
        SELECT key_id, key_type, last_rotated_at, next_rotation_due,
               rotation_period_days, is_overdue
        FROM key_schedule
        ORDER BY key_type
        """,
    )
    data = {
        "collected_at": NOW.isoformat(),
        "rotation_schedule": status,
        "rotation_history": log_rows,
    }
    name = f"key_rotation_log_{YYYYMM}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_dependency_scan(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """Run pip-audit and bandit, capture JSON output."""
    log.info("Collecting dependency scan (pip-audit + bandit)...")
    pip_result: dict = {"skipped": True, "reason": "pip-audit not available"}
    bandit_result: dict = {"skipped": True, "reason": "bandit not available"}

    try:
        r = subprocess.run(
            ["pip-audit", "--format=json", "--no-deps"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        pip_result = (
            json.loads(r.stdout) if r.stdout.strip() else {"raw": r.stdout, "stderr": r.stderr}
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        pip_result = {"skipped": True, "reason": str(exc)}

    try:
        r = subprocess.run(
            ["bandit", "-r", "src/", "workers/", "-f", "json", "-ll"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        bandit_result = json.loads(r.stdout) if r.stdout.strip() else {"raw": r.stdout}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        bandit_result = {"skipped": True, "reason": str(exc)}

    data = {
        "collected_at": NOW.isoformat(),
        "pip_audit": pip_result,
        "bandit": bandit_result,
    }
    name = f"dependency_scan_{YYYYMMDD}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_compliance_gate(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """Run test_compliance.py and capture DEFSTAN score."""
    log.info("Collecting compliance gate results...")
    result: dict = {"skipped": True, "reason": "pytest not available"}
    try:
        r = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "tests/test_compliance.py",
                "--tb=short",
                "--json-report",
                "--json-report-file=/tmp/compliance_report.json",
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd="/home/user/Tranc3",
        )
        report_path = Path("/tmp/compliance_report.json")
        if report_path.exists():
            result = json.loads(report_path.read_text())
        else:
            result = {
                "returncode": r.returncode,
                "stdout": r.stdout[-2000:],
                "stderr": r.stderr[-500:],
            }
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        result = {"skipped": True, "reason": str(exc)}

    data = {"collected_at": NOW.isoformat(), "compliance_gate": result}
    name = f"compliance_gate_{YYYYMMDD}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_data_residency(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """Snapshot current DATA_RESIDENCY_REGION config and enforcement status."""
    log.info("Collecting data residency config...")
    region = os.environ.get("DATA_RESIDENCY_REGION", "eu-west")
    allowed_regions = os.environ.get("DATA_RESIDENCY_ALLOWED_REGIONS", "eu-west,eu-central").split(
        ","
    )
    residency_log = (
        _sqlite_query(
            USERS_DB,
            """
        SELECT region, COUNT(*) as record_count, MIN(created_at) as earliest, MAX(created_at) as latest
        FROM users
        GROUP BY region
        """,
        )
        if Path(USERS_DB).exists()
        else []
    )

    data = {
        "collected_at": NOW.isoformat(),
        "active_region": region,
        "allowed_regions": [r.strip() for r in allowed_regions],
        "enforcement_enabled": os.environ.get("DATA_RESIDENCY_ENFORCE", "true").lower() == "true",
        "user_distribution_by_region": residency_log,
    }
    name = f"data_residency_{YYYYMM}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


def collect_health_snapshot(output_dir: Path, dry_run: bool, manifest: dict) -> None:
    """GET /health/all from health-aggregator if reachable."""
    log.info("Collecting health snapshot...")
    health_data: dict = {"skipped": True, "reason": "httpx not available or service unreachable"}
    try:
        import httpx  # noqa: PLC0415

        r = httpx.get(HEALTH_URL, timeout=10)
        health_data = r.json()
    except Exception as exc:
        health_data = {"skipped": True, "reason": str(exc)}

    data = {"collected_at": NOW.isoformat(), "health": health_data}
    name = f"health_snapshot_{YYYYMMDD}.json"
    digest = _write(output_dir, name, data, dry_run)
    if digest:
        manifest["artefacts"][name] = {"sha256": digest, "collected_at": NOW.isoformat()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="SOC 2 Type II evidence collector")
    parser.add_argument("--output", default="/data/soc2_evidence", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    args = parser.parse_args()

    output_dir = Path(args.output)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.json"
    manifest: dict = {"generated_at": NOW.isoformat(), "artefacts": {}}
    if manifest_path.exists() and not args.dry_run:
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest["generated_at"] = NOW.isoformat()
        except json.JSONDecodeError:
            pass

    collectors = [
        collect_audit_snapshot,
        collect_access_review,
        collect_jwt_revocations,
        collect_key_rotation_log,
        collect_dependency_scan,
        collect_compliance_gate,
        collect_data_residency,
        collect_health_snapshot,
    ]

    errors: list[str] = []
    for collector in collectors:
        try:
            collector(output_dir, args.dry_run, manifest)
        except Exception as exc:
            log.error("Collector %s failed: %s", collector.__name__, exc)
            errors.append(f"{collector.__name__}: {exc}")

    if not args.dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
        log.info("Manifest updated: %s", manifest_path)

    if errors:
        log.error("%d collector(s) failed:", len(errors))
        for e in errors:
            log.error("  - %s", e)
        return 1

    log.info("Evidence collection complete. %d artefacts.", len(manifest.get("artefacts", {})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
