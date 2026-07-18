# src/deployment_modes/registry.py
"""Deployment Mode Registry.

Tracks, per platform Location (`src/entities/platform.py`), which of the
three deployment modes it currently runs under, and the on-demand
provisioning state of its Dev/UAT environments. This encodes the platform's
actual, settled architecture (not an open question):

  - **Cloud Only** — the default for every Location today. Not an
    architectural preference: the founder's local server needs repair or
    replacement money that isn't available yet, so Local/Self-Hosted isn't
    viable until that funding exists.
  - **Hybrid** — part cloud, part local. A future state once some local
    capacity exists.
  - **Local (Self-Hosted)** — fully on owned hardware. Blocked purely on
    server funding, not a rejection of self-hosting.

Each Location also carries Dev, UAT, and Prod **per mode**: provisioning
state is scoped to (Location, mode), not just Location, so switching a
Location from Cloud Only to Hybrid/Local doesn't silently carry over a
Dev/UAT environment's provisioned state from the old mode — the new mode
starts with its own fresh, unprovisioned Dev/UAT (Prod is always-on
regardless of mode). Prod is never gated by this registry — it's seeded
provisioned and can't be deprovisioned here. Dev and UAT are NOT standing
environments: they're provisioned on demand, only once Think Tank
(Trancendos AI's R&D centre) has actually scoped R&D work that needs them
(`scoped_by`), and deprovisioned again once that work is done.

Backed by SQLite (zero-cost, self-hosted — no external DB dependency, per
this platform's architecture principles) so mode/provisioning state and
their audit trails survive restarts. Mirrors the Role Assignment Registry's
shape (`src/roles/registry.py`) — SQLite-backed, module-level singleton,
full history tables, never overwritten.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from src.entities.platform import PLATFORM_ENTITIES

DEFAULT_DB_PATH = Path("data/deployment_mode_registry.db")


class DeploymentMode(str, Enum):
    CLOUD_ONLY = "cloud_only"
    HYBRID = "hybrid"
    LOCAL = "local"


class Environment(str, Enum):
    DEV = "dev"
    UAT = "uat"
    PROD = "prod"


# Prod is always-on — not gated by on-demand provisioning. Attempting to
# provision/deprovision it through this registry is a caller error.
_ON_DEMAND_ENVIRONMENTS = (Environment.DEV, Environment.UAT)


@dataclass
class ModeState:
    location: str
    mode: DeploymentMode
    changed_at: float
    changed_by: str
    reason: str


@dataclass
class ModeHistoryEntry:
    location: str
    previous_mode: Optional[DeploymentMode]
    new_mode: DeploymentMode
    changed_at: float
    changed_by: str
    reason: str


@dataclass
class EnvironmentState:
    location: str
    mode: DeploymentMode
    environment: Environment
    provisioned: bool
    provisioned_at: Optional[float]
    scoped_by: str
    changed_by: str
    reason: str


@dataclass
class EnvironmentHistoryEntry:
    location: str
    mode: DeploymentMode
    environment: Environment
    action: str  # "provisioned" | "deprovisioned"
    changed_at: float
    changed_by: str
    scoped_by: str
    reason: str


class UnknownLocationError(KeyError):
    """Raised when a location name is not one of the 43 canonical entities."""


class ProdNotOnDemandError(ValueError):
    """Raised when Prod (always-on) is passed to provision/deprovision."""


class DeploymentModeRegistry:
    """SQLite-backed registry of Location -> deployment mode + env provisioning."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Same rationale as RoleRegistry: check_same_thread=False + FastAPI's
        # threadpool (sync `def` handlers) means reads/writes can interleave
        # across threads on one shared connection. An RLock guards every
        # method, reentrant so e.g. set_mode can call the locked get_mode()
        # from within its own critical section without deadlocking.
        self._lock = threading.RLock()
        self._init_schema()
        self._seed_defaults()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS location_deployment_mode (
                location TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                changed_at REAL NOT NULL,
                changed_by TEXT NOT NULL DEFAULT 'system',
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS location_deployment_mode_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                previous_mode TEXT,
                new_mode TEXT NOT NULL,
                changed_at REAL NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS location_environment (
                location TEXT NOT NULL,
                mode TEXT NOT NULL,
                environment TEXT NOT NULL,
                provisioned INTEGER NOT NULL,
                provisioned_at REAL,
                scoped_by TEXT NOT NULL DEFAULT '',
                changed_by TEXT NOT NULL DEFAULT 'system',
                reason TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (location, mode, environment)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS location_environment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                mode TEXT NOT NULL,
                environment TEXT NOT NULL,
                action TEXT NOT NULL,
                changed_at REAL NOT NULL,
                changed_by TEXT NOT NULL,
                scoped_by TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.commit()

    def _seed_defaults(self) -> None:
        """Seed one mode row (Cloud Only) per platform entity, and three
        environment rows (Dev/UAT unprovisioned, Prod always-provisioned)
        per (entity, mode) combination — so switching modes later finds a
        fresh, correctly-scoped Dev/UAT already waiting, never a stale row
        carried over from a different mode.

        Uses INSERT OR IGNORE per-row rather than a table-level skip-guard,
        so a location added to PLATFORM_ENTITIES after this registry's DB
        file already exists still gets backfilled on the next startup
        instead of being silently skipped forever.
        """
        now = time.time()
        mode_rows = [
            (location, DeploymentMode.CLOUD_ONLY.value, now, "system:seed", "")
            for location in PLATFORM_ENTITIES
        ]
        self._conn.executemany(
            "INSERT OR IGNORE INTO location_deployment_mode "
            "(location, mode, changed_at, changed_by, reason) VALUES (?, ?, ?, ?, ?)",
            mode_rows,
        )
        env_rows = []
        for location in PLATFORM_ENTITIES:
            for mode in DeploymentMode:
                for env in Environment:
                    provisioned = env == Environment.PROD
                    env_rows.append(
                        (
                            location,
                            mode.value,
                            env.value,
                            1 if provisioned else 0,
                            now if provisioned else None,
                            "",
                            "system:seed",
                            "always-on" if provisioned else "",
                        )
                    )
        self._conn.executemany(
            "INSERT OR IGNORE INTO location_environment "
            "(location, mode, environment, provisioned, provisioned_at, scoped_by, "
            "changed_by, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            env_rows,
        )
        self._conn.commit()

    def _row_to_mode_state(self, row: sqlite3.Row) -> ModeState:
        return ModeState(
            location=row["location"],
            mode=DeploymentMode(row["mode"]),
            changed_at=row["changed_at"],
            changed_by=row["changed_by"],
            reason=row["reason"],
        )

    def list_modes(self) -> List[ModeState]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT location, mode, changed_at, changed_by, reason "
                "FROM location_deployment_mode ORDER BY location"
            )
            return [self._row_to_mode_state(row) for row in cur.fetchall()]

    def get_mode(self, location: str) -> Optional[ModeState]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT location, mode, changed_at, changed_by, reason "
                "FROM location_deployment_mode WHERE location = ?",
                (location,),
            )
            row = cur.fetchone()
            return self._row_to_mode_state(row) if row else None

    def _current_mode(self, location: str) -> DeploymentMode:
        """Internal helper — assumes `location` has already been validated
        against PLATFORM_ENTITIES and _seed_defaults has run, so a mode row
        always exists."""
        state = self.get_mode(location)
        assert state is not None  # seeded for every PLATFORM_ENTITIES key
        return state.mode

    def set_mode(
        self,
        location: str,
        mode: DeploymentMode,
        changed_by: str = "operator",
        reason: str = "",
    ) -> ModeState:
        """Set (or change) a Location's deployment mode.

        Does not touch location_environment — Dev/UAT/Prod rows already
        exist for every mode (seeded upfront by _seed_defaults), so the
        newly-active mode's environments are simply whatever they were last
        left as under that mode, independent of the mode being switched
        away from.
        """
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            current = self.get_mode(location)
            previous_mode = current.mode.value if current else None
            now = time.time()
            self._conn.execute(
                "UPDATE location_deployment_mode SET mode = ?, changed_at = ?, "
                "changed_by = ?, reason = ? WHERE location = ?",
                (mode.value, now, changed_by, reason, location),
            )
            self._conn.execute(
                "INSERT INTO location_deployment_mode_history "
                "(location, previous_mode, new_mode, changed_at, changed_by, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (location, previous_mode, mode.value, now, changed_by, reason),
            )
            self._conn.commit()
            result: ModeState = self.get_mode(location)  # type: ignore[assignment]
        return result

    def get_mode_history(self, location: str) -> List[ModeHistoryEntry]:
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            cur = self._conn.execute(
                "SELECT location, previous_mode, new_mode, changed_at, changed_by, reason "
                "FROM location_deployment_mode_history WHERE location = ? "
                "ORDER BY changed_at DESC, id DESC",
                (location,),
            )
            rows = cur.fetchall()
        return [
            ModeHistoryEntry(
                location=row["location"],
                previous_mode=DeploymentMode(row["previous_mode"])
                if row["previous_mode"]
                else None,
                new_mode=DeploymentMode(row["new_mode"]),
                changed_at=row["changed_at"],
                changed_by=row["changed_by"],
                reason=row["reason"],
            )
            for row in rows
        ]

    def _row_to_env_state(self, row: sqlite3.Row) -> EnvironmentState:
        return EnvironmentState(
            location=row["location"],
            mode=DeploymentMode(row["mode"]),
            environment=Environment(row["environment"]),
            provisioned=bool(row["provisioned"]),
            provisioned_at=row["provisioned_at"],
            scoped_by=row["scoped_by"],
            changed_by=row["changed_by"],
            reason=row["reason"],
        )

    def list_environments(self, location: str) -> List[EnvironmentState]:
        """Dev/UAT/Prod state for `location` under its *current* mode."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            mode = self._current_mode(location)
            cur = self._conn.execute(
                "SELECT location, mode, environment, provisioned, provisioned_at, scoped_by, "
                "changed_by, reason FROM location_environment "
                "WHERE location = ? AND mode = ? ORDER BY environment",
                (location, mode.value),
            )
            return [self._row_to_env_state(row) for row in cur.fetchall()]

    def get_environment(
        self, location: str, environment: Environment
    ) -> Optional[EnvironmentState]:
        """State of one environment for `location` under its *current* mode."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            mode = self._current_mode(location)
            cur = self._conn.execute(
                "SELECT location, mode, environment, provisioned, provisioned_at, scoped_by, "
                "changed_by, reason FROM location_environment "
                "WHERE location = ? AND mode = ? AND environment = ?",
                (location, mode.value, environment.value),
            )
            row = cur.fetchone()
            return self._row_to_env_state(row) if row else None

    def provision_environment(
        self,
        location: str,
        environment: Environment,
        scoped_by: str,
        changed_by: str = "operator",
        reason: str = "",
    ) -> EnvironmentState:
        """Provision Dev or UAT for a Location, under its *current* mode —
        must be tied to a Think Tank R&D scoping reference (`scoped_by`),
        matching the platform policy that these are never standing
        environments."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        if environment not in _ON_DEMAND_ENVIRONMENTS:
            raise ProdNotOnDemandError(f"{environment.value} is always-on, not on-demand")
        scoped_by = scoped_by.strip()
        if not scoped_by:
            raise ValueError("scoped_by is required — Dev/UAT only provision against R&D scoping")
        with self._lock:
            mode = self._current_mode(location)
            now = time.time()
            self._conn.execute(
                "UPDATE location_environment SET provisioned = 1, provisioned_at = ?, "
                "scoped_by = ?, changed_by = ?, reason = ? "
                "WHERE location = ? AND mode = ? AND environment = ?",
                (now, scoped_by, changed_by, reason, location, mode.value, environment.value),
            )
            self._conn.execute(
                "INSERT INTO location_environment_history "
                "(location, mode, environment, action, changed_at, changed_by, scoped_by, reason) "
                "VALUES (?, ?, ?, 'provisioned', ?, ?, ?, ?)",
                (location, mode.value, environment.value, now, changed_by, scoped_by, reason),
            )
            self._conn.commit()
            result: EnvironmentState = self.get_environment(location, environment)  # type: ignore[assignment]
        return result

    def deprovision_environment(
        self,
        location: str,
        environment: Environment,
        changed_by: str = "operator",
        reason: str = "",
    ) -> EnvironmentState:
        """Tear down Dev or UAT (under the Location's *current* mode) once
        its scoped R&D work is done."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        if environment not in _ON_DEMAND_ENVIRONMENTS:
            raise ProdNotOnDemandError(f"{environment.value} is always-on, not on-demand")
        with self._lock:
            mode = self._current_mode(location)
            # Preserve the scope this environment was torn down from in the
            # audit trail — writing an empty scoped_by here would lose the
            # one piece of history most worth keeping (what R&D work this
            # Dev/UAT was for).
            current = self.get_environment(location, environment)
            previous_scoped_by = current.scoped_by if current else ""
            now = time.time()
            self._conn.execute(
                "UPDATE location_environment SET provisioned = 0, provisioned_at = NULL, "
                "scoped_by = '', changed_by = ?, reason = ? "
                "WHERE location = ? AND mode = ? AND environment = ?",
                (changed_by, reason, location, mode.value, environment.value),
            )
            self._conn.execute(
                "INSERT INTO location_environment_history "
                "(location, mode, environment, action, changed_at, changed_by, scoped_by, reason) "
                "VALUES (?, ?, ?, 'deprovisioned', ?, ?, ?, ?)",
                (
                    location,
                    mode.value,
                    environment.value,
                    now,
                    changed_by,
                    previous_scoped_by,
                    reason,
                ),
            )
            self._conn.commit()
            result: EnvironmentState = self.get_environment(location, environment)  # type: ignore[assignment]
        return result

    def get_environment_history(
        self, location: str, environment: Optional[Environment] = None
    ) -> List[EnvironmentHistoryEntry]:
        """Full provisioning history for `location`, across every mode it
        has ever run under (each entry carries its own `mode`) — mode
        switches don't erase or hide prior audit trail."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            if environment is not None:
                cur = self._conn.execute(
                    "SELECT location, mode, environment, action, changed_at, changed_by, "
                    "scoped_by, reason FROM location_environment_history "
                    "WHERE location = ? AND environment = ? ORDER BY changed_at DESC, id DESC",
                    (location, environment.value),
                )
            else:
                cur = self._conn.execute(
                    "SELECT location, mode, environment, action, changed_at, changed_by, "
                    "scoped_by, reason FROM location_environment_history "
                    "WHERE location = ? ORDER BY changed_at DESC, id DESC",
                    (location,),
                )
            rows = cur.fetchall()
        return [
            EnvironmentHistoryEntry(
                location=row["location"],
                mode=DeploymentMode(row["mode"]),
                environment=Environment(row["environment"]),
                action=row["action"],
                changed_at=row["changed_at"],
                changed_by=row["changed_by"],
                scoped_by=row["scoped_by"],
                reason=row["reason"],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[DeploymentModeRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> DeploymentModeRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_registry()` in src/roles/registry.py, etc.)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = DeploymentModeRegistry()
    return _registry
