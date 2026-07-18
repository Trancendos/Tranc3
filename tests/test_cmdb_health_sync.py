"""health-aggregator -> CMDB HealthObservation sync.

No live production health_aggregator.db exists in this environment, so
this proves the sync logic is correct against a synthetic DB built with
the exact schema health-aggregator's worker.py uses (health_checks:
id, service, port, url, status, latency_ms, checked_at, error). It does
NOT prove the sync has been run against real production data — see
docs/governance/OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from src.cmdb.health_sync import (  # noqa: E402
    build_health_aggregator_name_to_service_id,
    first_port_in_notes,
    sync_from_health_aggregator_db,
)
from src.cmdb.loader import load_all  # noqa: E402
from src.cmdb.models import HealthObservation, build_engine  # noqa: E402


@pytest.fixture()
def cmdb_session():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        load_all(tmp.name)
        engine = build_engine(tmp.name)
        Session = sqlalchemy.orm.sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()


def _make_health_aggregator_db(rows):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        """CREATE TABLE health_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT, port INTEGER, url TEXT, status TEXT,
            latency_ms INTEGER, checked_at TEXT, error TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO health_checks (service, port, url, status, latency_ms, checked_at, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return tmp.name


def test_first_port_in_notes_takes_first_mention():
    notes = "Verified working on port 8058. Previously conflicted with port 9999."
    assert first_port_in_notes(notes) == 8058


def test_first_port_in_notes_handles_no_mention():
    assert first_port_in_notes("No port documented here.") is None


def test_name_to_service_id_mapping_is_nonempty_and_known_entries_resolve(cmdb_session):
    mapping = build_health_aggregator_name_to_service_id(cmdb_session)
    assert mapping
    # infinity-ws (port 8004) was fixed and documented with a clear port
    # mention this session — a reliable known-good case.
    assert mapping.get("infinity-ws") == "SRV-WS-001"


def test_sync_writes_observations_for_mapped_services(cmdb_session):
    db_path = _make_health_aggregator_db(
        [
            (
                "infinity-ws",
                8004,
                "http://infinity-ws:8004/health",
                "healthy",
                12,
                "2026-07-18T10:00:00+00:00",
                None,
            ),
            (
                "infinity-ws",
                8004,
                "http://infinity-ws:8004/health",
                "unhealthy",
                None,
                "2026-07-18T10:00:30+00:00",
                "connection refused",
            ),
            (
                "totally-unknown-service",
                9999,
                "http://x:9999/health",
                "healthy",
                5,
                "2026-07-18T10:00:00+00:00",
                None,
            ),
        ]
    )
    stats = sync_from_health_aggregator_db(cmdb_session, db_path)

    assert stats["rows_read"] == 3
    assert stats["written"] == 2
    assert stats["skipped_unmapped"] == 1

    obs = cmdb_session.query(HealthObservation).filter_by(service_id="SRV-WS-001").all()
    assert len(obs) == 2
    statuses = {o.status for o in obs}
    assert statuses == {"healthy", "unhealthy"}
    scores = {o.health_score for o in obs}
    assert scores == {1.0, 0.0}


def test_sync_is_incremental_via_since_id(cmdb_session):
    db_path = _make_health_aggregator_db(
        [
            (
                "infinity-ws",
                8004,
                "http://infinity-ws:8004/health",
                "healthy",
                12,
                "2026-07-18T10:00:00+00:00",
                None,
            ),
        ]
    )
    first = sync_from_health_aggregator_db(cmdb_session, db_path)
    assert first["written"] == 1

    second = sync_from_health_aggregator_db(cmdb_session, db_path, since_id=first["max_id"])
    assert second["rows_read"] == 0
    assert second["written"] == 0

    total = cmdb_session.query(HealthObservation).count()
    assert total == 1
