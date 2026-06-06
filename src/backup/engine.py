"""
Backup Engine — SQLite Hot-Backup with AES-GCM Encryption, Compression & Verification
======================================================================================
Uses SQLite's built-in ``sqlite3.Connection.backup()`` API (safe under live writes,
no WAL checkpoint required) to produce consistent point-in-time snapshots.

Each backup file is:
    <backup_dir>/<worker>/<worker>_<ISO8601_timestamp>_<tier>.db.gz[.enc]

Steps per backup
----------------
1. sqlite3.Connection.backup() → temp file (consistent copy, live-safe)
2. gzip compress → reduces SQLite files by 60-90%
3. AES-GCM encrypt the compressed bytes (uses same key derivation as encrypted_sqlite)
4. Write to destination + write a sidecar <name>.meta.json
5. Verify: decompress+decrypt, open with sqlite3, run PRAGMA integrity_check
6. Prune old backups per retention policy

Recovery
--------
See BackupEngine.restore() and scripts/dr_restore.py for automated restore.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.backup.registry import (
    RETENTION,
    WORKER_DATABASE_REGISTRY,
    BackupTier,
    WorkerDB,
)

logger = logging.getLogger("tranc3.backup.engine")

BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/data/backups"))
_ENC_MAGIC = b"BKPENC1"  # 7-byte sentinel for encrypted backup files


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BackupMeta:
    worker: str
    db_path: str
    backup_path: str
    tier: str
    timestamp: str
    size_bytes: int
    compressed_size_bytes: int
    sha256: str
    encrypted: bool
    verified: bool
    duration_ms: float
    error: Optional[str] = None


@dataclass
class BackupResult:
    success: bool
    meta: Optional[BackupMeta] = None
    error: Optional[str] = None


@dataclass
class RestoreResult:
    success: bool
    worker: str
    restored_to: str
    backup_path: str
    verified: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Encryption helpers (separate key space from encrypted_sqlite field keys)
# ---------------------------------------------------------------------------


def _backup_key() -> bytes:
    """32-byte AES key for backup file encryption, derived from TRANC3_DB_MASTER_KEY."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    master_hex = os.environ.get("TRANC3_DB_MASTER_KEY", "")
    secret_key = os.environ.get("SECRET_KEY", "")
    salt = b"tranc3-backup-encryption-v1"

    if master_hex:
        try:
            master = bytes.fromhex(master_hex.strip())
            return HKDF(
                algorithm=hashes.SHA256(), length=32, salt=salt,
                info=b"backup-file-encryption",
            ).derive(master)
        except ValueError:
            pass

    if secret_key:
        return PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000,
        ).derive(secret_key.encode())

    import socket
    seed = f"dev-backup:{socket.gethostname()}".encode()
    return hashlib.sha256(seed).digest()


def _encrypt_bytes(data: bytes) -> bytes:
    key = _backup_key()
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, data, None)
    return _ENC_MAGIC + iv + ct


def _decrypt_bytes(data: bytes) -> bytes:
    if not data.startswith(_ENC_MAGIC):
        raise ValueError("Not an encrypted backup (missing BKPENC1 magic)")
    payload = data[len(_ENC_MAGIC):]
    iv, ct = payload[:12], payload[12:]
    return AESGCM(_backup_key()).decrypt(iv, ct, None)


# ---------------------------------------------------------------------------
# Backup Engine
# ---------------------------------------------------------------------------


