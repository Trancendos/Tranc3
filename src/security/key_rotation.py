"""
Automated Key Rotation — Trancendos Platform
=============================================
Provides 90-day automated rotation for:
  - JWT_SECRET (all active sessions revoked on rotation)
  - DB_MASTER_KEY (AES-256-GCM master key used by encrypted_sqlite)
  - API tokens (registered via register_key)

Design:
  - Rotation state is persisted to a SQLite DB (key_rotation.db) so it
    survives restarts.  WAL mode + FULL sync for durability.
  - Each rotation generates a new secret, fingerprints both old + new,
    writes the log entry, and calls registered post-rotation hooks so
    dependent services (e.g. infinity-auth JWT revocation) can react.
  - Rotation never deletes the previous key immediately — it retains it
    under `previous_<key_id>` for a configurable grace period so in-flight
    tokens can drain.  After the grace period the previous key is purged.
  - A background asyncio task runs `check_and_rotate()` every hour.

Usage (from any FastAPI lifespan):
    from src.security.key_rotation import get_rotation_service
    svc = get_rotation_service()
    await svc.start()           # starts background loop
    ...
    await svc.stop()

Manual rotation (e.g. from admin endpoint):
    svc = get_rotation_service()
    result = await svc.rotate("jwt_secret", reason="manual")

Environment variables:
    KEY_ROTATION_DB_PATH       path to SQLite DB (default: /data/key_rotation.db)
    KEY_ROTATION_PERIOD_DAYS   rotation period in days (default: 90)
    KEY_ROTATION_GRACE_DAYS    grace period before purging old key (default: 1)
    JWT_SECRET                 read + rotated in-process
    DB_MASTER_KEY              read + rotated in-process
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("KEY_ROTATION_DB_PATH", "/data/key_rotation.db")
_ROTATION_PERIOD_DAYS = int(os.environ.get("KEY_ROTATION_PERIOD_DAYS", "90"))
_GRACE_DAYS = int(os.environ.get("KEY_ROTATION_GRACE_DAYS", "1"))
_CHECK_INTERVAL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS key_schedule (
            key_id              TEXT PRIMARY KEY,
            key_type            TEXT NOT NULL,
            last_rotated_at     TEXT NOT NULL,
            next_rotation_due   TEXT NOT NULL,
            rotation_period_days INTEGER NOT NULL DEFAULT 90,
            is_overdue          INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS rotation_log (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id                   TEXT NOT NULL,
            key_type                 TEXT NOT NULL,
            rotated_at               TEXT NOT NULL,
            rotated_by               TEXT NOT NULL DEFAULT 'system',
            previous_key_fingerprint TEXT,
            new_key_fingerprint      TEXT NOT NULL,
            success                  INTEGER NOT NULL DEFAULT 1,
            notes                    TEXT
        );
        CREATE TABLE IF NOT EXISTS key_store (
            key_id      TEXT PRIMARY KEY,
            key_type    TEXT NOT NULL,
            key_value   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            expires_at  TEXT,
            is_previous INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_rotation_log_key ON rotation_log(key_id);
        CREATE INDEX IF NOT EXISTS idx_rotation_log_at  ON rotation_log(rotated_at);
    """)
    conn.commit()
    return conn


