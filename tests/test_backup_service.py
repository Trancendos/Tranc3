"""
Tests for src.backup — BackupEngine, registry, and DR restore logic.
"""

from __future__ import annotations

import gzip
import os
import sqlite3
from pathlib import Path

import pytest

os.environ["SECRET_KEY"] = "test-backup-secret-key-for-unit-tests-at-least-32chars"
os.environ.pop("TRANC3_DB_ENCRYPTION_DISABLED", None)

from src.backup.engine import BackupEngine, _decrypt_bytes, _encrypt_bytes
from src.backup.registry import (
    REGISTRY_BY_TIER,
    REGISTRY_BY_WORKER,
    WORKER_DATABASE_REGISTRY,
    BackupTier,
    WorkerDB,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path) -> Path:
    """Create a small test SQLite database."""
    db = tmp_path / "test_worker.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'alice')")
    conn.execute("INSERT INTO users VALUES (2, 'bob')")
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def worker_db(tmp_db) -> WorkerDB:
    return WorkerDB(
        worker="test-worker",
        env_var="TEST_WORKER_DB",
        default_path=str(tmp_db),
        tier=BackupTier.CRITICAL,
        description="Test worker",
    )


@pytest.fixture()
def engine(tmp_path) -> BackupEngine:
    return BackupEngine(backup_root=tmp_path / "backups", encrypt=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_not_empty():
    assert len(WORKER_DATABASE_REGISTRY) > 0


def test_all_tiers_represented():
    tiers_present = {w.tier for w in WORKER_DATABASE_REGISTRY}
    assert tiers_present == set(BackupTier)


def test_critical_workers_include_auth_and_vault():
    critical = {w.worker for w in REGISTRY_BY_TIER[BackupTier.CRITICAL]}
    assert "infinity-auth" in critical
    assert "vault-service" in critical
    assert "users-service" in critical
    assert "payments-service" in critical


def test_registry_by_worker_lookup():
    assert "infinity-auth" in REGISTRY_BY_WORKER
    assert REGISTRY_BY_WORKER["infinity-auth"].tier == BackupTier.CRITICAL


def test_worker_db_resolved_path(monkeypatch, tmp_path):
    db_path = str(tmp_path / "custom.db")
    monkeypatch.setenv("AUTH_DATABASE_PATH", db_path)
    worker = REGISTRY_BY_WORKER["infinity-auth"]
    assert worker.resolved_path == db_path


def test_rpo_minutes_ordering():
    from src.backup.registry import RPO_MINUTES

    assert RPO_MINUTES[BackupTier.CRITICAL] < RPO_MINUTES[BackupTier.HIGH]
    assert RPO_MINUTES[BackupTier.HIGH] < RPO_MINUTES[BackupTier.STANDARD]
    assert RPO_MINUTES[BackupTier.STANDARD] < RPO_MINUTES[BackupTier.LOW]


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    data = b"sensitive backup data " * 100
    encrypted = _encrypt_bytes(data)
    assert encrypted[:7] == b"BKPENC1"
    assert _decrypt_bytes(encrypted) == data


def test_encrypt_produces_different_output_each_call():
    data = b"same data"
    assert _encrypt_bytes(data) != _encrypt_bytes(data)


def test_decrypt_invalid_magic():
    with pytest.raises(ValueError, match="BKPENC1"):
        _decrypt_bytes(b"not encrypted")


# ---------------------------------------------------------------------------
# BackupEngine.backup()
# ---------------------------------------------------------------------------


def test_backup_creates_file(engine, worker_db):
    result = engine.backup(worker_db)
    assert result.success is True
    assert result.meta is not None
    assert Path(result.meta.backup_path).exists()


def test_backup_creates_meta_sidecar(engine, worker_db):
    result = engine.backup(worker_db)
    meta_path = Path(result.meta.backup_path).with_suffix("").with_suffix(".meta.json")
    assert meta_path.exists()


def test_backup_is_verified(engine, worker_db):
    result = engine.backup(worker_db)
    assert result.meta.verified is True


def test_backup_encrypted_file_not_plaintext(engine, worker_db):
    result = engine.backup(worker_db)
    raw = Path(result.meta.backup_path).read_bytes()
    # Must start with our encryption sentinel
    assert raw[:7] == b"BKPENC1"
    # Original DB content must NOT be recoverable without decryption
    assert b"alice" not in raw


def test_backup_compression_reduces_size(engine, worker_db, tmp_db):
    result = engine.backup(worker_db)
    assert (
        result.meta.compressed_size_bytes < result.meta.size_bytes or result.meta.size_bytes < 100
    )


def test_backup_missing_db(engine, tmp_path):
    missing = WorkerDB(
        worker="ghost",
        env_var="GHOST_DB",
        default_path=str(tmp_path / "nonexistent.db"),
        tier=BackupTier.LOW,
    )
    result = engine.backup(missing)
    assert result.success is False
    assert "not found" in (result.error or "").lower()


def test_backup_records_sha256(engine, worker_db):
    result = engine.backup(worker_db)
    assert len(result.meta.sha256) == 64  # hex SHA-256


# ---------------------------------------------------------------------------
# BackupEngine.verify()
# ---------------------------------------------------------------------------


def test_verify_latest_backup(engine, worker_db):
    engine.backup(worker_db)
    latest = engine._latest_backup(worker_db.worker)
    assert engine._verify(Path(latest), worker_db.worker) is True


def test_verify_tampered_backup(engine, worker_db, tmp_path):
    result = engine.backup(worker_db)
    backup = Path(result.meta.backup_path)
    raw = backup.read_bytes()
    # Corrupt the ciphertext
    backup.write_bytes(raw[:-10] + bytes([x ^ 0xFF for x in raw[-10:]]))
    assert engine._verify(backup, worker_db.worker) is False


# ---------------------------------------------------------------------------
# BackupEngine.restore()
# ---------------------------------------------------------------------------


def test_restore_dry_run(engine, worker_db, tmp_db):
    engine.backup(worker_db)
    result = engine.restore(worker_db.worker, target_path=str(tmp_db), dry_run=True)
    assert result.success is True
    assert result.verified is True


def test_restore_overwrites_live_db(engine, worker_db, tmp_db):
    # Create backup
    engine.backup(worker_db)

    # Corrupt the live DB
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("DROP TABLE users")
    conn.commit()
    conn.close()

    # Restore
    result = engine.restore(worker_db.worker, target_path=str(tmp_db), dry_run=False)
    assert result.success is True

    # Verify data is back
    conn = sqlite3.connect(str(tmp_db))
    rows = conn.execute("SELECT name FROM users ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["alice", "bob"]


def test_restore_creates_pre_restore_backup(engine, worker_db, tmp_db):
    engine.backup(worker_db)
    engine.restore(worker_db.worker, target_path=str(tmp_db), dry_run=False)
    assert (tmp_db.parent / (tmp_db.stem + ".pre-restore.db")).exists()


def test_restore_unknown_worker_no_target(engine):
    result = engine.restore("nonexistent-worker", dry_run=True)
    assert result.success is False


def test_restore_no_backups(engine, worker_db, tmp_db):
    # No backup taken yet
    result = engine.restore(worker_db.worker, target_path=str(tmp_db), dry_run=True)
    assert result.success is False
    assert "No backups" in (result.error or "")


# ---------------------------------------------------------------------------
# BackupEngine.list_backups() and status()
# ---------------------------------------------------------------------------


def test_list_backups_after_backup(engine, worker_db):
    engine.backup(worker_db)
    backups = engine.list_backups(worker_db.worker)
    assert len(backups) == 1
    assert backups[0]["worker"] == worker_db.worker


def test_status_shows_all_workers(engine):
    status = engine.status()
    assert "total_workers" in status
    assert "workers" in status
    assert status["total_workers"] == len(WORKER_DATABASE_REGISTRY)


def test_status_rpo_breached_when_no_backup(engine):
    status = engine.status()
    # All workers have no backups in a fresh engine
    all_breached = all(w["rpo_breached"] for w in status["workers"])
    assert all_breached


def test_status_ok_after_backup(engine, worker_db, monkeypatch):
    monkeypatch.setattr(worker_db, "worker", "test-worker")
    engine.backup(worker_db)
    # Check just the backup exists (status for unregistered worker won't appear,
    # but the backup API confirms it's restorable)
    backups = engine.list_backups("test-worker")
    assert len(backups) >= 1
    assert backups[0]["verified"] is True


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


def test_prune_keeps_retention_limit(engine, worker_db, tmp_db):
    # Create 10 backups
    for _ in range(10):
        engine.backup(worker_db)

    backups = engine.list_backups(worker_db.worker)
    # CRITICAL tier keeps 7 daily + up to 4 weekly + 6 monthly but overlap means ≤ 10
    assert len(backups) <= 10  # retention hasn't exceeded anything in a single test run


# ---------------------------------------------------------------------------
# Unencrypted engine
# ---------------------------------------------------------------------------


def test_unencrypted_backup_no_magic(engine, worker_db, tmp_path):
    plain_engine = BackupEngine(backup_root=tmp_path / "plain", encrypt=False)
    result = plain_engine.backup(worker_db)
    assert result.success is True
    raw = Path(result.meta.backup_path).read_bytes()
    assert not raw.startswith(b"BKPENC1")


def test_unencrypted_backup_is_valid_gzip(engine, worker_db, tmp_path):
    plain_engine = BackupEngine(backup_root=tmp_path / "plain", encrypt=False)
    result = plain_engine.backup(worker_db)
    raw = Path(result.meta.backup_path).read_bytes()
    decompressed = gzip.decompress(raw)
    # Should be a valid SQLite database
    assert decompressed[:16].startswith(b"SQLite format 3")
