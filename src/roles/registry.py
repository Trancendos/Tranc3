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
from typing import Dict, List, Optional, Tuple

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


def _emit_relations_event(
    actor_ai: str, location: str, sentiment: str, summary: str, reason: str, changed_at: float
) -> None:
    """Best-effort trigger into the AI-to-AI Relations activity feed.

    Role reassignment is exactly the kind of platform event the Relations
    feed / Location brochure want to surface ("X was assigned as the new
    Chief Financial Officer of Royal Bank of Arcadia"). Kept decoupled and
    swallowing all errors — `src/relations` is a separate, independently
    testable module, and a reassignment must never fail because the
    Relations registry is unavailable, mid-migration, or simply not
    imported in a given test/runtime context.

    This call happens after the role lock is released (see assign_ai/
    remove_ai), so under concurrent reassignments the Relations feed's own
    `ts` (stamped by `record_event` at call time) can land in a different
    order than `role_assignment_history.changed_at`. `changed_at` is
    threaded through into the event's `details` so the two systems share a
    canonical ordering key even if their own timestamps disagree.
    """
    try:
        from src.relations.registry import get_relations_registry

        get_relations_registry().record_event(
            actor_ai=actor_ai,
            event_type="system",
            location=location,
            sentiment=sentiment,
            summary=summary,
            details={"reason": reason, "changed_at": changed_at}
            if reason
            else {"changed_at": changed_at},
        )
    except Exception:
        pass


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
        # commit) can genuinely interleave across threads. Reads and writes
        # share one connection, so an uncommitted UPDATE is visible to any
        # other statement on that same connection — an unlocked reader could
        # observe a row that's been UPDATEd but not yet committed (and would
        # vanish if the transaction rolled back). An RLock (not a plain
        # Lock) guards every method, reads included, and is reentrant so
        # assign_ai/remove_ai can call the locked get_role() from within
        # their own critical section without deadlocking.
        self._lock = threading.RLock()
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
        self._migrate_renamed_lead_ais()

    # Retired `lead_ai` display names -> their current canonical replacement,
    # keyed by Location. INSERT OR IGNORE above never touches a row that
    # already exists, so a DB seeded before these three Locations' names were
    # reconciled to trance_one/platform_manifest.py's spelling (see
    # docs/governance/LOCATION-FUNCTIONS.md's 2026-07-24 verification-log
    # entry) would otherwise keep resolving to the old name forever, and
    # AI_NAME_TO_PROFILE_ID (src/personality/role_resolution.py) no longer
    # has an entry for it — silently dropping the assigned personality.
    _RENAMED_LEAD_AIS: Dict[str, Tuple[str, str]] = {
        "Infinity": ("The Guardian (Anchor: Orb of Orisis)", "The Guardian (Marcus Magnolia)"),
        "The Lab": ("The Dr. & Slime", "The Dr. (Nikolai O'denhime)"),
        "DocUtari": ("To be Defined", "Fiddsy"),
        "TateKing": ("Benji Tate & Sam King", "Benji Tate"),
        "Arcadian Exchange": ("The Porter Family", "Clarence Porter"),
    }

    def _migrate_renamed_lead_ais(self) -> None:
        """Backfill a persisted DB's stale `assigned_ai` values after a rename.

        Only rewrites a row still holding the exact retired name — an
        operator who has since manually reassigned that seat is left alone.
        Idempotent: once migrated, `assigned_ai` no longer matches
        `old_name` and this is a no-op on every later startup.
        """
        now = time.time()
        for location, (old_name, new_name) in self._RENAMED_LEAD_AIS.items():
            cur = self._conn.execute(
                "SELECT assigned_ai FROM role_assignments WHERE location = ?",
                (location,),
            )
            row = cur.fetchone()
            if row is None or row["assigned_ai"] != old_name:
                continue
            self._conn.execute(
                "UPDATE role_assignments SET assigned_ai = ?, assigned_at = ?, "
                "assigned_by = ? WHERE location = ?",
                (new_name, now, "system:rename_migration", location),
            )
            self._conn.execute(
                "INSERT INTO role_assignment_history "
                "(location, previous_ai, new_ai, changed_at, changed_by, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    location,
                    old_name,
                    new_name,
                    now,
                    "system:rename_migration",
                    "canonical lead_ai display name reconciled to trance_one/platform_manifest.py",
                ),
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
        with self._lock:
            cur = self._conn.execute(
                "SELECT location, job_description, assigned_ai, assigned_at, assigned_by "
                "FROM role_assignments ORDER BY location"
            )
            return [self._row_to_assignment(row) for row in cur.fetchall()]

    def get_role(self, location: str) -> Optional[RoleAssignment]:
        with self._lock:
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
            result: RoleAssignment = self.get_role(location)  # type: ignore[assignment]
        _emit_relations_event(
            actor_ai=ai_name,
            location=location,
            sentiment="positive",
            summary=f"{ai_name} was assigned as {result.job_description} of {location}",
            reason=reason,
            changed_at=now,
        )
        return result

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
            result: RoleAssignment = self.get_role(location)  # type: ignore[assignment]
        if previous_ai:
            _emit_relations_event(
                actor_ai=previous_ai,
                location=location,
                sentiment="neutral",
                summary=f"{previous_ai} was vacated from {result.job_description} of {location}",
                reason=reason,
                changed_at=now,
            )
        return result

    def get_history(self, location: str) -> List[AssignmentHistoryEntry]:
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            cur = self._conn.execute(
                "SELECT location, previous_ai, new_ai, changed_at, changed_by, reason "
                "FROM role_assignment_history WHERE location = ? "
                "ORDER BY changed_at DESC, id DESC",
                (location,),
            )
            rows = cur.fetchall()
        return [
            AssignmentHistoryEntry(
                location=row["location"],
                previous_ai=row["previous_ai"],
                new_ai=row["new_ai"],
                changed_at=row["changed_at"],
                changed_by=row["changed_by"],
                reason=row["reason"],
            )
            for row in rows
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