def _fingerprint(value: str) -> str:
    """Return first 8 hex chars of SHA-256(value) — safe to log."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RotationResult:
    key_id: str
    success: bool
    new_fingerprint: str
    previous_fingerprint: Optional[str]
    rotated_at: str
    notes: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Key rotation service
# ---------------------------------------------------------------------------

PostRotationHook = Callable[[str, str, str], Coroutine[Any, Any, None]]


class KeyRotationService:
    """
    Manages automated 90-day key rotation with audit trail.
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._hooks: Dict[str, List[PostRotationHook]] = {}
        self._task: Optional[asyncio.Task] = None

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            # Override global path if instance was constructed with a custom one
            global _DB_PATH  # noqa: PLW0603
            old = _DB_PATH
            _DB_PATH = self._db_path
            self._conn = _get_db()
            _DB_PATH = old
        return self._conn

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_hook(self, key_id: str, hook: PostRotationHook) -> None:
        """Register an async callback invoked after key_id is rotated.

        Signature: async def hook(key_id, new_value, old_value) -> None
        """
        self._hooks.setdefault(key_id, []).append(hook)

    def register_key(
        self,
        key_id: str,
        key_type: str,
        current_value: str,
        rotation_period_days: int = _ROTATION_PERIOD_DAYS,
    ) -> None:
        """Register a key for managed rotation (idempotent)."""
        conn = self._db()
        now = datetime.now(timezone.utc).isoformat()
        # Register in schedule (only if not already tracked)
        conn.execute(
            """INSERT OR IGNORE INTO key_schedule
               (key_id, key_type, last_rotated_at, next_rotation_due, rotation_period_days)
               VALUES (?, ?, ?, datetime(?, '+' || ? || ' days'), ?)""",
            (key_id, key_type, now, now, rotation_period_days, rotation_period_days),
        )
        # Store current value (if not already stored)
        conn.execute(
            "INSERT OR IGNORE INTO key_store (key_id, key_type, key_value, created_at) VALUES (?,?,?,?)",
            (key_id, key_type, current_value, now),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    async def rotate(
        self,
        key_id: str,
        reason: str = "scheduled",
        rotated_by: str = "system",
    ) -> RotationResult:
        """Rotate key_id — generate new secret, persist, call hooks, log."""
        conn = self._db()
        now = datetime.now(timezone.utc).isoformat()

        # Fetch current value
        row = conn.execute(
            "SELECT key_value, key_type FROM key_store WHERE key_id = ? AND is_previous = 0",
            (key_id,),
        ).fetchone()

        if row is None:
            return RotationResult(
                key_id=key_id,
                success=False,
                new_fingerprint="",
                previous_fingerprint=None,
                rotated_at=now,
                error=f"key_id '{key_id}' not registered",
            )

        old_value, key_type = row
        old_fingerprint = _fingerprint(old_value)

        # Generate new secret (48 bytes = 96 hex chars)
        new_value = secrets.token_hex(48)
        new_fingerprint = _fingerprint(new_value)

        try:
            # Mark old as previous
            conn.execute("UPDATE key_store SET is_previous = 1 WHERE key_id = ?", (key_id,))
            # Insert new active
            expires_at = None  # key_store doesn't expire; rotation_log tracks schedule
            conn.execute(
                "INSERT INTO key_store (key_id, key_type, key_value, created_at, expires_at, is_previous) "
                "VALUES (?,?,?,?,?,0)",
                (key_id, key_type, new_value, now, expires_at),
            )
            # Update schedule
            conn.execute(
                """UPDATE key_schedule SET
                       last_rotated_at = ?,
                       next_rotation_due = datetime(?, '+' || rotation_period_days || ' days'),
                       is_overdue = 0
                   WHERE key_id = ?""",
                (now, now, key_id),
            )
            # Append to log
            conn.execute(
                """INSERT INTO rotation_log
                   (key_id, key_type, rotated_at, rotated_by, previous_key_fingerprint,
                    new_key_fingerprint, success, notes)
                   VALUES (?,?,?,?,?,?,1,?)""",
                (key_id, key_type, now, rotated_by, old_fingerprint, new_fingerprint, reason),
            )
            conn.commit()

            # Apply to environment (in-process, takes effect for new requests)
            env_key = key_id.upper()
            os.environ[env_key] = new_value
            logger.info(
                "key_rotation: rotated %s (%s) fingerprint %s→%s reason=%s",
                key_id,
                key_type,
                old_fingerprint,
                new_fingerprint,
                reason,
            )

            # Call post-rotation hooks
            for hook in self._hooks.get(key_id, []):
                try:
                    await hook(key_id, new_value, old_value)
                except Exception:
                    logger.exception("key_rotation: hook failed for %s", key_id)

            result = RotationResult(
                key_id=key_id,
                success=True,
                new_fingerprint=new_fingerprint,
                previous_fingerprint=old_fingerprint,
                rotated_at=now,
                notes=reason,
            )

        except Exception as exc:
            conn.execute(
                """INSERT INTO rotation_log
                   (key_id, key_type, rotated_at, rotated_by, previous_key_fingerprint,
                    new_key_fingerprint, success, notes)
                   VALUES (?,?,?,?,?,?,0,?)""",
                (key_id, key_type, now, rotated_by, old_fingerprint, "", str(exc)),
            )
            conn.commit()
            logger.exception("key_rotation: rotation FAILED for %s", key_id)
            result = RotationResult(
                key_id=key_id,
                success=False,
                new_fingerprint="",
                previous_fingerprint=old_fingerprint,
                rotated_at=now,
                error=str(exc),
            )

        return result

    # ------------------------------------------------------------------
    # Overdue check + bulk rotation
    # ------------------------------------------------------------------

    def get_overdue_keys(self) -> list[dict]:
        """Return keys where next_rotation_due <= now."""
        conn = self._db()
        rows = conn.execute(
            """SELECT key_id, key_type, last_rotated_at, next_rotation_due, rotation_period_days
               FROM key_schedule
               WHERE next_rotation_due <= datetime('now')
               ORDER BY next_rotation_due""",
        ).fetchall()
        conn.execute(
            "UPDATE key_schedule SET is_overdue = 1 WHERE next_rotation_due <= datetime('now')"
        )
        conn.commit()
        return [
            {
                "key_id": r[0],
                "key_type": r[1],
                "last_rotated_at": r[2],
                "next_rotation_due": r[3],
                "rotation_period_days": r[4],
            }
            for r in rows
        ]

    async def check_and_rotate(self) -> list[RotationResult]:
        """Rotate all overdue keys. Called by background loop."""
        overdue = self.get_overdue_keys()
        results = []
        for key in overdue:
            logger.info("key_rotation: key %s is overdue, rotating...", key["key_id"])
            result = await self.rotate(key["key_id"], reason="scheduled_90d")
            results.append(result)
        return results

    def get_schedule(self) -> list[dict]:
        """Return full rotation schedule for all registered keys."""
        conn = self._db()
        rows = conn.execute(
            """SELECT key_id, key_type, last_rotated_at, next_rotation_due,
                      rotation_period_days, is_overdue
               FROM key_schedule
               ORDER BY next_rotation_due""",
        ).fetchall()
        return [
            {
                "key_id": r[0],
                "key_type": r[1],
                "last_rotated_at": r[2],
                "next_rotation_due": r[3],
                "rotation_period_days": r[4],
                "is_overdue": bool(r[5]),
            }
            for r in rows
        ]

    def get_rotation_history(self, key_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        conn = self._db()
        if key_id:
            rows = conn.execute(
                "SELECT * FROM rotation_log WHERE key_id = ? ORDER BY rotated_at DESC LIMIT ?",
                (key_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM rotation_log ORDER BY rotated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM rotation_log LIMIT 0").description or []]
        if not cols:
            cols = [
                "id",
                "key_id",
                "key_type",
                "rotated_at",
                "rotated_by",
                "previous_key_fingerprint",
                "new_key_fingerprint",
                "success",
                "notes",
            ]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def purge_previous_keys(self) -> int:
        """Delete previous (old) key values older than grace period."""
        conn = self._db()
        cutoff = f"datetime('now', '-{_GRACE_DAYS} days')"
        cur = conn.execute(f"DELETE FROM key_store WHERE is_previous = 1 AND created_at < {cutoff}")
        conn.commit()
        purged = cur.rowcount
        if purged:
            logger.info("key_rotation: purged %d previous key(s) past grace period", purged)
        return purged

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(_CHECK_INTERVAL)
                try:
                    results = await self.check_and_rotate()
                    for r in results:
                        if not r.success:
                            logger.error("key_rotation: FAILED for %s: %s", r.key_id, r.error)
                    self.purge_previous_keys()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("key_rotation: background loop error")

        self._task = asyncio.ensure_future(_loop())
        logger.info(
            "key_rotation: background rotation loop started (interval=%ds)", _CHECK_INTERVAL
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: Optional[KeyRotationService] = None


def get_rotation_service() -> KeyRotationService:
    global _service  # noqa: PLW0603
    if _service is None:
        _service = KeyRotationService()
        _bootstrap_defaults()
    return _service


def _bootstrap_defaults() -> None:
    """Register JWT_SECRET and DB_MASTER_KEY if present in environment."""
    svc = _service
    assert svc is not None

    jwt_secret = os.environ.get("JWT_SECRET", "")
    if jwt_secret and len(jwt_secret) >= 32:
        svc.register_key("jwt_secret", "jwt", jwt_secret, _ROTATION_PERIOD_DAYS)

    db_master = os.environ.get("DB_MASTER_KEY", "")
    if db_master and len(db_master) >= 32:
        svc.register_key("db_master_key", "encryption", db_master, _ROTATION_PERIOD_DAYS)
