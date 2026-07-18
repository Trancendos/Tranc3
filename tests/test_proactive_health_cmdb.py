"""ProactiveHealthMonitor.sample_from_cmdb: the existing EWMA/trend-detection
machinery must produce correct alerts when replayed against real CMDB
HealthObservation rows, not just against live in-process entities."""

from __future__ import annotations

import sqlite3

from src.observability.proactive_health import ProactiveHealthMonitor


def _make_cmdb_db(path, rows):
    """rows: list of (service_id, health_score, observed_at) tuples."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE health_observations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, service_id TEXT, "
        "observed_at TEXT, health_score REAL, status TEXT, "
        "error_count INTEGER, response_time_ms INTEGER, source TEXT, notes TEXT)"
    )
    for i, (service_id, score, observed_at) in enumerate(rows):
        conn.execute(
            "INSERT INTO health_observations "
            "(service_id, observed_at, health_score, status, error_count, source) "
            "VALUES (?, ?, ?, 'healthy', 0, 'test')",
            (service_id, observed_at, score),
        )
    conn.commit()
    conn.close()


def test_missing_db_returns_no_alerts_not_an_error(tmp_path):
    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(tmp_path / "does-not-exist.db"))
    assert alerts == []


def test_empty_health_observations_table_returns_no_alerts(tmp_path):
    cmdb_path = tmp_path / "cmdb.db"
    _make_cmdb_db(cmdb_path, [])
    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert alerts == []


def test_steady_healthy_scores_raise_no_alerts(tmp_path):
    cmdb_path = tmp_path / "cmdb.db"
    _make_cmdb_db(
        cmdb_path,
        [("SRV-SPARK-001", 1.0, f"2026-07-{d:02d}T00:00:00") for d in range(1, 6)],
    )
    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert alerts == []


def test_declining_scores_raise_critical_alert(tmp_path):
    """EWMA (alpha=0.3) smooths from a 1.0 baseline, so driving it under the
    0.35 critical threshold needs several consecutive low samples, not just
    one — matches how check_all()'s own EWMA behaves for a live entity."""
    cmdb_path = tmp_path / "cmdb.db"
    _make_cmdb_db(
        cmdb_path,
        [("SRV-SPARK-001", 0.02, f"2026-07-{d:02d}T00:00:00") for d in range(1, 7)],
    )
    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert any(a.severity == "critical" for a in alerts)
    assert all(a.entity_id == "SRV-SPARK-001" for a in alerts)


def test_multiple_services_scored_independently(tmp_path):
    """A critical service's low score must not bleed into another
    service's EWMA — each service_id gets its own baseline."""
    cmdb_path = tmp_path / "cmdb.db"
    _make_cmdb_db(
        cmdb_path,
        [("SRV-SPARK-001", 0.02, f"2026-07-{d:02d}T00:00:00") for d in range(1, 7)]
        + [
            ("SRV-VOID-001", 1.0, "2026-07-01T00:00:00"),
            ("SRV-VOID-001", 1.0, "2026-07-02T00:00:00"),
        ],
    )
    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert any(a.entity_id == "SRV-SPARK-001" and a.severity == "critical" for a in alerts)
    assert not any(a.entity_id == "SRV-VOID-001" for a in alerts)


def test_null_health_score_rows_are_excluded(tmp_path):
    """health_sync.py writes health_score=None for statuses outside the
    known vocabulary — those rows must not silently count as a 0.0 score."""
    cmdb_path = tmp_path / "cmdb.db"
    conn = sqlite3.connect(cmdb_path)
    conn.execute(
        "CREATE TABLE health_observations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, service_id TEXT, "
        "observed_at TEXT, health_score REAL, status TEXT, "
        "error_count INTEGER, response_time_ms INTEGER, source TEXT, notes TEXT)"
    )
    conn.execute(
        "INSERT INTO health_observations "
        "(service_id, observed_at, health_score, status, error_count, source) "
        "VALUES ('SRV-SPARK-001', '2026-07-01T00:00:00', NULL, 'unknown', 0, 'test')"
    )
    conn.commit()
    conn.close()

    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert alerts == []
    assert "SRV-SPARK-001" not in monitor._ewma


def test_repeated_calls_against_unchanged_history_do_not_duplicate_alerts(tmp_path):
    """Regression test: calling sample_from_cmdb twice against the same,
    unchanged HealthObservation history must not re-raise the same
    historical alerts a second time — otherwise self._alerts grows
    unboundedly and the same events get re-logged/re-persisted forever."""
    cmdb_path = tmp_path / "cmdb.db"
    _make_cmdb_db(
        cmdb_path,
        [("SRV-SPARK-001", 0.02, f"2026-07-{d:02d}T00:00:00") for d in range(1, 7)],
    )
    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")

    first_alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert first_alerts != []
    total_after_first = len(monitor._alerts)

    second_alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert second_alerts == []  # nothing *new* — every alert was already raised
    assert len(monitor._alerts) == total_after_first  # no growth on replay


def test_distinct_rows_sharing_a_timestamp_both_raise(tmp_path):
    """Regression test: two distinct HealthObservation rows for the same
    service that happen to share an identical observed_at (e.g. two sources
    polling in the same instant) must not collide into a single suppressed
    alert — the replay id must key on the row's own id, not just
    (service_id, observed_at, severity, kind)."""
    cmdb_path = tmp_path / "cmdb.db"
    same_ts = "2026-07-01T00:00:00"
    _make_cmdb_db(
        cmdb_path,
        [(sid, 0.02, same_ts) for sid in ("SRV-SPARK-001", "SRV-VOID-001")],
    )
    # Drive both down to critical with more low samples at the same timestamp.
    conn = sqlite3.connect(cmdb_path)
    for sid in ("SRV-SPARK-001", "SRV-VOID-001"):
        for _ in range(6):
            conn.execute(
                "INSERT INTO health_observations "
                "(service_id, observed_at, health_score, status, error_count, source) "
                "VALUES (?, ?, 0.02, 'healthy', 0, 'test')",
                (sid, same_ts),
            )
    conn.commit()
    conn.close()

    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    ids_seen = {a.entity_id for a in alerts if a.severity == "critical"}
    assert ids_seen == {"SRV-SPARK-001", "SRV-VOID-001"}


def test_missing_health_observations_table_returns_no_alerts_not_a_crash(tmp_path):
    """A CMDB db that predates HealthObservation (or points at the wrong
    file) must report and return no alerts, not raise sqlite3.OperationalError."""
    cmdb_path = tmp_path / "cmdb.db"
    conn = sqlite3.connect(cmdb_path)
    conn.execute("CREATE TABLE services (service_id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    monitor = ProactiveHealthMonitor(db_path=tmp_path / "alerts.db")
    alerts = monitor.sample_from_cmdb(str(cmdb_path))
    assert alerts == []
