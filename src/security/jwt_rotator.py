"""Automated JWT secret rotation — RSK-001 (JWT compromise mitigation).

Rotates JWT signing secrets on a schedule, invalidates old tokens gracefully
with a transition window, and records rotation events to The Observatory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

DB_PATH = Path("./data/jwt_rotation.db")
ROTATION_INTERVAL_HOURS = int(os.getenv("JWT_ROTATION_INTERVAL_HOURS", "720"))  # 30 days
TRANSITION_WINDOW_HOURS = int(os.getenv("JWT_TRANSITION_WINDOW_HOURS", "24"))


class JWTRotator:
    """Manages JWT secret rotation with graceful transition windows."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jwt_secrets (
                    secret_id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    rotated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS rotation_log (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    details TEXT
                );
            """)

    def _log_event(self, event_type: str, details: str = "") -> None:
        import uuid
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO rotation_log (event_id, event_type, occurred_at, details) VALUES (?,?,?,?)",
                (str(uuid.uuid4()), event_type, datetime.now(timezone.utc).isoformat(), details),
            )

    def generate_secret(self) -> str:
        return secrets.token_hex(64)

    def rotate(self) -> str:
        """Generate new JWT secret, deactivate old ones after transition window."""
        import hashlib
        import uuid

        new_secret = self.generate_secret()
        secret_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ROTATION_INTERVAL_HOURS + TRANSITION_WINDOW_HOURS)

        # Mark all current active secrets as transitioning (they stay valid during window)
        with self._conn() as conn:
            conn.execute(
                "UPDATE jwt_secrets SET rotated_at = ? WHERE is_active = 1 AND rotated_at IS NULL",
                (now.isoformat(),),
            )
            # Insert new secret (store only hash for audit — actual secret goes to vault)
            conn.execute(
                "INSERT INTO jwt_secrets (secret_id, secret_hash, created_at, expires_at) VALUES (?,?,?,?)",
                (
                    secret_id,
                    hashlib.sha256(new_secret.encode()).hexdigest()[:16],
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )

        self._log_event("rotation", f"New secret {secret_id[:8]}... created; transition window {TRANSITION_WINDOW_HOURS}h")
        logger.info("JWT secret rotated. Secret ID: %s, expires: %s", secret_id, expires_at)
        return new_secret

    def cleanup_expired(self) -> int:
        """Remove secrets past their transition window."""
        now = datetime.now(timezone.utc)
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM jwt_secrets WHERE expires_at < ? AND is_active = 0",
                (now.isoformat(),),
            )
            deleted = cursor.rowcount
        if deleted:
            self._log_event("cleanup", f"Removed {deleted} expired secrets")
        return deleted

    def should_rotate(self) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM jwt_secrets WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return True
        last_rotation = datetime.fromisoformat(row["created_at"])
        age_hours = (datetime.now(timezone.utc) - last_rotation).total_seconds() / 3600
        return age_hours >= ROTATION_INTERVAL_HOURS

    async def rotation_loop(self) -> None:
        """Background task: check and rotate JWT secrets on schedule."""
        logger.info("JWT rotation loop started (interval: %dh)", ROTATION_INTERVAL_HOURS)
        while True:
            try:
                if self.should_rotate():
                    new_secret = self.rotate()
                    # Push to vault if available
                    try:
                        from src.security.vault_client import get_vault_client
                        client = get_vault_client()
                        await client.set_secret("jwt-secret", new_secret)
                        logger.info("New JWT secret pushed to vault")
                    except Exception as e:
                        logger.warning("Could not push JWT secret to vault: %s", e)
                self.cleanup_expired()
            except Exception as e:
                logger.error("JWT rotation error: %s", e)
            await asyncio.sleep(3600)  # Check every hour

    def rotation_status(self) -> dict:
        with self._conn() as conn:
            active = conn.execute(
                "SELECT COUNT(*) as cnt FROM jwt_secrets WHERE is_active = 1"
            ).fetchone()["cnt"]
            last = conn.execute(
                "SELECT created_at FROM jwt_secrets WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        last_rotation = last["created_at"] if last else None
        age_hours = None
        if last_rotation:
            age_hours = round((datetime.now(timezone.utc) - datetime.fromisoformat(last_rotation)).total_seconds() / 3600, 1)
        return {
            "active_secrets": active,
            "last_rotation": last_rotation,
            "age_hours": age_hours,
            "rotation_interval_hours": ROTATION_INTERVAL_HOURS,
            "needs_rotation": self.should_rotate(),
        }


_rotator: JWTRotator | None = None


def get_rotator() -> JWTRotator:
    global _rotator
    if _rotator is None:
        _rotator = JWTRotator()
    return _rotator
