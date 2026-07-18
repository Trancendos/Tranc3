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
    HEALTH_AGGREGATOR_REGISTRY,
    build_health_aggregator_name_to_service_id,
    build_port_to_service_id,
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


@pytest.fixture()
def make_health_aggregator_db(tmp_path):
    """Builds a synthetic health-aggregator SQLite DB per call, in a
    pytest-managed tmp_path so files are cleaned up automatically."""

    def _make(rows, name="health_aggregator.db"):
        db_path = str(tmp_path / name)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """CREATE TABLE health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT, port INTEGER, url TEXT, status TEXT,
                    latency_ms INTEGER, checked_at TEXT, error TEXT
                )"""
            )
            conn.executemany(
                "INSERT INTO health_checks "
                "(service, port, url, status, latency_ms, checked_at, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        return db_path

    return _make


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


def test_port_to_service_id_resolves_known_port(cmdb_session):
    mapping = build_port_to_service_id(cmdb_session)
    assert mapping.get(8004) == "SRV-WS-001"


def test_sync_writes_observations_for_mapped_services(cmdb_session, make_health_aggregator_db):
    db_path = make_health_aggregator_db(
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
                "down",
                None,
                "2026-07-18T10:00:30+00:00",
                "probe_failed",
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
    assert statuses == {"healthy", "down"}
    scores = {o.health_score for o in obs}
    assert scores == {1.0, 0.0}


def test_sync_covers_dynamically_registered_services_via_port_join(
    cmdb_session, make_health_aggregator_db
):
    """A dynamic registration (scripts/register_ea_workbook_services.py)
    records health_checks.service as the CSV ServiceName ("MCP Server"),
    not a name from HEALTH_AGGREGATOR_REGISTRY — so this must still sync
    via the port column, not the static name list (PR #223 review)."""
    db_path = make_health_aggregator_db(
        [
            (
                "MCP Server",  # not in HEALTH_AGGREGATOR_REGISTRY at all
                8004,
                "http://infinity-ws:8004/health",
                "healthy",
                9,
                "2026-07-18T10:00:00+00:00",
                None,
            ),
        ]
    )
    stats = sync_from_health_aggregator_db(cmdb_session, db_path)

    assert stats["written"] == 1
    assert stats["skipped_unmapped"] == 0

    obs = cmdb_session.query(HealthObservation).filter_by(service_id="SRV-WS-001").one()
    assert obs.status == "healthy"
    assert obs.response_time_ms == 9


def test_sync_is_incremental_via_since_id(cmdb_session, make_health_aggregator_db):
    db_path = make_health_aggregator_db(
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


def test_sync_rerun_without_since_id_does_not_duplicate(cmdb_session, make_health_aggregator_db):
    """Simulates the crash-recovery case flagged on review: the marker file
    wasn't advanced (e.g. a crash between the CMDB commit and the marker
    write), so the next run re-reads the same rows from id 0. The
    (service_id, observed_at, source) dedupe check must prevent duplicate
    HealthObservation rows in that case."""
    db_path = make_health_aggregator_db(
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

    second = sync_from_health_aggregator_db(cmdb_session, db_path, since_id=0)
    assert second["rows_read"] == 1
    assert second["written"] == 0
    assert second["skipped_duplicate"] == 1

    total = cmdb_session.query(HealthObservation).count()
    assert total == 1


def test_registry_does_not_drift_from_health_aggregator_worker():
    """HEALTH_AGGREGATOR_REGISTRY is a deliberate static copy (see module
    docstring in src/cmdb/health_sync.py) — this catches it silently going
    stale if workers/health-aggregator/worker.py's SERVICE_REGISTRY changes
    without the copy being updated by hand."""
    import importlib.util

    worker_path = "workers/health-aggregator/worker.py"
    spec = importlib.util.spec_from_file_location("_health_aggregator_worker", worker_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    live_registry = [(svc["name"], svc["port"]) for svc in module.SERVICE_REGISTRY]
    assert HEALTH_AGGREGATOR_REGISTRY == live_registry, (
        "HEALTH_AGGREGATOR_REGISTRY in src/cmdb/health_sync.py has drifted from "
        "workers/health-aggregator/worker.py:SERVICE_REGISTRY — update the copy by hand."
    )
