# tests/test_analytics_service.py
# Tests for workers/analytics-service/worker.py
# Covers event ingestion, metric recording, funnel, DuckDB OLAP endpoints,
# Parquet archival, and the safety guard on /analytics/query.

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("INTERNAL_SECRET", "")  # auth disabled in tests


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import importlib.util
    import sqlite3
    import sys
    from pathlib import Path
    from unittest.mock import patch

    tmp = tmp_path_factory.mktemp("analytics_data")
    os.environ["ANALYTICS_DATA_DIR"] = str(tmp)
    os.environ["ANALYTICS_ARCHIVE_AFTER_DAYS"] = "1"

    # The worker directory is named "analytics-service" (hyphen) which is not
    # a valid Python package name, so we load it via importlib from its path.
    worker_path = (
        Path(__file__).parent.parent / "workers" / "analytics-service" / "worker.py"
    )
    module_name = "analytics_service_worker"

    # Remove any previously cached module so env vars above take effect.
    sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(module_name, worker_path)
    assert spec is not None and spec.loader is not None, f"Cannot load {worker_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    # Replace the encrypted_sqlite module so that the worker's top-level import
    # `from src.database.encrypted_sqlite import connect as sqlite3_connect`
    # resolves to plain sqlite3.connect instead of the encrypted backend.
    import types as _types

    fake_enc = _types.ModuleType("src.database.encrypted_sqlite")
    fake_enc.connect = lambda p, **kw: sqlite3.connect(p, **kw)  # type: ignore[attr-defined]
    sys.modules.setdefault("src", _types.ModuleType("src"))
    sys.modules.setdefault("src.database", _types.ModuleType("src.database"))
    sys.modules["src.database.encrypted_sqlite"] = fake_enc

    spec.loader.exec_module(module)  # type: ignore[union-attr]

    from fastapi.testclient import TestClient

    yield TestClient(module.app, raise_server_exceptions=True)


# ── Health ────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "live_events" in data

    def test_reports_duckdb_availability(self, client):
        r = client.get("/health")
        assert "duckdb_available" in r.json()


# ── Event Ingestion ───────────────────────────────────────────────────────────


class TestEventIngestion:
    def test_single_event(self, client):
        r = client.post("/events", json={"event_type": "page_view", "user_id": "u1", "session_id": "s1"})
        assert r.status_code == 201
        data = r.json()
        assert data["event_type"] == "page_view"
        assert "id" in data

    def test_batch_events(self, client):
        events = [
            {"event_type": "click", "user_id": f"u{i}", "session_id": "s2"}
            for i in range(5)
        ]
        r = client.post("/events/batch", json={"events": events})
        assert r.status_code == 201
        assert r.json()["inserted"] == 5

    def test_empty_event_type_rejected(self, client):
        r = client.post("/events", json={"event_type": ""})
        assert r.status_code == 422

    def test_query_events(self, client):
        r = client.get("/events?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert isinstance(data["events"], list)

    def test_event_types(self, client):
        r = client.get("/events/types")
        assert r.status_code == 200
        assert "types" in r.json()

    def test_funnel(self, client):
        # Seed some events for funnel
        client.post("/events", json={"event_type": "signup", "user_id": "uf1", "session_id": "sf1"})
        client.post("/events", json={"event_type": "login", "user_id": "uf1", "session_id": "sf1"})
        r = client.post("/events/funnel", json={"steps": ["signup", "login"]})
        assert r.status_code == 200
        funnel = r.json()["funnel"]
        assert len(funnel) == 2
        assert funnel[0]["step"] == "signup"


# ── Metrics ───────────────────────────────────────────────────────────────────


class TestMetrics:
    def test_record_metric(self, client):
        r = client.post("/metrics", json={"name": "response_time", "value": 123.4})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "response_time"

    def test_get_metric_aggregates(self, client):
        for v in [100.0, 200.0, 300.0]:
            client.post("/metrics", json={"name": "latency", "value": v})
        for agg in ("avg", "sum", "min", "max", "count"):
            r = client.get(f"/metrics/latency?agg={agg}")
            assert r.status_code == 200
            assert r.json()["result"] is not None

    def test_metric_timeseries(self, client):
        r = client.get("/metrics/latency/timeseries?bucket=day&limit=7")
        assert r.status_code == 200
        assert "series" in r.json()


# ── Summary ───────────────────────────────────────────────────────────────────


class TestSummary:
    def test_summary(self, client):
        r = client.get("/summary")
        assert r.status_code == 200
        data = r.json()
        assert "live_events" in data
        assert "live_metrics" in data
        assert "top_event_types" in data


# ── DuckDB OLAP ───────────────────────────────────────────────────────────────


class TestDuckDBOlap:
    """These tests run only if DuckDB is installed; skip gracefully otherwise."""

    def _skip_if_no_duckdb(self, client):
        r = client.get("/health")
        if not r.json().get("duckdb_available"):
            pytest.skip("DuckDB not installed")

    def test_dau(self, client):
        self._skip_if_no_duckdb(client)
        r = client.get("/analytics/dau?days=7")
        assert r.status_code == 200
        data = r.json()
        assert "wau" in data
        assert "mau" in data
        assert isinstance(data["daily"], list)

    def test_retention(self, client):
        self._skip_if_no_duckdb(client)
        r = client.get("/analytics/retention?cohort_days=7")
        assert r.status_code == 200
        assert "cohorts" in r.json()

    def test_sessions(self, client):
        self._skip_if_no_duckdb(client)
        r = client.get("/analytics/sessions?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert "bounce_rate" in data
        assert "avg_depth" in data

    def test_journeys(self, client):
        self._skip_if_no_duckdb(client)
        r = client.get("/analytics/journeys?top_n=5")
        assert r.status_code == 200
        assert "journeys" in r.json()

    def test_platform_summary(self, client):
        self._skip_if_no_duckdb(client)
        r = client.get("/analytics/platform")
        assert r.status_code == 200
        assert "platform" in r.json()

    def test_olap_query_valid_select(self, client):
        self._skip_if_no_duckdb(client)
        r = client.post(
            "/analytics/query",
            json={"sql": "SELECT event_type, COUNT(*) AS n FROM all_events GROUP BY event_type ORDER BY n DESC", "limit": 10},
        )
        assert r.status_code == 200
        data = r.json()
        assert "columns" in data
        assert "rows" in data

    def test_olap_query_rejects_insert(self, client):
        self._skip_if_no_duckdb(client)
        r = client.post("/analytics/query", json={"sql": "INSERT INTO events (event_type) VALUES ('x')", "limit": 10})
        assert r.status_code == 422  # rejected by field validator

    def test_olap_query_rejects_drop(self, client):
        self._skip_if_no_duckdb(client)
        r = client.post("/analytics/query", json={"sql": "DROP TABLE events", "limit": 10})
        assert r.status_code == 422

    def test_olap_query_rejects_with_mutation(self, client):
        self._skip_if_no_duckdb(client)
        r = client.post(
            "/analytics/query",
            json={"sql": "WITH x AS (DELETE FROM events RETURNING *) SELECT * FROM x", "limit": 10},
        )
        assert r.status_code == 422

    def test_archive_endpoint(self, client):
        self._skip_if_no_duckdb(client)
        r = client.post("/analytics/archive")
        assert r.status_code == 200
        data = r.json()
        assert "archive_after_days" in data
