"""Tests for health metadata and override store."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.entities.effective import resolve_entity
from src.entities.health_metadata import health_entity_block
from src.entities.override_store import invalidate_override_cache, load_overrides_for_pid


class TestHealthEntityBlock:
    def test_nexus_port_canonical_lead_ai(self):
        block = health_entity_block(8004, "infinity-ws")
        assert block["pid"] == "PID-NXS"
        assert block["lead_ai"] == "Nexus-Prime"
        assert block["location"] == "The Nexus"

    def test_lab_syntax_sage_is_agent_not_prime(self):
        ent = resolve_entity("PID-LAB")
        assert ent is not None
        assert ent.agent_beta is not None
        assert ent.agent_beta.code_name == "Syntax-Sage"
        assert ent.agent_beta.tier == 4
        primes = ent.primes
        assert "Syntax-Sage" not in primes


class TestOverrideStore:
    def test_load_from_sqlite(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "admin.db"
            conn = sqlite3_connect(db_path)
            conn.execute(
                """CREATE TABLE entity_overrides (
                id TEXT PRIMARY KEY, location_pid TEXT, entity_type TEXT,
                slot TEXT, original_name TEXT, override_name TEXT,
                updated_at TEXT, updated_by TEXT,
                UNIQUE(location_pid, entity_type, slot))"""
            )
            conn.execute(
                """INSERT INTO entity_overrides VALUES
                ('1','PID-NXS','lead_ai','','Nexus-Prime','Custom-Nexus','now','test')"""
            )
            conn.commit()
            conn.close()

            monkeypatch.setenv("ENTITY_OVERRIDES_DB", str(db_path))
            invalidate_override_cache()
            ov = load_overrides_for_pid("PID-NXS", force=True)
            assert ov.get("lead_ai") == "Custom-Nexus"

            block = health_entity_block(8004)
            assert block["lead_ai"] == "Custom-Nexus"
            assert block["overrides_active"] is True
