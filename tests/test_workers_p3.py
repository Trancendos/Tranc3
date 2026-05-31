"""
Worker Integration Tests — P3 Workers (16 supporting services)
===============================================================
Tests all 16 extended/supporting workers using FastAPI TestClient.
No external services required — all use in-memory or temp SQLite state.

P3 Workers covered:
  analytics-service  (8016)   the-grid          (8010)
  search-service     (8017)   identity-service  (8015)
  email-service      (8018)   queue-service     (8022)
  sms-service        (8019)   cache-service     (8023)
  storage-service    (8020)   config-service    (8024)
  cron-service       (8021)   audit-service     (8025)
  rate-limit-service (8026)   geo-service       (8027)
  cdn-service        (8028)   health-aggregator (8029)
"""

from __future__ import annotations

import importlib
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


def _import_worker(module_dotted: str, file_path: Path):
    """Import a worker module from a hyphenated path via importlib."""
    spec = importlib.util.spec_from_file_location(module_dotted, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_dotted] = mod
    spec.loader.exec_module(mod)
    return mod


analytics_mod = _import_worker(
    "analytics_service_worker",
    _TRANC3_ROOT / "workers" / "analytics-service" / "worker.py",
)
search_mod = _import_worker(
    "search_service_worker",
    _TRANC3_ROOT / "workers" / "search-service" / "worker.py",
)
email_mod = _import_worker(
    "email_service_worker",
    _TRANC3_ROOT / "workers" / "email-service" / "worker.py",
)
sms_mod = _import_worker(
    "sms_service_worker",
    _TRANC3_ROOT / "workers" / "sms-service" / "worker.py",
)
storage_mod = _import_worker(
    "storage_service_worker",
    _TRANC3_ROOT / "workers" / "storage-service" / "worker.py",
)
cron_mod = _import_worker(
    "cron_service_worker",
    _TRANC3_ROOT / "workers" / "cron-service" / "worker.py",
)
queue_mod = _import_worker(
    "queue_service_worker",
    _TRANC3_ROOT / "workers" / "queue-service" / "worker.py",
)
cache_mod = _import_worker(
    "cache_service_worker",
    _TRANC3_ROOT / "workers" / "cache-service" / "worker.py",
)
config_mod = _import_worker(
    "config_service_worker",
    _TRANC3_ROOT / "workers" / "config-service" / "worker.py",
)
audit_mod = _import_worker(
    "audit_service_worker",
    _TRANC3_ROOT / "workers" / "audit-service" / "worker.py",
)
rate_limit_mod = _import_worker(
    "rate_limit_service_worker",
    _TRANC3_ROOT / "workers" / "rate-limit-service" / "worker.py",
)
geo_mod = _import_worker(
    "geo_service_worker",
    _TRANC3_ROOT / "workers" / "geo-service" / "worker.py",
)
cdn_mod = _import_worker(
    "cdn_service_worker",
    _TRANC3_ROOT / "workers" / "cdn-service" / "worker.py",
)
health_agg_mod = _import_worker(
    "health_aggregator_worker",
    _TRANC3_ROOT / "workers" / "health-aggregator" / "worker.py",
)
identity_mod = _import_worker(
    "identity_service_worker",
    _TRANC3_ROOT / "workers" / "identity-service" / "worker.py",
)
grid_mod = _import_worker(
    "the_grid_worker",
    _TRANC3_ROOT / "workers" / "the-grid" / "worker.py",
)


# ===========================================================================
# analytics-service (8016)
# ===========================================================================


