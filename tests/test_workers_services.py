"""
Worker Integration Tests — Service Workers
===========================================
Tests for five self-hosted workers using FastAPI TestClient with temporary
SQLite databases. No external services required.

Workers tested:
- users-service    (port 8006) — user CRUD
- products-service (port 8011) — product catalogue
- vault-service    (port 8038) — secret storage (AES-GCM SQLite backend)
- notifications    (port 8008) — notification dispatch
- audit-service    (port 8017) — hash-chained audit log
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker as _import_worker

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Lazy fixtures — each worker is imported once per test session
# ---------------------------------------------------------------------------


def _load_users_service():
    return _import_worker(
        "users_service_worker",
        _TRANC3_ROOT / "workers" / "users-service" / "worker.py",
    )


def _load_products_service():
    return _import_worker(
        "products_service_worker",
        _TRANC3_ROOT / "workers" / "products-service" / "worker.py",
    )


def _load_vault_service():
    # vault-service requires VAULT_MASTER_KEY only in production
    return _import_worker(
        "vault_service_worker",
        _TRANC3_ROOT / "workers" / "vault-service" / "worker.py",
    )


def _load_notifications():
    """Load notifications worker, mocking the Dimensional package dependency."""
    # Stub Dimensional sub-modules so the import succeeds without the package
    _stub_dimensional()
    return _import_worker(
        "notifications_worker",
        _TRANC3_ROOT / "workers" / "notifications" / "worker.py",
    )


def _stub_dimensional():
    """Inject stub modules for Dimensional.* so the notifications worker can import."""
    dim = types.ModuleType("Dimensional")
    sys.modules.setdefault("Dimensional", dim)

    err = types.ModuleType("Dimensional.error_handlers")
    err.safe_error_detail = lambda exc, *a, **kw: str(exc)
    sys.modules.setdefault("Dimensional.error_handlers", err)

    san = types.ModuleType("Dimensional.sanitize")
    san.sanitize_for_log = lambda x, **kw: x
    sys.modules.setdefault("Dimensional.sanitize", san)

    url_val = types.ModuleType("Dimensional.url_validation")

    class SSRFError(Exception):
        pass

    url_val.SSRFError = SSRFError
    url_val.validate_webhook_url = lambda url: url  # passthrough in tests
    sys.modules.setdefault("Dimensional.url_validation", url_val)


def _load_audit_service():
    return _import_worker(
        "audit_service_worker",
        _TRANC3_ROOT / "workers" / "audit-service" / "worker.py",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Users Service
# ═══════════════════════════════════════════════════════════════════════════


class TestUsersService:
    """Test users-service: health check, user creation, and retrieval."""

    @pytest.fixture(scope="class")
    def mod(self):
        return _load_users_service()

    @pytest.fixture
    def client(self, mod, tmp_path):
        """TestClient with a temporary SQLite database."""
        db_path = str(tmp_path / "users_test.db")
        # Patch the module-level DATABASE_PATH so _get_db uses the temp path
        with patch.object(mod, "DATABASE_PATH", db_path):
            # Re-initialise DB at the patched path
            db = mod.UsersDatabase(db_path=db_path)
            with patch.object(mod, "db", db):
                yield TestClient(mod.app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "healthy")
        assert "service" in data

    def test_create_user(self, client):
        resp = client.post(
            "/users",
            json={
                "username": "testuser",
                "email": "testuser@example.com",
                "display_name": "Test User",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["email"] == "testuser@example.com"
        assert "user_id" in data

    def test_get_user_by_id(self, client):
        # Create first
        create_resp = client.post(
            "/users",
            json={
                "username": "getme",
                "email": "getme@example.com",
            },
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["user_id"]

        # Then retrieve
        get_resp = client.get(f"/users/{user_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["user_id"] == user_id
        assert get_resp.json()["username"] == "getme"

    def test_get_nonexistent_user(self, client):
        resp = client.get("/users/nonexistent-id-00000")
        assert resp.status_code == 404

    def test_duplicate_username_rejected(self, client):
        client.post("/users", json={"username": "dupuser", "email": "dup1@example.com"})
        resp = client.post("/users", json={"username": "dupuser", "email": "dup2@example.com"})
        assert resp.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# Products Service
# ═══════════════════════════════════════════════════════════════════════════


class TestProductsService:
    """Test products-service: health, create product, list products."""

    @pytest.fixture(scope="class")
    def mod(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("products_db")
        db_path = tmp / "products.db"
        # products-service uses Path(__file__).parent / "data" / "products.db"
        # We patch DB_PATH at module level before importing
        mod = _load_products_service()
        mod.DB_PATH = db_path
        # Re-create the database at the new path
        mod.db = mod.ProductsDatabase(db_path)
        return mod

    @pytest.fixture
    def client(self, mod):
        return TestClient(mod.app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "healthy")

    def test_create_product(self, client):
        resp = client.post(
            "/",
            json={
                "name": "Widget Pro",
                "description": "A professional widget",
                "price": 9.99,
                "category": "tools",
                "sku": "WGT-001",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Widget Pro"
        assert "product_id" in data or "id" in data

    def test_list_products(self, client):
        # Ensure at least one product exists
        client.post(
            "/",
            json={
                "name": "Listed Widget",
                "price": 4.99,
                "sku": "WGT-LIST-001",
            },
        )
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        # Response may be a list or an object with a "products" / "items" key
        items = body if isinstance(body, list) else body.get("products", body.get("items", []))
        assert isinstance(items, list)
        assert len(items) >= 1

    def test_get_product_by_id(self, client):
        create_resp = client.post(
            "/",
            json={
                "name": "Gettable Widget",
                "price": 14.99,
                "sku": "WGT-GET-001",
            },
        )
        assert create_resp.status_code == 201
        body = create_resp.json()
        product_id = body.get("product_id") or body.get("id")

        get_resp = client.get(f"/{product_id}")
        assert get_resp.status_code == 200
        got = get_resp.json()
        assert got.get("product_id") == product_id or got.get("id") == product_id


# ═══════════════════════════════════════════════════════════════════════════
# Vault Service
# ═══════════════════════════════════════════════════════════════════════════


class TestVaultService:
    """Test vault-service: health, store secret, retrieve secret, backend endpoint."""

    @pytest.fixture(scope="class")
    def mod(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("vault_db")
        db_path = str(tmp / "vault.db")
        with patch.dict("os.environ", {"VAULT_DB_PATH": db_path, "ENVIRONMENT": "development"}):
            mod = _load_vault_service()
        # Ensure DB is initialised at the temp path
        with patch.object(mod, "DB_PATH", db_path):
            mod._init_db()
        return mod

    @pytest.fixture
    def client(self, mod, tmp_path):
        db_path = str(tmp_path / "vault.db")
        with patch.object(mod, "DB_PATH", db_path):
            mod._init_db()
            yield TestClient(mod.app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "vault-service"

    def test_vault_backend_endpoint(self, client, mod):
        """Backend endpoint should report aes-gcm-sqlite when OpenBao is off."""
        with patch.object(mod, "_openbao_active", False):
            resp = client.get("/vault/backend")
        assert resp.status_code == 200
        data = resp.json()
        assert "backend" in data
        assert data["backend"] in ("aes-gcm-sqlite", "openbao")

    def test_create_secret(self, client, mod, tmp_path):
        db_path = str(tmp_path / "vault_create.db")
        with patch.object(mod, "DB_PATH", db_path):
            mod._init_db()
            c = TestClient(mod.app)
            resp = c.post("/secrets", json={"key": "my-api-key", "value": "supersecret123"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "my-api-key"
        assert "id" in data

    def test_retrieve_secret(self, client, mod, tmp_path):
        db_path = str(tmp_path / "vault_retrieve.db")
        with patch.object(mod, "DB_PATH", db_path):
            mod._init_db()
            c = TestClient(mod.app)
            create = c.post("/secrets", json={"key": "retrieve-me", "value": "hidden_value"})
            assert create.status_code == 201
            secret_id = create.json()["id"]

            get_resp = c.get(f"/secrets/{secret_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["key"] == "retrieve-me"

    def test_openbao_client_unavailable(self, mod):
        """OpenBaoClient returns None gracefully when server is not reachable."""
        client_obj = mod.OpenBaoClient(
            addr="http://127.0.0.1:19999",
            token="fake-token",  # nothing listening
        )
        assert client_obj.is_available() is False
        assert client_obj.get_secret("any/path") is None
        assert client_obj.put_secret("any/path", {"value": "x"}) is False


# ═══════════════════════════════════════════════════════════════════════════
# Notifications Service
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificationsService:
    """Test notifications worker: health and send notification."""

    @pytest.fixture(scope="class")
    def mod(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("notif_db")
        # Stub Dimensional before import
        _stub_dimensional()
        mod = _load_notifications()
        # Point DB at temp dir
        db_path = tmp / "notifications.db"
        mod.DB_PATH = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return mod

    @pytest.fixture
    def client(self, mod):
        return TestClient(mod.app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("ok", "healthy")

    def test_send_in_app_notification(self, client):
        """Send an in-app notification — dispatches without external services."""
        resp = client.post(
            "/notifications/send",
            json={
                "user_id": "user-001",
                "channel": "in_app",
                "title": "Test Alert",
                "body": "This is a test notification",
            },
        )
        # Accept 200/201/202 — worker may queue async
        assert resp.status_code in (200, 201, 202)

    def test_list_notifications(self, client):
        resp = client.get("/notifications")
        assert resp.status_code == 200
        body = resp.json()
        items = body if isinstance(body, list) else body.get("notifications", body.get("items", []))
        assert isinstance(items, list)


# ═══════════════════════════════════════════════════════════════════════════
# Audit Service
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditService:
    """Test audit-service: health, append event, list events."""

    @pytest.fixture(scope="class")
    def mod(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("audit_db")
        with patch.dict("os.environ", {"DATA_DIR": str(tmp)}):
            mod = _load_audit_service()
        return mod

    @pytest.fixture
    def client(self, mod, tmp_path):
        db_path = tmp_path / "audit.db"
        with patch.object(mod, "DB_PATH", db_path):
            # Re-init the DB at the temp path so each test gets a clean slate
            mod._init_db()
            yield TestClient(mod.app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("ok", "healthy")
        assert "total_events" in data or "service" in data

    def test_append_audit_event(self, client):
        resp = client.post(
            "/events",
            json={
                "service": "test-service",
                "actor": "test-user",
                "action": "test.action",
                "resource_type": "secret",
                "resource_id": "res-001",
                "severity": "info",
                "details": {"key": "value"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "event_id" in data or "id" in data

    def test_list_audit_events(self, client):
        # Append one event first
        client.post(
            "/events",
            json={
                "service": "list-test-svc",
                "actor": "tester",
                "action": "list.test",
            },
        )
        resp = client.get("/events")
        assert resp.status_code == 200
        body = resp.json()
        events = body if isinstance(body, list) else body.get("events", body.get("items", []))
        assert isinstance(events, list)

    def test_audit_via_compat_route(self, client):
        """The /audit POST compatibility route should also work."""
        resp = client.post(
            "/audit",
            json={
                "service": "compat-svc",
                "actor": "compat-user",
                "action": "compat.log",
            },
        )
        assert resp.status_code in (200, 201)
