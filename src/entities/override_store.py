"""
src/entities/override_store.py — Cached reader for Infinity-Admin entity_overrides.

Proactive: workers poll the same SQLite file as infinity-admin-service (or refresh
from INFINITY_ADMIN_URL) so renamed entities appear in /health without redeploy.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from src.database.encrypted_sqlite import connect as sqlite3_connect
import time
from pathlib import Path
from typing import Dict

from src.entities.effective import build_overrides_map

logger = logging.getLogger(__name__)

_CACHE_TTL = float(os.environ.get("ENTITY_OVERRIDES_CACHE_TTL", "60"))
_all_by_pid_cache: dict[str, tuple[float, Dict[str, Dict[str, str]]]] = {}


def _db_path() -> Path:
    return Path(
        os.environ.get(
            "ENTITY_OVERRIDES_DB",
            os.environ.get("INFINITY_ADMIN_DB_PATH", "data/infinity_admin.db"),
        )
    )


def overrides_enabled() -> bool:
    return _db_path().is_file()


def load_all_overrides_by_pid(*, force: bool = False) -> Dict[str, Dict[str, str]]:
    """Load all entity_overrides grouped by location_pid (TTL cache)."""
    cache_key = str(_db_path().resolve())
    now = time.monotonic()
    if not force and cache_key in _all_by_pid_cache:
        ts, data = _all_by_pid_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    result: Dict[str, Dict[str, str]] = {}
    path = _db_path()
    if not path.is_file():
        _all_by_pid_cache[cache_key] = (now, result)
        return result

    try:
        conn = sqlite3_connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT location_pid, entity_type, slot, override_name FROM entity_overrides"
        ).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("override_store: cannot read %s: %s", path, exc)
        _all_by_pid_cache[cache_key] = (now, result)
        return result

    by_pid: Dict[str, list] = {}
    for row in rows:
        pid = row["location_pid"]
        by_pid.setdefault(pid, []).append(row)

    for pid, pid_rows in by_pid.items():
        result[pid] = build_overrides_map(pid_rows)

    _all_by_pid_cache[cache_key] = (now, result)
    return result


def load_overrides_for_pid(pid: str, *, force: bool = False) -> Dict[str, str]:
    """Overrides for one PID."""
    return load_all_overrides_by_pid(force=force).get(pid, {})


def invalidate_override_cache() -> None:
    """Call after admin rename (or on Sentinel entity_renamed hook)."""
    _all_by_pid_cache.clear()
