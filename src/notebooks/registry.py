# src/notebooks/registry.py
"""Notebook Registry — personal, freeform notes for AIs and Agents.

Implements the `NotebookEntry` data model from
`docs/governance/NOTEBOOKS-JOURNALS-SCOPE.md` §3.1, resolving that doc's §4
open questions with the defaults documented here (and in that doc):

- **Storage**: Tranc3, not CranBania — the "smaller of the two options"
  §5 recommended building first, following the exact SQLite-per-registry
  pattern already used by Role/Access/Relations.
- **Visibility default**: `ai_private`. Three values, matching §4's actual
  audiences (not the stale `private|location|platform` enum §4 itself
  flagged as inconsistent):
  - `ai_private` — the tightest scope. This platform has no per-AI
    authenticated principal today (Role Registry's `changed_by` is a human
    operator id, not an AI credential), so "only the owning AI can read
    this" cannot be enforced by checking a request's identity against
    `owner`. Read access is deliberately restricted to admins instead,
    which is at least as strict as the intent, not a fabricated identity
    check this platform can't actually perform yet.
  - `operator` — any authenticated user.
  - `public` — no authentication required, same audience as the Relations
    Activity Feed.
- **Activity Feed integration**: left separate, not built. §4 flagged this
  as an open question with real duplication-vs-fragmentation tradeoffs
  either way; wiring it in later is additive and doesn't require redoing
  this registry.

The identity-namespacing gap `AI-RELATIONSHIP-MATRIX.md` §2 and this scope
doc's own §2 both flag (e.g. "Agent Alpha" isn't unique across Locations) is
NOT resolved here — `owner` and `linked_card_id`/`linked_location` are plain
free-text fields, matching how Role Registry and Relations Registry already
store AI/Agent identity. Fixing that namespacing is a separate, cross-cutting
piece of work, not something this registry can fix in isolation.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.validation.validators import validate_non_empty, validate_safe_string

DEFAULT_DB_PATH = Path("data/notebooks_registry.db")

VISIBILITY_VALUES = ("ai_private", "operator", "public")


@dataclass
class NotebookEntry:
    id: int
    owner: str
    created_at: float
    content: str
    visibility: str
    linked_card_id: Optional[str]
    linked_location: Optional[str]


def validate_visibility(value: str) -> str:
    if value not in VISIBILITY_VALUES:
        raise ValueError(f"visibility must be one of {VISIBILITY_VALUES}, got {value!r}")
    return value


class NotebookRegistry:
    """SQLite-backed registry of personal Notebook entries per AI/Agent."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Same rationale as RoleRegistry/RelationsRegistry: FastAPI's
        # threadpool runs these sync handlers concurrently, so every method
        # (reads included) takes this RLock rather than relying on SQLite's
        # own locking, which would leave read-modify-write sequences racy.
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notebook_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                created_at REAL NOT NULL,
                content TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'ai_private',
                linked_card_id TEXT,
                linked_location TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notebook_owner ON notebook_entries(owner)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notebook_card ON notebook_entries(linked_card_id)"
        )
        self._conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> NotebookEntry:
        return NotebookEntry(
            id=row["id"],
            owner=row["owner"],
            created_at=row["created_at"],
            content=row["content"],
            visibility=row["visibility"],
            linked_card_id=row["linked_card_id"],
            linked_location=row["linked_location"],
        )

    def create_entry(
        self,
        owner: str,
        content: str,
        visibility: str = "ai_private",
        linked_card_id: Optional[str] = None,
        linked_location: Optional[str] = None,
    ) -> NotebookEntry:
        owner = validate_non_empty(owner, "owner")
        owner = validate_safe_string(owner, "owner", max_length=256)
        content = validate_non_empty(content, "content")
        content = validate_safe_string(content, "content", max_length=10_000)
        if linked_card_id is not None:
            linked_card_id = validate_safe_string(linked_card_id, "linked_card_id", max_length=256)
        if linked_location is not None:
            linked_location = validate_safe_string(
                linked_location, "linked_location", max_length=512
            )
        visibility = validate_visibility(visibility)
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO notebook_entries "
                "(owner, created_at, content, visibility, linked_card_id, linked_location) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (owner, now, content, visibility, linked_card_id, linked_location),
            )
            self._conn.commit()
            assert cur.lastrowid is not None
            entry = self._get_by_id(cur.lastrowid)
            assert entry is not None
            return entry

    def _get_by_id(self, entry_id: int) -> Optional[NotebookEntry]:
        cur = self._conn.execute(
            "SELECT * FROM notebook_entries WHERE id = ?",
            (entry_id,),
        )
        row = cur.fetchone()
        return self._row_to_entry(row) if row else None

    def get_entry(self, entry_id: int) -> Optional[NotebookEntry]:
        with self._lock:
            return self._get_by_id(entry_id)

    def list_for_owner(self, owner: str) -> List[NotebookEntry]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM notebook_entries WHERE owner = ? ORDER BY created_at DESC",
                (owner,),
            )
            return [self._row_to_entry(row) for row in cur.fetchall()]

    def list_for_card(self, card_id: str) -> List[NotebookEntry]:
        """Task -> Notebook direction (§3.3): every entry linked to one CranBania Card."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM notebook_entries WHERE linked_card_id = ? ORDER BY created_at DESC",
                (card_id,),
            )
            return [self._row_to_entry(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[NotebookRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> NotebookRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_devocity()`, `get_library()`, `get_marketplace()`)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = NotebookRegistry()
    return _registry