class TestAnalyticsService:
    """Tests for analytics-service: events, metrics, funnel analysis."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "analytics.db")
        with patch.object(analytics_mod, "DB_PATH", db_path):
            analytics_mod.init_db()
            secret = getattr(analytics_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(analytics_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "event_count" in data

    def test_track_event(self, client):
        r = client.post(
            "/events",
            json={"event_type": "page_view", "user_id": "u1", "properties": {"page": "/home"}},
        )
        assert r.status_code == 201
        data = r.json()
        # Returns {id, event_type, timestamp}
        assert "id" in data
        assert data["event_type"] == "page_view"

    def test_track_batch_events(self, client):
        r = client.post(
            "/events/batch",
            json={
                "events": [
                    {"event_type": "click", "user_id": "u1"},
                    {"event_type": "scroll", "user_id": "u2"},
                ]
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["inserted"] == 2

    def test_list_events(self, client):
        client.post("/events", json={"event_type": "signup"})
        r = client.get("/events")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "total" in data

    def test_event_types(self, client):
        client.post("/events", json={"event_type": "purchase"})
        r = client.get("/events/types")
        assert r.status_code == 200
        data = r.json()
        assert "types" in data

    def test_record_metric(self, client):
        r = client.post(
            "/metrics",
            json={"name": "response_time_ms", "value": 42.5, "labels": {"endpoint": "/api"}},
        )
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["name"] == "response_time_ms"

    def test_get_metric(self, client):
        client.post("/metrics", json={"name": "cpu_usage", "value": 55.0})
        r = client.get("/metrics/cpu_usage")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "cpu_usage"
        assert "result" in data

    def test_get_metric_timeseries(self, client):
        client.post("/metrics", json={"name": "mem_usage", "value": 60.0})
        r = client.get("/metrics/mem_usage/timeseries")
        assert r.status_code == 200
        data = r.json()
        assert "series" in data

    def test_funnel_analysis(self, client):
        for evt in ["visit", "signup", "purchase"]:
            client.post("/events", json={"event_type": evt, "user_id": "funnel_user"})
        r = client.post(
            "/events/funnel",
            json={"steps": ["visit", "signup", "purchase"], "user_id": "funnel_user"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "funnel" in data

    def test_summary(self, client):
        r = client.get("/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_events" in data


# ===========================================================================
# search-service (8017)
# ===========================================================================


class TestSearchService:
    """Tests for search-service: full-text search with FTS5 indices."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "search.db")
        with patch.object(search_mod, "DB_PATH", db_path):
            search_mod.init_db()
            secret = getattr(search_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(search_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_index(self, client):
        r = client.post(
            "/indices",
            json={"name": "articles"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "articles"

    def test_list_indices(self, client):
        client.post("/indices", json={"name": "docs"})
        r = client.get("/indices")
        assert r.status_code == 200
        data = r.json()
        assert "indices" in data

    def test_index_document(self, client):
        client.post("/indices", json={"name": "pages"})
        r = client.put(
            "/indices/pages/documents/doc1",
            json={"id": "doc1", "title": "Hello World", "body": "Test content"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["indexed"] == "doc1"

    def test_search_query(self, client):
        client.post("/indices", json={"name": "kb"})
        client.put(
            "/indices/kb/documents/kb1",
            json={"id": "kb1", "title": "Python tutorial", "body": "Learn Python"},
        )
        r = client.post("/search", json={"index": "kb", "query": "Python"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data

    def test_delete_document(self, client):
        client.post("/indices", json={"name": "blog"})
        client.put(
            "/indices/blog/documents/b1",
            json={"id": "b1", "body": "Delete me"},
        )
        r = client.delete("/indices/blog/documents/b1")
        assert r.status_code == 200

    def test_batch_index(self, client):
        client.post("/indices", json={"name": "products"})
        r = client.post(
            "/indices/products/documents/batch",
            json={
                "documents": [
                    {"id": "p1", "title": "Widget A", "body": "A great widget"},
                    {"id": "p2", "title": "Widget B", "body": "Another widget"},
                ]
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["indexed"] == 2

    def test_delete_index(self, client):
        client.post("/indices", json={"name": "temp_idx"})
        r = client.delete("/indices/temp_idx")
        assert r.status_code == 200


# ===========================================================================
# email-service (8018)
# ===========================================================================


class TestEmailService:
    """Tests for email-service: async email delivery queue with templates."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "email.db")
        with patch.object(email_mod, "DB_PATH", db_path):
            email_mod.init_db()
            secret = getattr(email_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(email_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_send_email(self, client):
        r = client.post(
            "/send",
            json={
                "to": "user@example.com",
                "subject": "Test Email",
                "body_text": "Hello from tests",
            },
        )
        assert r.status_code == 202
        data = r.json()
        assert "id" in data
        assert data["status"] == "queued"

    def test_send_email_with_html(self, client):
        r = client.post(
            "/send",
            json={
                "to": "user@example.com",
                "subject": "HTML Email",
                "body_text": "Plain",
                "body_html": "<p>HTML body</p>",
            },
        )
        assert r.status_code == 202
        assert r.json()["status"] == "queued"

    def test_send_batch(self, client):
        r = client.post(
            "/send/batch",
            json={
                "emails": [
                    {"to": "a@example.com", "subject": "Email A", "body_text": "Body A"},
                    {"to": "b@example.com", "subject": "Email B", "body_text": "Body B"},
                ]
            },
        )
        assert r.status_code == 202
        data = r.json()
        assert data["queued"] == 2

    def test_list_outbox(self, client):
        client.post(
            "/send",
            json={"to": "x@example.com", "subject": "X", "body_text": "X body"},
        )
        r = client.get("/outbox")
        assert r.status_code == 200
        data = r.json()
        assert "emails" in data
        assert data["total"] >= 1

    def test_create_template(self, client):
        r = client.post(
            "/templates",
            json={
                "id": "welcome",
                "name": "Welcome Email",
                "subject": "Welcome {{name}}!",
                "body_text": "Hi {{name}}, welcome!",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["id"] == "welcome"

    def test_list_templates(self, client):
        client.post(
            "/templates",
            json={
                "id": "reset",
                "name": "Reset Email",
                "subject": "Reset",
                "body_text": "Reset {{token}}",
            },
        )
        r = client.get("/templates")
        assert r.status_code == 200
        data = r.json()
        assert "templates" in data

    def test_send_with_template(self, client):
        client.post(
            "/templates",
            json={
                "id": "greet",
                "name": "Greet",
                "subject": "Hi {{name}}",
                "body_text": "Hello {{name}}",
            },
        )
        r = client.post(
            "/templates/greet/send",
            json={"to": "user@example.com", "variables": {"name": "Alice"}},
        )
        assert r.status_code == 202
        assert r.json()["status"] == "queued"


# ===========================================================================
# sms-service (8019)
# ===========================================================================


class TestSmsService:
    """Tests for sms-service: outbound SMS queue."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "sms.db")
        with patch.object(sms_mod, "DB_PATH", db_path):
            sms_mod.init_db()
            secret = getattr(sms_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(sms_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_send_sms(self, client):
        r = client.post(
            "/send",
            json={"to": "+15551234567", "message": "Test SMS"},
        )
        assert r.status_code == 202
        data = r.json()
        assert "id" in data
        assert data["status"] == "queued"

    def test_send_batch_sms(self, client):
        r = client.post(
            "/send/batch",
            json={
                "messages": [
                    {"to": "+15551111111", "message": "Hello A"},
                    {"to": "+15552222222", "message": "Hello B"},
                ]
            },
        )
        assert r.status_code == 202
        data = r.json()
        assert data["queued"] == 2

    def test_list_outbox(self, client):
        client.post("/send", json={"to": "+15559999999", "message": "Outbox test"})
        r = client.get("/outbox")
        assert r.status_code == 200
        data = r.json()
        assert "messages" in data

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        data = r.json()
        assert "by_status" in data


# ===========================================================================
# storage-service (8020)
# ===========================================================================


class TestStorageService:
    """Tests for storage-service: S3-compatible object storage."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "storage.db")
        storage_path = tmp_path / "objects"
        with (
            patch.object(storage_mod, "DB_PATH", db_path),
            patch.object(storage_mod, "STORAGE_ROOT", storage_path),
        ):
            storage_mod.init_db()
            secret = getattr(storage_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(storage_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_bucket(self, client):
        r = client.post("/buckets", json={"name": "test-bucket"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "test-bucket"

    def test_list_buckets(self, client):
        client.post("/buckets", json={"name": "my-bucket"})
        r = client.get("/buckets")
        assert r.status_code == 200
        data = r.json()
        assert "buckets" in data

    def test_create_duplicate_bucket(self, client):
        client.post("/buckets", json={"name": "dup-bucket"})
        r = client.post("/buckets", json={"name": "dup-bucket"})
        assert r.status_code == 409

    def test_upload_object(self, client):
        client.post("/buckets", json={"name": "uploads"})
        r = client.put(
            "/buckets/uploads/objects/myfile.txt",
            files={"file": ("myfile.txt", b"Hello, world!", "text/plain")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["key"] == "myfile.txt"
        assert "size" in data

    def test_get_object(self, client):
        client.post("/buckets", json={"name": "get-bucket"})
        client.put(
            "/buckets/get-bucket/objects/hello.txt",
            files={"file": ("hello.txt", b"Test content", "text/plain")},
        )
        r = client.get("/buckets/get-bucket/objects/hello.txt")
        assert r.status_code == 200
        assert r.content == b"Test content"

    def test_get_object_metadata(self, client):
        client.post("/buckets", json={"name": "meta-bucket"})
        client.put(
            "/buckets/meta-bucket/objects/data.json",
            files={"file": ("data.json", b'{"key": "value"}', "application/json")},
        )
        r = client.get("/buckets/meta-bucket/objects/data.json/meta")
        assert r.status_code == 200
        data = r.json()
        assert "key" in data
        assert "content_type" in data

    def test_list_objects_in_bucket(self, client):
        client.post("/buckets", json={"name": "list-bucket"})
        client.put(
            "/buckets/list-bucket/objects/f1.txt",
            files={"file": ("f1.txt", b"File 1", "text/plain")},
        )
        r = client.get("/buckets/list-bucket/objects")
        assert r.status_code == 200
        data = r.json()
        assert "objects" in data

    def test_delete_bucket(self, client):
        client.post("/buckets", json={"name": "del-bucket"})
        r = client.delete("/buckets/del-bucket")
        assert r.status_code == 200


# ===========================================================================
# cron-service (8021)
# ===========================================================================


class TestCronService:
    """Tests for cron-service: scheduled job management."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "cron.db")
        with patch.object(cron_mod, "DB_PATH", db_path):
            cron_mod.init_db()
            secret = getattr(cron_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(cron_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_job(self, client):
        r = client.post(
            "/jobs",
            json={
                "name": "cleanup",
                "schedule": "0 2 * * *",
                "action": "http_call",
                "config": {"url": "http://localhost:8000/admin/cleanup"},
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert "id" in data

    def test_list_jobs(self, client):
        client.post(
            "/jobs",
            json={
                "name": "daily-report",
                "schedule": "0 9 * * 1-5",
                "action": "http_call",
                "config": {},
            },
        )
        r = client.get("/jobs")
        assert r.status_code == 200
        data = r.json()
        assert "jobs" in data

    def test_get_job(self, client):
        created = client.post(
            "/jobs",
            json={
                "name": "heartbeat",
                "schedule": "*/5 * * * *",
                "action": "http_call",
                "config": {"url": "http://localhost:8000/health"},
            },
        ).json()
        job_id = created["id"]
        r = client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == job_id

    def test_trigger_job(self, client):
        created = client.post(
            "/jobs",
            json={
                "name": "manual-task",
                "schedule": "0 0 * * *",
                "action": "http_call",
                "config": {},
            },
        ).json()
        job_id = created["id"]
        r = client.post(f"/jobs/{job_id}/trigger")
        assert r.status_code in (200, 202)

    def test_delete_job(self, client):
        created = client.post(
            "/jobs",
            json={"name": "temp", "schedule": "* * * * *", "action": "http_call", "config": {}},
        ).json()
        job_id = created["id"]
        r = client.delete(f"/jobs/{job_id}")
        assert r.status_code == 200

    def test_get_job_runs(self, client):
        created = client.post(
            "/jobs",
            json={
                "name": "run-tracker",
                "schedule": "*/1 * * * *",
                "action": "http_call",
                "config": {},
            },
        ).json()
        job_id = created["id"]
        r = client.get(f"/jobs/{job_id}/runs")
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data


# ===========================================================================
# queue-service (8022)
# ===========================================================================


class TestQueueService:
    """Tests for queue-service: pub/sub message broker."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "queue.db")
        with patch.object(queue_mod, "DB_PATH", db_path):
            queue_mod.init_db()
            secret = getattr(queue_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(queue_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_topic(self, client):
        r = client.post("/topics", json={"name": "events", "description": "Platform events"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "events"

    def test_list_topics(self, client):
        client.post("/topics", json={"name": "notifications"})
        r = client.get("/topics")
        assert r.status_code == 200
        data = r.json()
        assert "topics" in data

    def test_publish_message(self, client):
        client.post("/topics", json={"name": "orders"})
        r = client.post(
            "/topics/orders/publish",
            json={"payload": {"order_id": "ord-001", "amount": 99.99}},
        )
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["topic"] == "orders"

    def test_publish_batch(self, client):
        client.post("/topics", json={"name": "logs"})
        r = client.post(
            "/topics/logs/publish/batch",
            json={
                "messages": [
                    {"payload": {"level": "INFO", "msg": "App started"}},
                    {"payload": {"level": "WARN", "msg": "High CPU"}},
                ]
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["published"] == 2

    def test_consume_message(self, client):
        client.post("/topics", json={"name": "tasks"})
        client.post("/topics/tasks/publish", json={"payload": {"task": "process_file"}})
        r = client.get("/topics/tasks/consume", params={"consumer_id": "worker-1"})
        assert r.status_code == 200
        data = r.json()
        assert "messages" in data
        assert len(data["messages"]) >= 1

    def test_acknowledge_message(self, client):
        client.post("/topics", json={"name": "ack-topic"})
        client.post("/topics/ack-topic/publish", json={"payload": {"x": 1}})
        consume = client.get(
            "/topics/ack-topic/consume", params={"consumer_id": "worker-ack"}
        ).json()
        msg_id = consume["messages"][0]["id"]
        r = client.post(f"/topics/ack-topic/ack/{msg_id}")
        assert r.status_code == 200

    def test_dead_letters(self, client):
        client.post("/topics", json={"name": "dl-topic"})
        r = client.get("/topics/dl-topic/dead-letters")
        assert r.status_code == 200
        data = r.json()
        assert "dead_letters" in data

    def test_delete_topic(self, client):
        client.post("/topics", json={"name": "delete-me"})
        r = client.delete("/topics/delete-me")
        assert r.status_code == 200


# ===========================================================================
# cache-service (8023)
# ===========================================================================


class TestCacheService:
    """Tests for cache-service: TTL-backed in-memory + SQLite cache."""

    @pytest.fixture
    def client(self, tmp_path):
        # cache-service uses _store dict (module-level) + DB
        db_path = str(tmp_path / "cache.db")
        saved_store = dict(cache_mod._store)
        with patch.object(cache_mod, "DB_PATH", db_path):
            cache_mod._store.clear()
            cache_mod.init_db()
            secret = getattr(cache_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(cache_mod.app, headers=headers)
        cache_mod._store.clear()
        cache_mod._store.update(saved_store)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_set_and_get(self, client):
        client.put("/cache/mykey", json={"value": "hello-world"})
        r = client.get("/cache/mykey")
        assert r.status_code == 200
        data = r.json()
        assert data["value"] == "hello-world"
        # Cache get returns {key, value, ttl_remaining}
        assert "key" in data

    def test_get_missing_key(self, client):
        r = client.get("/cache/nonexistent-key-xyz")
        # Returns 404 for missing keys
        assert r.status_code == 404

    def test_set_with_ttl(self, client):
        r = client.put("/cache/ttl-key", json={"value": "temp", "ttl": 3600})
        assert r.status_code == 200
        data = r.json()
        assert data["key"] == "ttl-key"

    def test_delete(self, client):
        client.put("/cache/del-key", json={"value": "to-delete"})
        r = client.delete("/cache/del-key")
        assert r.status_code == 200
        gone = client.get("/cache/del-key")
        assert gone.status_code == 404

    def test_key_exists(self, client):
        client.put("/cache/exists-key", json={"value": "yes"})
        r = client.get("/cache/exists-key/exists")
        assert r.status_code == 200
        assert r.json()["exists"] is True

    def test_key_not_exists(self, client):
        r = client.get("/cache/no-such-key/exists")
        assert r.status_code == 200
        assert r.json()["exists"] is False

    def test_multi_set(self, client):
        r = client.post(
            "/cache/mset",
            json={"entries": {"k1": "v1", "k2": "v2"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2

    def test_multi_get(self, client):
        client.put("/cache/mg1", json={"value": "alpha"})
        client.put("/cache/mg2", json={"value": "beta"})
        r = client.post("/cache/mget", json=["mg1", "mg2", "missing"])
        assert r.status_code == 200
        data = r.json()
        assert "mg1" in data
        assert data["mg1"] == "alpha"

    def test_list_keys(self, client):
        client.put("/cache/list-key-1", json={"value": "a"})
        r = client.get("/cache")
        assert r.status_code == 200
        data = r.json()
        assert "keys" in data

    def test_flush_all(self, client):
        client.put("/cache/flush-key", json={"value": "flush-me"})
        r = client.delete("/cache")
        assert r.status_code == 200

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_keys" in data


# ===========================================================================
# config-service (8024)
# ===========================================================================


class TestConfigService:
    """Tests for config-service: namespaced configuration store."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "config.db")
        with patch.object(config_mod, "DB_PATH", db_path):
            config_mod.init_db()
            secret = getattr(config_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(config_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_namespace(self, client):
        r = client.post(
            "/namespaces",
            json={"name": "app", "description": "Application config"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "app"

    def test_list_namespaces(self, client):
        client.post("/namespaces", json={"name": "db"})
        r = client.get("/namespaces")
        assert r.status_code == 200
        data = r.json()
        assert "namespaces" in data

    def test_set_config_value(self, client):
        client.post("/namespaces", json={"name": "settings"})
        r = client.put(
            "/config/settings/timeout_seconds",
            json={"value": "30", "description": "Request timeout"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["key"] == "timeout_seconds"

    def test_get_config_value(self, client):
        client.post("/namespaces", json={"name": "feature_flags"})
        client.put("/config/feature_flags/dark_mode", json={"value": "true"})
        r = client.get("/config/feature_flags/dark_mode")
        assert r.status_code == 200
        data = r.json()
        assert data["value"] == "true"

    def test_get_all_namespace_config(self, client):
        client.post("/namespaces", json={"name": "limits"})
        client.put("/config/limits/max_connections", json={"value": "100"})
        client.put("/config/limits/rate_limit_rps", json={"value": "50"})
        r = client.get("/config/limits")
        assert r.status_code == 200
        data = r.json()
        assert "keys" in data
        assert data["count"] == 2

    def test_delete_config_key(self, client):
        client.post("/namespaces", json={"name": "temp"})
        client.put("/config/temp/delete_me", json={"value": "gone"})
        r = client.delete("/config/temp/delete_me")
        assert r.status_code == 200

    def test_bulk_set(self, client):
        client.post("/namespaces", json={"name": "bulk"})
        r = client.post(
            "/config/bulk/bulk",
            json={
                "entries": [
                    {"key": "k1", "value": "v1"},
                    {"key": "k2", "value": "v2"},
                    {"key": "k3", "value": "v3"},
                ]
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] == 3

    def test_config_history(self, client):
        client.post("/namespaces", json={"name": "hist"})
        client.put("/config/hist/version", json={"value": "1"})
        client.put("/config/hist/version", json={"value": "2"})
        r = client.get("/config/hist/version/history")
        assert r.status_code == 200
        data = r.json()
        assert "history" in data

    def test_delete_namespace(self, client):
        client.post("/namespaces", json={"name": "cleanup"})
        r = client.delete("/namespaces/cleanup")
        assert r.status_code == 200


# ===========================================================================
# audit-service (8025)
# ===========================================================================


class TestAuditService:
    """Tests for audit-service: hash-chained append-only audit log."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "audit.db")
        with patch.object(audit_mod, "DB_PATH", db_path):
            audit_mod.init_db()
            secret = getattr(audit_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(audit_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "chain_tip" in data

    def test_write_audit_entry(self, client):
        r = client.post(
            "/audit",
            json={
                "actor": "user:alice",
                "action": "login",
                "resource": "auth",
                "outcome": "success",
            },
        )
        assert r.status_code == 201
        data = r.json()
        # audit-service returns {id, actor, action, timestamp, chain_hash, prev_hash}
        assert "id" in data
        assert "chain_hash" in data

    def test_write_batch(self, client):
        r = client.post(
            "/audit/batch",
            json={
                "entries": [
                    {"actor": "user:bob", "action": "view", "resource": "dashboard"},
                    {"actor": "user:bob", "action": "export", "resource": "report"},
                ]
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["inserted"] == 2

    def test_list_audit_entries(self, client):
        client.post("/audit", json={"actor": "system", "action": "startup"})
        r = client.get("/audit")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert data["total"] >= 1

    def test_filter_by_actor(self, client):
        client.post("/audit", json={"actor": "user:charlie", "action": "delete"})
        r = client.get("/audit?actor=user:charlie")
        assert r.status_code == 200
        data = r.json()
        assert all(e["actor"] == "user:charlie" for e in data["entries"])

    def test_get_entry_by_id(self, client):
        created = client.post(
            "/audit", json={"actor": "user:alice", "action": "update", "resource": "profile"}
        ).json()
        # ID returned as integer in 'id' field
        entry_id = created["id"]
        r = client.get(f"/audit/{entry_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == entry_id

    def test_chain_integrity(self, client):
        client.post("/audit", json={"actor": "a", "action": "x"})
        client.post("/audit", json={"actor": "b", "action": "y"})
        r = client.get("/audit/verify/chain")
        assert r.status_code == 200
        data = r.json()
        assert "valid" in data
        assert data["valid"] is True

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_entries" in data


# ===========================================================================
# rate-limit-service (8026)
# ===========================================================================


class TestRateLimitService:
    """Tests for rate-limit-service: token-bucket rate limiter."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "ratelimit.db")
        saved = dict(rate_limit_mod._buckets)
        with patch.object(rate_limit_mod, "DB_PATH", db_path):
            rate_limit_mod._buckets.clear()
            rate_limit_mod.init_db()
            secret = getattr(rate_limit_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(rate_limit_mod.app, headers=headers)
        rate_limit_mod._buckets.clear()
        rate_limit_mod._buckets.update(saved)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_policy(self, client):
        r = client.post(
            "/policies",
            json={"name": "api", "capacity": 100, "refill_rate": 10.0, "description": "API policy"},
        )
        assert r.status_code == 201
        data = r.json()
        # Returns {name, capacity, refill_rate}
        assert data["name"] == "api"
        assert data["capacity"] == 100

    def test_list_policies(self, client):
        client.post("/policies", json={"name": "web", "capacity": 50, "refill_rate": 5.0})
        r = client.get("/policies")
        assert r.status_code == 200
        data = r.json()
        assert "policies" in data

    def test_check_rate_limit_allowed(self, client):
        client.post("/policies", json={"name": "test-policy", "capacity": 100, "refill_rate": 10.0})
        r = client.post("/check", json={"key": "user:123", "policy": "test-policy", "tokens": 1})
        assert r.status_code == 200
        data = r.json()
        assert data["allowed"] is True

    def test_peek_rate_limit(self, client):
        client.post("/policies", json={"name": "peek-pol", "capacity": 20, "refill_rate": 2.0})
        r = client.post("/peek", json={"key": "user:456", "policy": "peek-pol", "tokens": 1})
        assert r.status_code == 200
        data = r.json()
        # Peek returns {key, tokens_available, capacity, policy}
        assert "tokens_available" in data
        assert "capacity" in data

    def test_delete_bucket(self, client):
        client.post("/policies", json={"name": "del-pol", "capacity": 10, "refill_rate": 1.0})
        client.post("/check", json={"key": "user:del", "policy": "del-pol", "tokens": 1})
        r = client.delete("/buckets/user:del")
        assert r.status_code == 200

    def test_update_policy(self, client):
        client.post("/policies", json={"name": "update-me", "capacity": 10, "refill_rate": 1.0})
        r = client.patch("/policies/update-me", json={"capacity": 20, "refill_rate": 2.0})
        assert r.status_code == 200
        data = r.json()
        # Returns {updated, evicted_buckets}
        assert data["updated"] == "update-me"

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        data = r.json()
        assert "active_buckets" in data


# ===========================================================================
# geo-service (8027)
# ===========================================================================


class TestGeoService:
    """Tests for geo-service: IP geolocation and distance calculation."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "geo.db")
        with patch.object(geo_mod, "DB_PATH", db_path):
            geo_mod.init_db()
            secret = getattr(geo_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(geo_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_lookup_localhost(self, client):
        """Localhost IPs return special local response."""
        r = client.get("/lookup/127.0.0.1")
        assert r.status_code == 200
        data = r.json()
        assert data["ip"] == "127.0.0.1"
        assert data["source"] == "local"

    def test_lookup_private_ip(self, client):
        """Private IP lookup returns a response (stub/fallback)."""
        r = client.get("/lookup/192.168.1.1")
        assert r.status_code == 200
        data = r.json()
        assert "ip" in data

    def test_batch_lookup(self, client):
        r = client.post("/lookup/batch", json={"ips": ["127.0.0.1", "::1"]})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert len(data["results"]) == 2

    def test_distance_calculation(self, client):
        r = client.post(
            "/distance",
            json={
                "lat1": 40.7128,
                "lon1": -74.0060,
                "lat2": 51.5074,
                "lon2": -0.1278,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "distance_km" in data
        # NYC to London is roughly 5570 km
        assert data["distance_km"] > 5000

    def test_cache_stats(self, client):
        # Seed cache with a lookup first
        client.get("/lookup/127.0.0.1")
        r = client.get("/cache")
        assert r.status_code == 200
        data = r.json()
        # Returns {total_cached, fresh, stale, by_source}
        assert "total_cached" in data

    def test_delete_from_cache(self, client):
        client.get("/lookup/127.0.0.1")
        r = client.delete("/cache/127.0.0.1")
        assert r.status_code == 200
        data = r.json()
        assert "evicted" in data


# ===========================================================================
# cdn-service (8028)
# ===========================================================================


class TestCdnService:
    """Tests for cdn-service: static asset caching and serving."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "cdn.db")
        assets_root = tmp_path / "assets"
        assets_root.mkdir()
        with (
            patch.object(cdn_mod, "DB_PATH", db_path),
            patch.object(cdn_mod, "ASSETS_ROOT", assets_root),
        ):
            cdn_mod.init_db()
            secret = getattr(cdn_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(cdn_mod.app, headers=headers), assets_root

    def test_health(self, client):
        client, _ = client
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_list_assets(self, client):
        client, _ = client
        r = client.get("/assets")
        assert r.status_code == 200
        data = r.json()
        assert "assets" in data

    def test_asset_stats(self, client):
        client, _ = client
        r = client.get("/assets/stats")
        assert r.status_code == 200
        data = r.json()
        # Returns {by_policy, top_assets}
        assert "by_policy" in data

    def test_register_asset(self, client):
        client, assets_root = client
        # Create a real file in ASSETS_ROOT
        (assets_root / "logo.png").write_bytes(b"\x89PNG\r\n")
        r = client.post(
            "/register",
            json={"path": "/logo.png", "content_type": "image/png", "cache_ttl": 86400},
        )
        assert r.status_code == 200
        data = r.json()
        assert "registered" in data

    def test_serve_static_file(self, client):
        client, assets_root = client
        (assets_root / "style.css").write_text("body { margin: 0; }")
        # Register then serve
        client.post("/register", json={"path": "/style.css", "content_type": "text/css"})
        r = client.get("/static/style.css")
        assert r.status_code == 200

    def test_serve_missing_file(self, client):
        client, _ = client
        r = client.get("/static/nonexistent.js")
        assert r.status_code == 404


# ===========================================================================
# health-aggregator (8029)
# ===========================================================================


class TestHealthAggregator:
    """Tests for health-aggregator: multi-service health rollup."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = str(tmp_path / "health_agg.db")
        # health-aggregator uses _latest dict (module-level)
        saved = dict(health_agg_mod._latest)
        with patch.object(health_agg_mod, "DB_PATH", db_path):
            health_agg_mod._latest.clear()
            health_agg_mod.init_db()
            secret = getattr(health_agg_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(health_agg_mod.app, headers=headers)
        health_agg_mod._latest.clear()
        health_agg_mod._latest.update(saved)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_register_service(self, client):
        r = client.post(
            "/services",
            json={
                "name": "tranc3-api",
                "url": "http://localhost:8000/health",
                "interval_seconds": 30,
            },
        )
        assert r.status_code == 201
        data = r.json()
        # Returns {registered, url}
        assert data["registered"] == "tranc3-api"

    def test_list_services(self, client):
        client.post(
            "/services",
            json={
                "name": "infinity-auth",
                "url": "http://localhost:8005/health",
                "interval_seconds": 60,
            },
        )
        r = client.get("/services")
        assert r.status_code == 200
        data = r.json()
        assert "services" in data

    def test_get_overall_status(self, client):
        r = client.get("/status")
        assert r.status_code == 200
        data = r.json()
        # Returns {summary, services}
        assert "summary" in data
        assert "services" in data

    def test_get_service_status_after_register(self, client):
        """Status for a newly registered service that hasn't been polled yet returns 404."""
        client.post(
            "/services",
            json={
                "name": "polled-svc",
                "url": "http://localhost:9999/health",
                "interval_seconds": 30,
            },
        )
        # Not in _latest yet — should return 404
        r = client.get("/status/polled-svc")
        assert r.status_code == 404

    def test_service_history(self, client):
        client.post(
            "/services",
            json={
                "name": "history-svc",
                "url": "http://localhost:8000/health",
                "interval_seconds": 60,
            },
        )
        r = client.get("/history/history-svc")
        assert r.status_code == 200
        data = r.json()
        assert "history" in data

    def test_delete_service(self, client):
        client.post(
            "/services",
            json={
                "name": "delete-svc",
                "url": "http://localhost:8000/health",
                "interval_seconds": 60,
            },
        )
        r = client.delete("/services/delete-svc")
        assert r.status_code == 200


# ===========================================================================
# identity-service (8015)
# ===========================================================================


class TestIdentityService:
    """Tests for identity-service: identity record management."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = tmp_path / "identity.db"
        with patch.object(identity_mod, "DB_PATH", db_path):
            identity_mod.db = identity_mod.IdentitiesDatabase(db_path)
            secret = getattr(identity_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(identity_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_identity(self, client):
        r = client.post(
            "/",
            json={
                "user_id": "u-001",
                "provider": "local",
                "provider_id": "alice@example.com",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "identity_id" in data

    def test_list_identities(self, client):
        client.post(
            "/",
            json={"user_id": "u-002", "provider": "google", "provider_id": "google|12345"},
        )
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "data" in data

    def test_get_identity(self, client):
        created = client.post(
            "/",
            json={"user_id": "u-003", "provider": "github", "provider_id": "gh|67890"},
        ).json()
        identity_id = created["identity_id"]
        r = client.get(f"/{identity_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["identity_id"] == identity_id

    def test_get_nonexistent_identity(self, client):
        r = client.get("/nonexistent-id-xyz")
        assert r.status_code == 404

    def test_update_identity(self, client):
        created = client.post(
            "/",
            json={"user_id": "u-004", "provider": "local", "provider_id": "bob"},
        ).json()
        identity_id = created["identity_id"]
        r = client.patch(f"/{identity_id}", json={"verified": 1})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_delete_identity(self, client):
        created = client.post(
            "/",
            json={"user_id": "u-005", "provider": "local", "provider_id": "charlie"},
        ).json()
        identity_id = created["identity_id"]
        r = client.delete(f"/{identity_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True


# ===========================================================================
# the-grid (8010)
# ===========================================================================


class TestTheGrid:
    """Tests for The Digital Grid: DAG-based workflow orchestration."""

    @pytest.fixture
    def client(self, tmp_path):
        db_path = tmp_path / "grid.db"
        with patch.object(grid_mod, "DB_PATH", db_path):
            grid_mod.db = grid_mod.GridDatabase(db_path)
            grid_mod.engine = grid_mod.WorkflowEngine(grid_mod.db)
            secret = getattr(grid_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(grid_mod.app, headers=headers)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_workflow(self, client):
        r = client.post(
            "/workflows",
            json={
                "name": "Simple Pipeline",
                "description": "A test workflow",
                "steps": [
                    {
                        "step_id": "step-1",
                        "name": "Transform",
                        "action": "transform",
                        "config": {"mapping": {"out": "input.value"}},
                        "depends_on": [],
                    }
                ],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "workflow_id" in data

    def test_list_workflows(self, client):
        client.post(
            "/workflows",
            json={"name": "WF1", "steps": [{"name": "S1", "action": "transform", "config": {}}]},
        )
        r = client.get("/workflows")
        assert r.status_code == 200
        data = r.json()
        assert "workflows" in data

    def test_get_workflow(self, client):
        created = client.post(
            "/workflows",
            json={"name": "Get WF", "steps": [{"name": "S1", "action": "transform", "config": {}}]},
        ).json()
        wf_id = created["workflow_id"]
        r = client.get(f"/workflows/{wf_id}")
        assert r.status_code == 200

    def test_delete_workflow(self, client):
        created = client.post(
            "/workflows",
            json={"name": "Del WF", "steps": [{"name": "S1", "action": "transform", "config": {}}]},
        ).json()
        wf_id = created["workflow_id"]
        r = client.delete(f"/workflows/{wf_id}")
        assert r.status_code == 200

    def test_execute_workflow(self, client):
        created = client.post(
            "/workflows",
            json={
                "name": "Execute WF",
                "steps": [
                    {
                        "step_id": "s1",
                        "name": "Transform",
                        "action": "transform",
                        "config": {"mapping": {"result": "input.x"}},
                        "depends_on": [],
                    }
                ],
            },
        ).json()
        wf_id = created["workflow_id"]
        r = client.post(f"/workflows/{wf_id}/execute", json={"input": {"x": 42}})
        assert r.status_code in (200, 202)
        data = r.json()
        assert "execution_id" in data

    def test_list_executions(self, client):
        r = client.get("/executions")
        assert r.status_code == 200
        data = r.json()
        assert "executions" in data

    def test_get_execution(self, client):
        created = client.post(
            "/workflows",
            json={
                "name": "Exec Get WF",
                "steps": [
                    {
                        "step_id": "s1",
                        "name": "S1",
                        "action": "transform",
                        "config": {},
                        "depends_on": [],
                    }
                ],
            },
        ).json()
        wf_id = created["workflow_id"]
        exec_resp = client.post(f"/workflows/{wf_id}/execute", json={"input": {}}).json()
        exec_id = exec_resp["execution_id"]
        r = client.get(f"/executions/{exec_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["execution_id"] == exec_id


# ===========================================================================
# Enhanced users-service new endpoints (Phase 19.1 regression)
# ===========================================================================


class TestEnhancedUsersService:
    """Tests for new users-service features added in Phase 19."""

    @pytest.fixture
    def users_v2_mod(self):
        """Import the Phase 19 users-service."""
        root = _TRANC3_ROOT
        mod = _import_worker(
            "users_service_worker_v2",
            root / "workers" / "users-service" / "worker.py",
        )
        return mod

    @pytest.fixture
    def client(self, users_v2_mod, tmp_path):
        db_path = str(tmp_path / "users_v2.db")
        with patch.object(users_v2_mod, "DATABASE_PATH", db_path):
            users_v2_mod.db = users_v2_mod.UsersDatabase(db_path)
            secret = getattr(users_v2_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            yield TestClient(users_v2_mod.app, headers=headers)

    def _create_user(self, client, suffix=""):
        username = f"user{suffix or str(uuid.uuid4())[:8]}"
        return client.post(
            "/users",
            json={
                "username": username,
                "email": f"{username}@example.com",
            },
        ).json()

    def test_create_user_with_bio(self, client):
        r = client.post(
            "/users",
            json={
                "username": "biographer",
                "email": "bio@example.com",
                "bio": "Software engineer passionate about distributed systems.",
                "timezone": "America/New_York",
                "avatar_url": "https://example.com/avatar.png",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["bio"] == "Software engineer passionate about distributed systems."
        assert data["timezone"] == "America/New_York"
        assert data["avatar_url"] == "https://example.com/avatar.png"

    def test_lock_and_unlock_user(self, client):
        user = self._create_user(client)
        user_id = user["user_id"]
        r = client.post(f"/users/{user_id}/lock")
        assert r.status_code == 200
        assert r.json()["user_id"] == user_id
        r = client.post(f"/users/{user_id}/unlock")
        assert r.status_code == 200

    def test_record_login(self, client):
        user = self._create_user(client)
        user_id = user["user_id"]
        r = client.post(f"/users/{user_id}/login")
        assert r.status_code == 200
        data = r.json()
        assert "last_login" in data

    def test_locked_user_cannot_login(self, client):
        user = self._create_user(client)
        user_id = user["user_id"]
        client.post(f"/users/{user_id}/lock")
        r = client.post(f"/users/{user_id}/login")
        assert r.status_code == 403

    def test_search_users(self, client):
        uid = str(uuid.uuid4())[:8]
        client.post(
            "/users",
            json={"username": f"searchuser{uid}", "email": f"search{uid}@example.com"},
        )
        r = client.get(f"/users/search/query?q=searchuser{uid}")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    def test_update_role(self, client):
        user = self._create_user(client)
        user_id = user["user_id"]
        r = client.patch(f"/users/{user_id}/role", json={"role": "admin"})
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"

    def test_password_reset_request(self, client):
        uid = str(uuid.uuid4())[:8]
        client.post(
            "/users",
            json={"username": f"resetuser{uid}", "email": f"reset{uid}@example.com"},
        )
        r = client.post(
            "/users/password-reset/request",
            json={"email": f"reset{uid}@example.com"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "reset_token" in data
        assert len(data["reset_token"]) > 0

    def test_password_reset_unknown_email(self, client):
        r = client.post(
            "/users/password-reset/request",
            json={"email": "unknown@example.com"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reset_token"] == ""

    def test_bulk_deactivate(self, client):
        u1 = self._create_user(client)
        u2 = self._create_user(client)
        r = client.post(
            "/admin/users/bulk-deactivate",
            json={"user_ids": [u1["user_id"], u2["user_id"], "nonexistent-id"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert "nonexistent-id" in data["not_found"]

    def test_roles_summary(self, client):
        client.post(
            "/users",
            json={"username": "admin_user", "email": "admin@roles.com", "role": "admin"},
        )
        r = client.get("/admin/users/roles/summary")
        assert r.status_code == 200
        data = r.json()
        assert "roles" in data

    def test_list_users_filter_by_role(self, client):
        uid = str(uuid.uuid4())[:8]
        client.post(
            "/users",
            json={"username": f"only_admin{uid}", "email": f"oa{uid}@example.com", "role": "admin"},
        )
        r = client.get("/users?role=admin")
        assert r.status_code == 200
        data = r.json()
        assert all(u["role"] == "admin" for u in data["users"])

    def test_list_users_active_only(self, client):
        uid = str(uuid.uuid4())[:8]
        user = client.post(
            "/users",
            json={"username": f"inactive{uid}", "email": f"inactive{uid}@example.com"},
        ).json()
        client.delete(f"/users/{user['user_id']}")
        r = client.get("/users?active_only=true")
        assert r.status_code == 200
        data = r.json()
        assert all(u["is_active"] for u in data["users"])

    def test_health_includes_active_count(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "active_count" in data

    def test_preferences_serialised_as_json(self, client):
        """Preferences must round-trip as dict, not string."""
        user = client.post(
            "/users",
            json={
                "username": "prefs_user",
                "email": "prefs@example.com",
                "preferences": {"theme": "dark", "lang": "en"},
            },
        ).json()
        user_id = user["user_id"]
        fetched = client.get(f"/users/{user_id}").json()
        assert isinstance(fetched["preferences"], dict)
        assert fetched["preferences"]["theme"] == "dark"
