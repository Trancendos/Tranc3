"""
Global Tier-1 orchestrator display names from Infinity-Admin overrides.

Stored in entity_overrides with location_pid=__ORCHESTRATOR__ so renames
do not require editing Dimensional/infinity/nomenclature.py.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.entities.override_store import _db_path, invalidate_override_cache

ORCHESTRATOR_PID = "__ORCHESTRATOR__"


def load_orchestrator_overrides(*, force: bool = False) -> dict[str, str]:
    """Map orchestrator id (e.g. cornelius) -> override display name."""
    path = _db_path()
    if not path.is_file():
        return {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT slot, override_name FROM entity_overrides "
            "WHERE location_pid = ? AND entity_type = 'orchestrator'",
            (ORCHESTRATOR_PID,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    return {str(r["slot"]): str(r["override_name"]) for r in rows if r["slot"]}


def get_orchestrator_display_name(orchestrator_id: str, canonical_name: str) -> str:
    """Effective Tier-1 name; falls back to nomenclature canonical."""
    return load_orchestrator_overrides().get(orchestrator_id, canonical_name)


def upsert_orchestrator_override(
    conn: Any,
    orchestrator_id: str,
    *,
    original_name: str,
    override_name: str,
    updated_at: str,
    updated_by: str | None = None,
) -> None:
    """Write orchestrator rename (used by infinity-admin-service)."""
    conn.execute(
        """INSERT INTO entity_overrides
           (id, location_pid, entity_type, slot, original_name, override_name,
            updated_at, updated_by)
           VALUES (?, ?, 'orchestrator', ?, ?, ?, ?, ?)
           ON CONFLICT(location_pid, entity_type, slot) DO UPDATE SET
             override_name = excluded.override_name,
             original_name = excluded.original_name,
             updated_at = excluded.updated_at,
             updated_by = excluded.updated_by""",
        (
            f"orch-{orchestrator_id}",
            ORCHESTRATOR_PID,
            orchestrator_id,
            original_name,
            override_name,
            updated_at,
            updated_by,
        ),
    )
    invalidate_override_cache()
