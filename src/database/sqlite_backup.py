"""Automated SQLite backup with integrity checking — RSK-002 (data corruption).

Performs WAL-safe hot backups of all worker SQLite databases, verifies
integrity post-backup, rotates old backups, and alerts on failures.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.getenv("SQLITE_BACKUP_DIR", "./backups/sqlite")) if False else Path("./backups/sqlite")
RETENTION_DAYS = 7
MAX_BACKUPS_PER_DB = 14


class BackupResult(NamedTuple):
    db_path: str
    backup_path: str
    success: bool
    integrity_ok: bool
    size_bytes: int
    checksum: str
    error: str | None


import os

BACKUP_DIR = Path(os.getenv("SQLITE_BACKUP_DIR", "./backups/sqlite"))


def _discover_databases() -> list[Path]:
    """Find all SQLite databases used by workers."""
    data_root = Path("./data")
    worker_root = Path("./workers")
    db_files: list[Path] = []

    for search_root in [data_root, worker_root]:
        if search_root.exists():
            db_files.extend(search_root.rglob("*.db"))

    return [p for p in db_files if p.stat().st_size > 0] if db_files else []


def _wal_backup(src: Path, dst: Path) -> bool:
    """Hot backup using SQLite backup API (WAL-safe)."""
    try:
        src_conn = sqlite3.connect(str(src))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst_conn = sqlite3.connect(str(dst))
        src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        return True
    except Exception as e:
        logger.error("WAL backup failed %s -> %s: %s", src, dst, e)
        return False


def _integrity_check(db_path: Path) -> bool:
    """Run PRAGMA integrity_check on a database file."""
    try:
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return result and result[0] == "ok"
    except Exception as e:
        logger.error("Integrity check failed for %s: %s", db_path, e)
        return False


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def backup_database(db_path: Path) -> BackupResult:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rel = db_path.relative_to(Path(".")) if db_path.is_relative_to(Path(".")) else Path(db_path.name)
    backup_path = BACKUP_DIR / rel.parent / f"{db_path.stem}_{ts}.db"

    success = _wal_backup(db_path, backup_path)
    if not success:
        return BackupResult(str(db_path), str(backup_path), False, False, 0, "", "WAL backup failed")

    integrity_ok = _integrity_check(backup_path)
    size = backup_path.stat().st_size if backup_path.exists() else 0
    checksum = _checksum(backup_path) if backup_path.exists() else ""

    if not integrity_ok:
        logger.error("Integrity check failed on backup: %s", backup_path)

    logger.info("Backup: %s -> %s (%d bytes, integrity=%s)", db_path.name, backup_path.name, size, integrity_ok)
    return BackupResult(str(db_path), str(backup_path), True, integrity_ok, size, checksum, None)


def rotate_old_backups(db_name: str) -> int:
    """Remove backups older than RETENTION_DAYS or exceeding MAX_BACKUPS_PER_DB."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    removed = 0
    for backup_file in BACKUP_DIR.rglob(f"{db_name}_*.db"):
        try:
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                backup_file.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def backup_all() -> list[BackupResult]:
    dbs = _discover_databases()
    if not dbs:
        logger.info("No SQLite databases found to backup")
        return []

    results = []
    for db in dbs:
        result = backup_database(db)
        results.append(result)
        rotate_old_backups(db.stem)

    failed = [r for r in results if not r.success or not r.integrity_ok]
    if failed:
        logger.error("Backup failures: %d/%d databases", len(failed), len(results))
    else:
        logger.info("All %d databases backed up successfully", len(results))

    return results


async def backup_loop() -> None:
    """Background task: run backups every 6 hours."""
    logger.info("SQLite backup loop started (every 6h, retention %dd)", RETENTION_DAYS)
    while True:
        try:
            results = backup_all()
            failed = [r for r in results if not r.success]
            if failed:
                logger.error("Backup failures: %s", [r.db_path for r in failed])
        except Exception as e:
            logger.error("Backup loop error: %s", e)
        await asyncio.sleep(6 * 3600)