class BackupEngine:
    """Performs, verifies, lists, prunes, and restores SQLite backups."""

    def __init__(
        self,
        backup_root: Path = BACKUP_ROOT,
        encrypt: bool = True,
    ) -> None:
        self.backup_root = Path(backup_root)
        self.encrypt = encrypt
        self.backup_root.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────────

    def backup(self, worker_db: WorkerDB) -> BackupResult:
        """Create a verified backup of *worker_db*."""
        import time

        db_path = Path(worker_db.resolved_path)
        if not db_path.exists():
            return BackupResult(
                success=False,
                error=f"Database not found: {db_path}",
            )

        start = time.monotonic()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest_dir = self.backup_root / worker_db.worker
        dest_dir.mkdir(parents=True, exist_ok=True)

        suffix = ".db.gz.enc" if self.encrypt else ".db.gz"
        backup_path = dest_dir / f"{worker_db.worker}_{ts}_{worker_db.tier.value}{suffix}"
        meta_path = backup_path.with_suffix("").with_suffix(".meta.json")

        try:
            raw_size = db_path.stat().st_size

            # Step 1: hot backup via sqlite3 API
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                src_conn = sqlite3.connect(str(db_path))
                dst_conn = sqlite3.connect(tmp_path)
                src_conn.backup(dst_conn)
                src_conn.close()
                dst_conn.close()

                # Step 2: read + compress
                raw_bytes = Path(tmp_path).read_bytes()
                compressed = gzip.compress(raw_bytes, compresslevel=6)

                # Step 3: optionally encrypt
                final_bytes = _encrypt_bytes(compressed) if self.encrypt else compressed
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            # Step 4: write
            backup_path.write_bytes(final_bytes)
            sha256 = hashlib.sha256(final_bytes).hexdigest()

            # Step 5: verify
            verified = self._verify(backup_path, worker_db.worker)

            duration_ms = (time.monotonic() - start) * 1000

            meta = BackupMeta(
                worker=worker_db.worker,
                db_path=str(db_path),
                backup_path=str(backup_path),
                tier=worker_db.tier.value,
                timestamp=ts,
                size_bytes=raw_size,
                compressed_size_bytes=len(final_bytes),
                sha256=sha256,
                encrypted=self.encrypt,
                verified=verified,
                duration_ms=round(duration_ms, 1),
            )
            meta_path.write_text(json.dumps(asdict(meta), indent=2))

            logger.info(
                "backup OK worker=%s tier=%s size=%d→%d verified=%s dur=%.0fms",
                worker_db.worker, worker_db.tier.value, raw_size, len(final_bytes),
                verified, duration_ms,
            )

            # Step 6: prune old backups
            self._prune(worker_db)

            return BackupResult(success=True, meta=meta)

        except Exception as exc:
            logger.exception("backup FAILED worker=%s: %s", worker_db.worker, exc)
            return BackupResult(success=False, error=str(exc))

    def backup_all(self, tier: Optional[BackupTier] = None) -> List[BackupResult]:
        """Backup all registered databases, optionally filtered by tier."""
        targets = WORKER_DATABASE_REGISTRY
        if tier:
            targets = [w for w in targets if w.tier == tier]
        return [self.backup(w) for w in targets]

    def restore(
        self,
        worker: str,
        backup_path: Optional[str] = None,
        target_path: Optional[str] = None,
        dry_run: bool = False,
    ) -> RestoreResult:
        """Restore a worker's database from the latest (or specified) backup.

        Args:
            worker:      Worker name (must match registry).
            backup_path: Specific backup file to restore; defaults to latest.
            target_path: Where to write the restored DB; defaults to the worker's
                         live database path (replacing it after verification).
            dry_run:     Verify only — do not overwrite the live database.
        """
        from src.backup.registry import REGISTRY_BY_WORKER

        worker_db = REGISTRY_BY_WORKER.get(worker)
        if not worker_db and not target_path:
            return RestoreResult(
                success=False, worker=worker, restored_to="",
                backup_path=backup_path or "",
                verified=False,
                error=f"Worker '{worker}' not in registry and no target_path given",
            )

        live_path = target_path or (worker_db.resolved_path if worker_db else "")

        # Find backup file
        if not backup_path:
            backup_path = self._latest_backup(worker)
            if not backup_path:
                return RestoreResult(
                    success=False, worker=worker, restored_to=live_path,
                    backup_path="", verified=False,
                    error=f"No backups found for worker '{worker}'",
                )

        bp = Path(backup_path)
        if not bp.exists():
            return RestoreResult(
                success=False, worker=worker, restored_to=live_path,
                backup_path=backup_path, verified=False,
                error=f"Backup file not found: {backup_path}",
            )

        try:
            raw = bp.read_bytes()
            # Decrypt if needed
            if raw.startswith(_ENC_MAGIC):
                raw = _decrypt_bytes(raw)
            # Decompress
            restored_bytes = gzip.decompress(raw)

            # Write to temp, verify integrity, then move into place
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp.write(restored_bytes)
                tmp_path = tmp.name

            # Integrity check
            verified = self._integrity_check(tmp_path)

            if dry_run:
                Path(tmp_path).unlink(missing_ok=True)
                return RestoreResult(
                    success=verified, worker=worker, restored_to=live_path,
                    backup_path=backup_path, verified=verified,
                    error=None if verified else "Integrity check failed (dry run)",
                )

            if not verified:
                Path(tmp_path).unlink(missing_ok=True)
                return RestoreResult(
                    success=False, worker=worker, restored_to=live_path,
                    backup_path=backup_path, verified=False,
                    error="Integrity check failed — refusing to overwrite live database",
                )

            # Atomic replace: rename live → .pre-restore, move temp → live
            live = Path(live_path)
            live.parent.mkdir(parents=True, exist_ok=True)
            if live.exists():
                live.rename(live.with_suffix(".pre-restore.db"))
            shutil.move(tmp_path, str(live))

            logger.info("restore OK worker=%s from=%s to=%s", worker, backup_path, live_path)
            return RestoreResult(
                success=True, worker=worker, restored_to=live_path,
                backup_path=backup_path, verified=True,
            )

        except Exception as exc:
            logger.exception("restore FAILED worker=%s: %s", worker, exc)
            return RestoreResult(
                success=False, worker=worker, restored_to=live_path,
                backup_path=backup_path, verified=False, error=str(exc),
            )

    def list_backups(self, worker: Optional[str] = None) -> List[dict]:
        """Return sorted list of backup metadata dicts (newest first)."""
        results = []
        search_root = self.backup_root / worker if worker else self.backup_root
        for meta_file in sorted(search_root.rglob("*.meta.json"), reverse=True):
            try:
                results.append(json.loads(meta_file.read_text()))
            except Exception:
                pass
        return results

    def verify_all(self) -> dict[str, bool]:
        """Verify the latest backup for every registered worker."""
        results = {}
        for worker_db in WORKER_DATABASE_REGISTRY:
            latest = self._latest_backup(worker_db.worker)
            if not latest:
                results[worker_db.worker] = False
                continue
            results[worker_db.worker] = self._verify(Path(latest), worker_db.worker)
        return results

    def status(self) -> dict:
        """Return a summary of backup health for all registered workers."""

        now = datetime.now(timezone.utc)
        workers_status = []

        for worker_db in WORKER_DATABASE_REGISTRY:
            latest_path = self._latest_backup(worker_db.worker)
            if not latest_path:
                workers_status.append({
                    "worker": worker_db.worker,
                    "tier": worker_db.tier.value,
                    "status": "NO_BACKUP",
                    "last_backup": None,
                    "age_minutes": None,
                    "rpo_minutes": worker_db.backup_interval_minutes,
                    "rpo_breached": True,
                })
                continue

            meta_path = Path(latest_path).with_suffix("").with_suffix(".meta.json")
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                except Exception:
                    pass

            ts_str = meta.get("timestamp", "")
            age_minutes = None
            rpo_breached = True
            if ts_str:
                try:
                    ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                    age_minutes = round((now - ts).total_seconds() / 60, 1)
                    rpo_breached = age_minutes > worker_db.backup_interval_minutes
                except Exception:
                    pass

            workers_status.append({
                "worker": worker_db.worker,
                "tier": worker_db.tier.value,
                "status": "OK" if not rpo_breached else "RPO_BREACHED",
                "last_backup": meta.get("timestamp"),
                "age_minutes": age_minutes,
                "rpo_minutes": worker_db.backup_interval_minutes,
                "rto_minutes": worker_db.rto_minutes,
                "rpo_breached": rpo_breached,
                "verified": meta.get("verified", False),
                "size_bytes": meta.get("compressed_size_bytes"),
            })

        total = len(workers_status)
        healthy = sum(1 for w in workers_status if w["status"] == "OK")
        return {
            "total_workers": total,
            "healthy": healthy,
            "unhealthy": total - healthy,
            "health_pct": round(healthy / total * 100, 1) if total else 0,
            "workers": workers_status,
        }

    # ── Internals ───────────────────────────────────────────────────────────

    def _verify(self, backup_path: Path, worker: str) -> bool:
        """Decrypt, decompress, open, and run integrity_check on the backup."""
        try:
            raw = backup_path.read_bytes()
            if raw.startswith(_ENC_MAGIC):
                raw = _decrypt_bytes(raw)
            restored = gzip.decompress(raw)
            return self._integrity_check_bytes(restored)
        except Exception as exc:
            logger.warning("verify FAILED worker=%s path=%s: %s", worker, backup_path, exc)
            return False

    def _integrity_check(self, db_path: str) -> bool:
        try:
            conn = sqlite3.connect(db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception:
            return False

    def _integrity_check_bytes(self, db_bytes: bytes) -> bool:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(db_bytes)
            tmp_path = tmp.name
        try:
            return self._integrity_check(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _latest_backup(self, worker: str) -> Optional[str]:
        worker_dir = self.backup_root / worker
        if not worker_dir.exists():
            return None
        backups = sorted(
            [f for f in worker_dir.iterdir() if f.suffix in (".enc", ".gz") and not f.name.endswith(".meta.json")],
            key=lambda f: f.name,
            reverse=True,
        )
        return str(backups[0]) if backups else None

    def _prune(self, worker_db: WorkerDB) -> None:
        """Remove backups older than the retention policy."""
        daily_keep, weekly_keep, monthly_keep = RETENTION[worker_db.tier]
        worker_dir = self.backup_root / worker_db.worker
        if not worker_dir.exists():
            return

        backups = sorted(
            [f for f in worker_dir.iterdir()
             if not f.name.endswith(".meta.json") and f.suffix in (".enc", ".gz")],
            key=lambda f: f.name,
            reverse=True,
        )

        # Keep strategy: newest N daily, 1-per-week for weekly_keep weeks,
        # 1-per-month for monthly_keep months; delete everything else.
        keep = set()

        # Keep the most recent daily_keep backups unconditionally
        for f in backups[:daily_keep]:
            keep.add(f)

        # Keep one backup per ISO week for weekly_keep weeks
        seen_weeks: set[str] = set()
        for f in backups:
            try:
                ts_part = f.name.split("_")[1]  # YYYYMMDDTHHMMSSZ
                dt = datetime.strptime(ts_part, "%Y%m%dT%H%M%SZ")
                week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
                if week_key not in seen_weeks and len(seen_weeks) < weekly_keep:
                    seen_weeks.add(week_key)
                    keep.add(f)
            except Exception:
                pass

        # Keep one backup per calendar month for monthly_keep months
        seen_months: set[str] = set()
        for f in backups:
            try:
                ts_part = f.name.split("_")[1]
                dt = datetime.strptime(ts_part, "%Y%m%dT%H%M%SZ")
                month_key = f"{dt.year}-{dt.month:02d}"
                if month_key not in seen_months and len(seen_months) < monthly_keep:
                    seen_months.add(month_key)
                    keep.add(f)
            except Exception:
                pass

        deleted = 0
        for f in backups:
            if f not in keep:
                f.unlink(missing_ok=True)
                # Also remove sidecar meta
                meta = f.with_suffix("").with_suffix(".meta.json")
                meta.unlink(missing_ok=True)
                deleted += 1

        if deleted:
            logger.debug("pruned %d old backup(s) for worker=%s", deleted, worker_db.worker)
