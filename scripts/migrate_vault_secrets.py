"""
Vault Migration — vault-service (port 8038) → The Void / infinity-void (port 8002)

Usage:
    python scripts/migrate_vault_secrets.py [--dry-run] [--vault-db PATH]

Reads every active, non-zeroized secret from vault-service's SQLite database,
decrypts with vault-service's AES-256-GCM key, and re-stores via The Void's
HTTP API using MASTER_KEY_SEED-based encryption.

Required env vars:
    VAULT_MASTER_KEY     — vault-service decryption key
    INTERNAL_SECRET      — shared internal auth header value
    VOID_URL             — base URL of The Void (default: http://localhost:8002)

After a successful migration run, decommission vault-service by removing it
from docker-compose and setting VAULT_DECOMMISSIONED=1.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

os.environ.setdefault("ENVIRONMENT", "development")

# Reuse vault-service crypto helpers directly (no running service needed)
os.environ.setdefault("VAULT_MASTER_KEY", os.environ.get("VAULT_MASTER_KEY", ""))
from workers.vault_service.worker import _decrypt_secret  # noqa: E402

VOID_URL = os.environ.get("VOID_URL", "http://localhost:8002")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
VAULT_DB = os.environ.get("VAULT_DB_PATH", "data/vault.db")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if INTERNAL_SECRET:
        h["X-Internal-Secret"] = INTERNAL_SECRET
    return h


def migrate(vault_db: str, dry_run: bool) -> None:
    if not Path(vault_db).exists():
        print(f"[SKIP] vault-service DB not found at {vault_db} — nothing to migrate.")
        return

    conn = sqlite3.connect(vault_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, key, encrypted_value, tags, ttl FROM secrets WHERE is_active=1"
    ).fetchall()
    conn.close()

    print(f"Found {len(rows)} active secret(s) in vault-service DB: {vault_db}")
    if not rows:
        print("Nothing to migrate.")
        return

    migrated = skipped = errors = 0

    with httpx.Client(base_url=VOID_URL, headers=_headers(), timeout=10) as client:
        for row in rows:
            key = row["key"]
            try:
                plaintext = _decrypt_secret(row["encrypted_value"])
            except Exception as exc:
                print(f"  [ERROR] Could not decrypt '{key}': {exc}")
                errors += 1
                continue

            if dry_run:
                print(f"  [DRY-RUN] Would migrate: {key}")
                migrated += 1
                continue

            resp = client.post("/secrets", json={"key": key, "value": plaintext})
            if resp.status_code in (200, 201):
                print(f"  [OK] Migrated: {key}")
                migrated += 1
            elif resp.status_code == 409:
                print(f"  [SKIP] Already exists in The Void: {key}")
                skipped += 1
            else:
                print(f"  [ERROR] {key} → HTTP {resp.status_code}: {resp.text[:120]}")
                errors += 1

    print(f"\nMigration complete: {migrated} migrated, {skipped} skipped, {errors} errors.")
    if errors:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate vault-service secrets to The Void")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be migrated, don't write")
    parser.add_argument("--vault-db", default=VAULT_DB, help="Path to vault-service SQLite DB")
    args = parser.parse_args()

    if not os.environ.get("VAULT_MASTER_KEY"):
        print("ERROR: VAULT_MASTER_KEY env var is required to decrypt vault-service secrets.")
        sys.exit(1)

    migrate(args.vault_db, args.dry_run)


if __name__ == "__main__":
    main()
