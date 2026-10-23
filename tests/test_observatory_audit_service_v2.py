"""Audit v2 end-to-end regression tests; run inside a Tranc3 checkout.

pytest -q tests/test_observatory_audit_service_v2.py
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def audit(tmp_path, monkeypatch):
    module = import_worker(
        "audit_service_v2_regression", ROOT / "workers" / "audit-service" / "worker.py"
    )
    monkeypatch.setattr(module, "DB_PATH", tmp_path / "audit.db")
    monkeypatch.setattr(module, "INTERNAL_SECRET", "test-only-audit-secret")
    module._init_db()
    return module, TestClient(module.app)


def _append(client, suffix="one"):
    response = client.post(
        "/events",
        headers={"X-Internal-Secret": "test-only-audit-secret"},
        json={
            "event_id": f"event-{suffix}",
            "service": "observatory",
            "action": "incident.triage",
            "actor": "test-agent",
            "severity": "info",
            "details": {"incident": suffix, "checks": [1, 2, 3]},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_new_events_use_version_2_and_verify_after_reopen(audit):
    module, client = audit
    _append(client)
    _append(client, "two")
    with module._connect() as conn:
        versions = [
            row[0] for row in conn.execute("SELECT hash_version FROM audit_log ORDER BY id")
        ]
    assert versions == [2, 2]
    assert client.get("/verify").json() == {"valid": True, "checked": 2, "first_break_at": None}


@pytest.mark.parametrize(
    "column,new_value",
    [
        ("severity", "critical"),
        ("details_json", '{"incident":"altered"}'),
    ],
)
def test_severity_or_details_tampering_breaks_chain_and_degrades_health(audit, column, new_value):
    module, client = audit
    _append(client)
    with module._connect() as conn:
        conn.execute(
            f"UPDATE audit_log SET {column} = ? WHERE event_id = ?", (new_value, "event-one")
        )
    verification = client.get("/verify").json()
    assert verification["valid"] is False
    assert verification["first_break_at"] == "event-one"
    health = client.get("/health").json()
    assert health["chain_valid"] is False
    assert health["status"] == "degraded"


def test_first_or_only_record_is_always_spot_checked(audit):
    module, client = audit
    _append(client)
    with module._connect() as conn:
        conn.execute("UPDATE audit_log SET actor = 'attacker' WHERE event_id = 'event-one'")
    assert client.get("/health").json()["chain_valid"] is False


def test_legacy_rows_remain_verifiable_after_schema_migration(audit):
    module, client = audit
    ts = "2026-10-23T09:00:00+00:00"
    legacy_hash = module._compute_hash(
        module.GENESIS_HASH, "event-legacy", ts, "obs", "write", "agent", "", "success"
    )
    with module._connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (event_id,timestamp,service,action,actor,resource,outcome,severity,details_json,prev_hash,hash,hash_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "event-legacy",
                ts,
                "obs",
                "write",
                "agent",
                "",
                "success",
                "info",
                "{}",
                module.GENESIS_HASH,
                legacy_hash,
                1,
            ),
        )
    _append(client)
    assert client.get("/verify").json()["valid"] is True


def test_legacy_database_migrates_without_rewriting_old_rows(tmp_path, monkeypatch):
    import sqlite3

    module = import_worker(
        "audit_service_v2_migration_regression", ROOT / "workers" / "audit-service" / "worker.py"
    )
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""CREATE TABLE audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
          timestamp TEXT NOT NULL, service TEXT NOT NULL, action TEXT NOT NULL,
          actor TEXT NOT NULL, resource TEXT NOT NULL, outcome TEXT NOT NULL,
          severity TEXT NOT NULL, details_json TEXT NOT NULL,
          prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
        """)
    monkeypatch.setattr(module, "DB_PATH", db)
    module._init_db()
    with module._connect() as conn:
        names = {row["name"] for row in conn.execute("PRAGMA table_info(audit_log)")}
    assert "hash_version" in names
