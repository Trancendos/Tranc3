"""Tests for global Tier-1 orchestrator name overrides."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.entities.orchestrator_effective import (
    ORCHESTRATOR_PID,
    get_orchestrator_display_name,
    load_orchestrator_overrides,
    upsert_orchestrator_override,
)


@pytest.fixture
def orch_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "infinity_admin.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE entity_overrides (
            id TEXT PRIMARY KEY,
            location_pid TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            slot TEXT NOT NULL DEFAULT '',
            original_name TEXT NOT NULL,
            override_name TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            UNIQUE(location_pid, entity_type, slot)
        )"""
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("ENTITY_OVERRIDES_DB", str(db_path))
    from src.entities import override_store

    override_store.invalidate_override_cache()
    return db_path


def test_orchestrator_override_roundtrip(orch_db: Path) -> None:
    conn = sqlite3.connect(orch_db)
    upsert_orchestrator_override(
        conn,
        "cornelius",
        original_name="Cornelius MacIntyre",
        override_name="Cornelius McIntyre",
        updated_at="2026-05-31T00:00:00Z",
    )
    conn.commit()
    conn.close()

    from src.entities import override_store

    override_store.invalidate_override_cache()

    assert load_orchestrator_overrides(force=True)["cornelius"] == "Cornelius McIntyre"
    assert (
        get_orchestrator_display_name("cornelius", "Cornelius MacIntyre")
        == "Cornelius McIntyre"
    )
    assert get_orchestrator_display_name("missing", "Canonical") == "Canonical"


def test_orchestrator_pid_constant() -> None:
    assert ORCHESTRATOR_PID == "__ORCHESTRATOR__"
