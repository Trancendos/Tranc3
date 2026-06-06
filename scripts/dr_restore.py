#!/usr/bin/env python3
"""
Trancendos DR Restore Script
=============================
Automated disaster-recovery restore utility.  Runs standalone — no running
services required.  Reads from the same backup directory as backup-service.

Usage
-----
# List available backups
python scripts/dr_restore.py list [--worker WORKER]

# Verify latest backup for all workers (or one)
python scripts/dr_restore.py verify [--worker WORKER]

# Dry-run restore — verify only, do NOT overwrite live DB
python scripts/dr_restore.py restore --worker WORKER --dry-run

# Full restore — overwrites live DB (backs up current first)
python scripts/dr_restore.py restore --worker WORKER

# Restore all CRITICAL-tier workers
python scripts/dr_restore.py restore-tier --tier critical

# Show RPO status
python scripts/dr_restore.py rpo-status

# Full DR drill — verify + dry-run restore all registered workers
python scripts/dr_restore.py dr-drill

Environment
-----------
BACKUP_ROOT         Path to backup directory (default: /data/backups)
TRANC3_DB_MASTER_KEY  AES key for encrypted backups (hex-encoded)
SECRET_KEY          Fallback passphrase for key derivation
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backup.engine import BackupEngine
from src.backup.registry import (
    REGISTRY_BY_TIER,
    REGISTRY_BY_WORKER,
    WORKER_DATABASE_REGISTRY,
    BackupTier,
)

BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/data/backups"))


def _engine() -> BackupEngine:
    return BackupEngine(backup_root=BACKUP_ROOT, encrypt=True)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    eng = _engine()
    backups = eng.list_backups(args.worker)
    if not backups:
        print("No backups found.")
        return 0
    for b in backups:
        print(
            f"  {b['worker']:35s}  {b['timestamp']}  {b['tier']:8s}  "
            f"{b['compressed_size_bytes']:>8,} bytes  verified={b['verified']}"
        )
    print(f"\n{len(backups)} backup(s) found.")
    return 0


def cmd_verify(args) -> int:
    eng = _engine()
    if args.worker:
        workers = [REGISTRY_BY_WORKER[args.worker]] if args.worker in REGISTRY_BY_WORKER else []
        if not workers:
            print(f"ERROR: worker '{args.worker}' not in registry", file=sys.stderr)
            return 1
        results = {args.worker: eng._verify(Path(eng._latest_backup(args.worker) or ""), args.worker)}
    else:
        results = eng.verify_all()

    ok = sum(1 for v in results.values() if v)
    print(f"\nVerification results ({ok}/{len(results)} OK):")
    for worker, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {worker}")
    return 0 if all(results.values()) else 1


def cmd_restore(args) -> int:
    eng = _engine()
    print(f"\n{'DRY-RUN ' if args.dry_run else ''}Restoring worker: {args.worker}")
    if not args.dry_run:
        confirm = input("  This will overwrite the live database. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return 1

    result = eng.restore(
        worker=args.worker,
        backup_path=getattr(args, "backup_path", None),
        dry_run=args.dry_run,
    )

    if result.success:
        print(f"  ✓ {'Verified (dry run)' if args.dry_run else 'Restored'}: {result.restored_to}")
        print(f"  From: {result.backup_path}")
    else:
        print(f"  ✗ FAILED: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


def cmd_restore_tier(args) -> int:
    try:
        tier = BackupTier(args.tier)
    except ValueError:
        print(f"ERROR: unknown tier '{args.tier}'. Valid: critical, high, standard, low", file=sys.stderr)
        return 1

    workers = REGISTRY_BY_TIER.get(tier, [])
    if not workers:
        print(f"No workers in tier '{args.tier}'")
        return 0

    eng = _engine()
    print(f"\nRestoring {len(workers)} {tier.value.upper()} workers (dry_run={args.dry_run})")

    exit_code = 0
    for worker_db in workers:
        result = eng.restore(worker=worker_db.worker, dry_run=args.dry_run)
        status = "✓" if result.success else "✗"
        print(f"  {status} {worker_db.worker:40s} {result.error or ''}")
        if not result.success:
            exit_code = 1

    return exit_code


def cmd_rpo_status(args) -> int:
    eng = _engine()
    status = eng.status()
    breached = [w for w in status["workers"] if w["rpo_breached"]]

    print(f"\nRPO Status — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"  Registered workers : {status['total_workers']}")
    print(f"  Healthy (RPO OK)   : {status['healthy']}")
    print(f"  RPO breached       : {len(breached)}")
    print(f"  Health             : {status['health_pct']}%\n")

    if breached:
        print("  RPO BREACHED:")
        for w in breached:
            age = f"{w['age_minutes']:.0f}min" if w["age_minutes"] is not None else "never"
            print(f"    ✗ {w['worker']:40s} tier={w['tier']:8s} age={age:>10s} rpo={w['rpo_minutes']}min")

    print("\n  ALL WORKERS:")
    for w in status["workers"]:
        age = f"{w['age_minutes']:.0f}min" if w["age_minutes"] is not None else "never"
        marker = "✓" if not w["rpo_breached"] else "✗"
        print(f"    {marker} {w['worker']:40s} tier={w['tier']:8s} age={age:>10s}")

    return 0 if not breached else 1


def cmd_dr_drill(args) -> int:
    """Full DR drill: verify + dry-run restore all workers. Safe — no live DBs touched."""
    eng = _engine()
    print(f"\n{'='*60}")
    print(f"  TRANCENDOS DR DRILL — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"{'='*60}")

    print("\n[1/2] Verifying all backups...")
    verify_results = eng.verify_all()

    print("\n[2/2] Dry-run restore for all workers...")
    restore_results = {}
    for worker_db in WORKER_DATABASE_REGISTRY:
        result = eng.restore(worker=worker_db.worker, dry_run=True)
        restore_results[worker_db.worker] = result

    # Report
    print(f"\n{'─'*60}")
    print(f"  {'WORKER':<40} VERIFY  RESTORE")
    print(f"{'─'*60}")
    all_ok = True
    for worker_db in WORKER_DATABASE_REGISTRY:
        v = "✓" if verify_results.get(worker_db.worker) else "✗"
        r_result = restore_results.get(worker_db.worker)
        r = "✓" if (r_result and r_result.success) else "✗"
        if v == "✗" or r == "✗":
            all_ok = False
        print(f"  {worker_db.worker:<40} {v}       {r}")

    print(f"{'─'*60}")
    v_ok = sum(1 for v in verify_results.values() if v)
    r_ok = sum(1 for r in restore_results.values() if r and r.success)
    total = len(WORKER_DATABASE_REGISTRY)
    print(f"\n  Verify:  {v_ok}/{total}")
    print(f"  Restore: {r_ok}/{total}")
    print(f"\n  Drill result: {'PASS ✓' if all_ok else 'FAIL ✗'}\n")

    return 0 if all_ok else 1


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trancendos DR Restore CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List available backups")
    p_list.add_argument("--worker", help="Filter by worker name")

    # verify
    p_verify = sub.add_parser("verify", help="Verify backup integrity")
    p_verify.add_argument("--worker", help="Verify specific worker only")

    # restore
    p_restore = sub.add_parser("restore", help="Restore a worker database")
    p_restore.add_argument("--worker", required=True, help="Worker name")
    p_restore.add_argument("--backup-path", help="Specific backup file (default: latest)")
    p_restore.add_argument("--dry-run", action="store_true", default=False,
                           help="Verify only — do not overwrite live DB")

    # restore-tier
    p_tier = sub.add_parser("restore-tier", help="Restore all workers of a given tier")
    p_tier.add_argument("--tier", required=True,
                        choices=["critical", "high", "standard", "low"])
    p_tier.add_argument("--dry-run", action="store_true", default=False)

    # rpo-status
    sub.add_parser("rpo-status", help="Show RPO compliance status")

    # dr-drill
    sub.add_parser("dr-drill", help="Full DR drill: verify + dry-run restore all workers")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "verify": cmd_verify,
        "restore": cmd_restore,
        "restore-tier": cmd_restore_tier,
        "rpo-status": cmd_rpo_status,
        "dr-drill": cmd_dr_drill,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
