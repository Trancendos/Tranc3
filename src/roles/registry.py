# src/roles/registry.py
"""Role Assignment Registry.

Tracks which AI currently holds the functional Job Description for each of
the platform's 43 named Locations (`src/entities/platform.py`), and lets
operators add/remove/reassign that AI at runtime — distinct from the static
`lead_ai` field baked into `LocationEntity`, which records the *original*
canonical name, not the live, changeable holder of the role.

Backed by SQLite (zero-cost, self-hosted — no external DB dependency, per
this platform's architecture principles) so assignments and their audit
trail survive restarts. Every reassignment is recorded in
`role_assignment_history`, never overwritten.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.entities.platform import JOB_DESCRIPTIONS, PLATFORM_ENTITIES

DEFAULT_DB_PATH = Path("data/role_registry.db")


@dataclass
class RoleAssignment:
    location: str
    pillar: str
    primary_function: str
    job_description: str
    assigned_ai: Optional[str]
    assigned_at: float
    assigned_by: str


@dataclass
class AssignmentHistoryEntry:
    location: str
    previous_ai: Optional[str]
    new_ai: Optional[str]
    changed_at: float
    changed_by: str
    reason: str


class UnknownLocationError(KeyError):
    """Raised when a location name is not one of the 43 canonical entities."""


class RoleRegistry:
    """SQLite-backed registry of Location -> Job Description -> assigned AI."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # `check_same_thread=False` plus FastAPI's threadpool (routes are
        # plain `def`, not `async def`) means assign_ai/remove_ai's
        # read-modify-write (SELECT current -> UPDATE -> INSERT history ->
        # commit) can genuinely interleave across threads. This lock makes
        # each call atomic so a concurrent reassignment can't record a
        # `previous_ai` that's already stale by the time it commits.
        self._lock = threading.Lock()
        self._init_schema()
        self._seed_defaults()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_assignments (
                location TEXT PRIMARY KEY,
                job_description TEXT NOT NULL,
                assigned_ai TEXT,
                assigned_at REAL NOT NULL,
                assigned_by TEXT NOT NULL DEFAULT 'system'
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_assignment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                previous_ai TEXT,
                new_ai TEXT,
                changed_at REAL NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.commit()

    def _seed_defaults(self) -> None:
        """Seed one row per platform entity, initial holder = its canonical `lead_ai`.

        Uses INSERT OR IGNORE per-location rather than a table-level
        COUNT(*) skip-guard, so a location added to PLATFORM_ENTITIES after
        this registry's DB file already exists still gets backfilled on the
        next startup instead of being silently skipped forever.
        """
        now = time.time()
        rows = [
            (
                location,
                JOB_DESCRIPTIONS.get(location, entity.primary_function),
                entity.lead_ai,
                now,
                "system:seed",
            )
            for location, entity in PLATFORM_ENTITIES.items()
        ]
        self._conn.executemany(
            "INSERT OR IGNORE INTO role_assignments "
            "(location, job_description, assigned_ai, assigned_at, assigned_by) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def _row_to_assignment(self, row: sqlite3.Row) -> RoleAssignment:
        entity = PLATFORM_ENTITIES.get(row["location"])
        return RoleAssignment(
            location=row["location"],
            pillar=entity.pillar.value if entity else "",
            primary_function=entity.primary_function if entity else "",
            job_description=row["job_description"],
            assigned_ai=row["assigned_ai"],
            assigned_at=row["assigned_at"],
            assigned_by=row["assigned_by"],
        )

    def list_roles(self) -> List[RoleAssignment]:
        cur = self._conn.execute(
            "SELECT location, job_description, assigned_ai, assigned_at, assigned_by "
            "FROM role_assignments ORDER BY location"
        )
        return [self._row_to_assignment(row) for row in cur.fetchall()]

    def get_role(self, location: str) -> Optional[RoleAssignment]:
        cur = self._conn.execute(
            "SELECT location, job_description, assigned_ai, assigned_at, assigned_by "
            "FROM role_assignments WHERE location = ?",
            (location,),
        )
        row = cur.fetchone()
        return self._row_to_assignment(row) if row else None

    def assign_ai(
        self,
        location: str,
        ai_name: str,
        changed_by: str = "operator",
        reason: str = "",
    ) -> RoleAssignment:
        """Assign (or reassign) an AI to a location's Job Description."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            current = self.get_role(location)
            previous_ai = current.assigned_ai if current else None
            now = time.time()
            self._conn.execute(
                "UPDATE role_assignments SET assigned_ai = ?, assigned_at = ?, assigned_by = ? "
                "WHERE location = ?",
                (ai_name, now, changed_by, location),
            )
            self._conn.execute(
                "INSERT INTO role_assignment_history "
                "(location, previous_ai, new_ai, changed_at, changed_by, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (location, previous_ai, ai_name, now, changed_by, reason),
            )
            self._conn.commit()
            return self.get_role(location)  # type: ignore[return-value]

    def remove_ai(
        self,
        location: str,
        changed_by: str = "operator",
        reason: str = "",
    ) -> RoleAssignment:
        """Vacate a location's Job Description — leaves the role unassigned."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            current = self.get_role(location)
            previous_ai = current.assigned_ai if current else None
            now = time.time()
            self._conn.execute(
                "UPDATE role_assignments SET assigned_ai = NULL, assigned_at = ?, "
                "assigned_by = ? WHERE location = ?",
                (now, changed_by, location),
            )
            self._conn.execute(
                "INSERT INTO role_assignment_history "
                "(location, previous_ai, new_ai, changed_at, changed_by, reason) "
                "VALUES (?, ?, NULL, ?, ?, ?)",
                (location, previous_ai, now, changed_by, reason or "unassigned"),
            )
            self._conn.commit()
            return self.get_role(location)  # type: ignore[return-value]

    def get_history(self, location: str) -> List[AssignmentHistoryEntry]:
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        cur = self._conn.execute(
            "SELECT location, previous_ai, new_ai, changed_at, changed_by, reason "
            "FROM role_assignment_history WHERE location = ? "
            "ORDER BY changed_at DESC, id DESC",
            (location,),
        )
        return [
            AssignmentHistoryEntry(
                location=row["location"],
                previous_ai=row["previous_ai"],
                new_ai=row["new_ai"],
                changed_at=row["changed_at"],
                changed_by=row["changed_by"],
                reason=row["reason"],
            )
            for row in cur.fetchall()
        ]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[RoleRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> RoleRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_devocity()`, `get_library()`, `get_marketplace()`)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = RoleRegistry()
    return _registry
