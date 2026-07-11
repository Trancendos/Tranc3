# src/access/registry.py
"""Location Access & Subscription Registry.

Not every user should have every Location's functionality switched on by
default. This registry tracks, per user, which of the platform's 43 named
Locations they have actually opted into — a genuine subscribe/consent step,
not an implicit "everything is on" default — so that:

- Locations carrying enhanced compliance obligations (financial, health,
  legal-adjacent functionality) only activate for a user once they've
  explicitly agreed to that Location's Terms & Conditions / Acceptable Use
  Policy, at a specific, trackable policy version.
- If the Acceptable Use Policy changes (`CURRENT_TERMS_VERSION` bumps),
  previously-subscribed users are not silently carried over — they must
  re-consent to the new version before the Location reactivates for them.
- There's an auditable record of who agreed to what, and when, matching
  this platform's audit-trail conventions (Role Registry's
  `role_assignment_history`, Relations' `activity_events`).

Backed by SQLite (zero-cost, self-hosted, matching this platform's
architecture principles — same pattern as the Role Assignment Registry and
the Relations Registry).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.entities.platform import PLATFORM_ENTITIES

DEFAULT_DB_PATH = Path("data/access_registry.db")

# Bumping this forces every existing subscriber to re-consent — see
# docs/governance/ACCEPTABLE-USE-POLICY.md, whose own version header must
# be kept in sync with this constant.
CURRENT_TERMS_VERSION = "1.0"


class UnknownLocationError(KeyError):
    """Raised when a location name is not one of the 43 canonical entities."""


class TermsNotAcceptedError(ValueError):
    """Raised when a subscribe attempt doesn't explicitly accept the terms."""


class StaleTermsVersionError(ValueError):
    """Raised when a subscribe attempt cites an outdated terms_version — the
    caller must fetch and accept CURRENT_TERMS_VERSION instead."""


@dataclass
class LocationSubscription:
    user_id: str
    location: str
    status: str  # "active" | "revoked"
    terms_version: str
    subscribed_at: float
    revoked_at: Optional[float]

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class AccessRegistry:
    """SQLite-backed registry of User -> subscribed Locations."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Reentrant so subscribe()/unsubscribe() can call the locked
        # get_subscription() internally without deadlocking; every method
        # (reads included) takes it, since reads and writes share one
        # connection (check_same_thread=False) and an unlocked reader could
        # otherwise observe an uncommitted write.
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS location_subscriptions (
                user_id TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                terms_version TEXT NOT NULL,
                subscribed_at REAL NOT NULL,
                revoked_at REAL,
                PRIMARY KEY (user_id, location)
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subs_user ON location_subscriptions(user_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subs_location ON location_subscriptions(location)"
        )
        self._conn.commit()

    def _row_to_subscription(self, row: sqlite3.Row) -> LocationSubscription:
        return LocationSubscription(
            user_id=row["user_id"],
            location=row["location"],
            status=row["status"],
            terms_version=row["terms_version"],
            subscribed_at=row["subscribed_at"],
            revoked_at=row["revoked_at"],
        )

    def get_subscription(self, user_id: str, location: str) -> Optional[LocationSubscription]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM location_subscriptions WHERE user_id = ? AND location = ?",
                (user_id, location),
            )
            row = cur.fetchone()
        return self._row_to_subscription(row) if row else None

    def is_subscribed(self, user_id: str, location: str) -> bool:
        sub = self.get_subscription(user_id, location)
        return sub is not None and sub.is_active

    def subscribe(
        self,
        user_id: str,
        location: str,
        accepted_terms: bool,
        terms_version: str,
    ) -> LocationSubscription:
        """Opt a user into a Location's functionality.

        Requires explicit, current-version consent — `accepted_terms` must
        be True and `terms_version` must match `CURRENT_TERMS_VERSION`, so a
        client can't silently "auto-accept" a policy it never actually
        fetched and displayed to the user.
        """
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        if not accepted_terms:
            raise TermsNotAcceptedError("accepted_terms must be true to subscribe to a Location")
        if terms_version != CURRENT_TERMS_VERSION:
            raise StaleTermsVersionError(
                f"terms_version {terms_version!r} is stale — current version is "
                f"{CURRENT_TERMS_VERSION!r}; fetch and accept the current Acceptable "
                f"Use Policy before subscribing"
            )
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO location_subscriptions "
                "(user_id, location, status, terms_version, subscribed_at, revoked_at) "
                "VALUES (?, ?, 'active', ?, ?, NULL) "
                "ON CONFLICT(user_id, location) DO UPDATE SET "
                "status = 'active', terms_version = excluded.terms_version, "
                "subscribed_at = excluded.subscribed_at, revoked_at = NULL",
                (user_id, location, terms_version, now),
            )
            self._conn.commit()
            return self.get_subscription(user_id, location)  # type: ignore[return-value]

    def unsubscribe(self, user_id: str, location: str) -> LocationSubscription:
        """Revoke a user's subscription — the row is kept (status='revoked'),
        never deleted, matching this platform's audit-trail conventions."""
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE location_subscriptions SET status = 'revoked', revoked_at = ? "
                "WHERE user_id = ? AND location = ?",
                (now, user_id, location),
            )
            self._conn.commit()
            existing = self.get_subscription(user_id, location)
            if existing is None:
                # Never subscribed — record an explicit revoked row anyway so
                # "never subscribed" and "subscribed then revoked" both leave
                # a queryable trace, and repeat calls are idempotent.
                self._conn.execute(
                    "INSERT INTO location_subscriptions "
                    "(user_id, location, status, terms_version, subscribed_at, revoked_at) "
                    "VALUES (?, ?, 'revoked', '', ?, ?)",
                    (user_id, location, now, now),
                )
                self._conn.commit()
                existing = self.get_subscription(user_id, location)
            return existing  # type: ignore[return-value]

    def list_user_subscriptions(
        self, user_id: str, active_only: bool = True
    ) -> List[LocationSubscription]:
        with self._lock:
            if active_only:
                cur = self._conn.execute(
                    "SELECT * FROM location_subscriptions WHERE user_id = ? AND status = 'active' "
                    "ORDER BY location",
                    (user_id,),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM location_subscriptions WHERE user_id = ? ORDER BY location",
                    (user_id,),
                )
            rows = cur.fetchall()
        return [self._row_to_subscription(row) for row in rows]

    def list_location_subscribers(
        self, location: str, active_only: bool = True
    ) -> List[LocationSubscription]:
        if location not in PLATFORM_ENTITIES:
            raise UnknownLocationError(location)
        with self._lock:
            if active_only:
                cur = self._conn.execute(
                    "SELECT * FROM location_subscriptions WHERE location = ? AND status = 'active' "
                    "ORDER BY user_id",
                    (location,),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM location_subscriptions WHERE location = ? ORDER BY user_id",
                    (location,),
                )
            rows = cur.fetchall()
        return [self._row_to_subscription(row) for row in rows]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[AccessRegistry] = None
_registry_lock = threading.Lock()


def get_access_registry() -> AccessRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_registry()` for roles, `get_relations_registry()`)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = AccessRegistry()
    return _registry
