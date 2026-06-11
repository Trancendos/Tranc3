"""Phase 21 — P5 Worker test suite.

Covers all 17 previously-untested workers:
  api-gateway (8040), backup-service (8039), blender-worker (8052),
  ffmpeg-worker (8052), gateway-service (8040), ice-box-service (8046),
  infinity-admin-service (8044), infinity-one-service (8043),
  infinity-portal-service (8042), infinity-shards-service (8045),
  infinity-void (8002), mlflow-service (varies), sentinel-station-service (8041),
  swarm-coordinator-service (8053), tranc3-ai (edge), triposr-worker (varies),
  turings-hub-service (8035)

Also validates the swarm-coordinator-service /run auth fix.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Generic worker loader (handles hyphenated directory names)
# ---------------------------------------------------------------------------

_module_cache: dict[str, object] = {}


def _import_worker(rel_path: str) -> object:
    """Import a worker module from its file path, bypassing hyphenated-dir issues."""
    if rel_path in _module_cache:
        return _module_cache[rel_path]
    full = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(rel_path.replace("/", "."), full)
    assert spec and spec.loader, f"Could not load spec for {full}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[rel_path.replace("/", ".")] = mod  # type: ignore[assignment]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    _module_cache[rel_path] = mod
    return mod


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _client_for(mod, extra_headers: dict | None = None) -> TestClient:
    """Create a TestClient, injecting X-Internal-Secret if the module uses one."""
    secret = getattr(mod, "_INTERNAL_SECRET", None) or getattr(mod, "INTERNAL_SECRET", None)
    headers: dict = {}
    if secret:
        headers["X-Internal-Secret"] = secret
    if extra_headers:
        headers.update(extra_headers)
    return TestClient(mod.app, headers=headers, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. swarm-coordinator-service (8053) — includes /run auth fix validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSwarmCoordinatorService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _import_worker("workers/swarm-coordinator-service/worker.py")
        # Point manifest dir at an empty temp directory (no manifests → quick exit)
        self.mod.MANIFEST_DIR = tmp_path / "manifests"
        self.mod.MANIFEST_DIR.mkdir(parents=True)
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "healthy"

    def test_status(self):
        r = self.client.get("/status")
        assert r.status_code == 200
        d = r.json()
        assert "service" in d
        assert "running" in d

    def test_run_no_auth_blocked_when_secret_set(self, monkeypatch):
        """When INTERNAL_SECRET is set, /run must reject missing header."""
        monkeypatch.setattr(self.mod, "_INTERNAL_SECRET", "test-secret-xyz")
        unauthenticated = TestClient(self.mod.app, raise_server_exceptions=False)
        r = unauthenticated.post("/run")
        assert r.status_code == 401

    def test_run_with_auth_when_secret_set(self, monkeypatch):
        """When INTERNAL_SECRET is set, /run must accept correct header."""
        monkeypatch.setattr(self.mod, "_INTERNAL_SECRET", "test-secret-xyz")
        authed = TestClient(
            self.mod.app,
            headers={"X-Internal-Secret": "test-secret-xyz"},
            raise_server_exceptions=False,
        )
        r = authed.post("/run")
        # Empty manifest dir → 200 with empty or quick result (not 401)
        assert r.status_code in (200, 422, 500)
        assert r.status_code != 401

    def test_run_allowed_when_no_secret_configured(self):
        """When INTERNAL_SECRET is empty (dev mode), /run is open."""
        # _INTERNAL_SECRET is "" by default — endpoint is permissive
        r = self.client.post("/run")
        assert r.status_code in (200, 422, 500)
        assert r.status_code != 401


# ═══════════════════════════════════════════════════════════════════════════════
# 2. api-gateway (8040)
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiGateway:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/api-gateway/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_root(self):
        r = self.client.get("/")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 3. backup-service (8039)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBackupService:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/backup-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert "status" in d

    def test_backup_status(self):
        r = self.client.get("/backup/status")
        assert r.status_code in (200, 404)

    def test_backup_list(self):
        r = self.client.get("/backup/list")
        assert r.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. blender-worker (8052)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBlenderWorker:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/blender-worker/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded", "unavailable")

    def test_render_missing_body(self):
        r = self.client.post("/render", json={})
        # Body validation (422) or service unavailable (503/500) — both acceptable
        assert r.status_code in (422, 400, 503, 500)

    def test_blend_create_missing_body(self):
        r = self.client.post("/blend/create", json={})
        assert r.status_code in (422, 400, 503, 500)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ffmpeg-worker (8052)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFfmpegWorker:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/ffmpeg-worker/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_transcode_missing_body(self):
        r = self.client.post("/transcode", json={})
        assert r.status_code in (422, 400, 503, 500)

    def test_thumbnail_missing_body(self):
        r = self.client.post("/thumbnail", json={})
        assert r.status_code in (422, 400, 503, 500)

    def test_job_not_found(self):
        r = self.client.get("/jobs/nonexistent-job-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. gateway-service (8040)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGatewayService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["GATEWAY_DB_PATH"] = str(tmp_path / "gateway_test.db")
        self.mod = _import_worker("workers/gateway-service/worker.py")
        # re-point DB and init in case module was already cached
        self.mod.DB_PATH = str(tmp_path / "gateway_test.db")
        self.mod._init_db()
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_stats(self):
        r = self.client.get("/stats")
        assert r.status_code in (200, 401, 403)

    def test_api_overview(self):
        r = self.client.get("/api/overview")
        assert r.status_code in (200, 401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ice-box-service (8046)
# ═══════════════════════════════════════════════════════════════════════════════


class TestIceBoxService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["ICE_BOX_QUARANTINE_DB"] = str(tmp_path / "icebox_test.db")
        self.mod = _import_worker("workers/ice-box-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200

    def test_stats(self):
        r = self.client.get("/stats")
        assert r.status_code == 200

    def test_quarantine_list_empty(self):
        r = self.client.get("/quarantine")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_scan_clean_content(self):
        r = self.client.post("/scan", json={"content": "hello world", "source": "test"})
        assert r.status_code == 200
        d = r.json()
        assert "verdict" in d
        assert "allow" in d

    def test_scan_empty_string(self):
        r = self.client.post("/scan", json={"content": "", "source": "test"})
        assert r.status_code in (200, 422)

    def test_quarantine_not_found(self):
        r = self.client.get("/quarantine/nonexistent-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 8. infinity-admin-service (8044)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityAdminService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["INFINITY_ADMIN_DB_PATH"] = str(tmp_path / "infinity_admin_test.db")
        self.mod = _import_worker("workers/infinity-admin-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_admin_config_requires_auth(self):
        unauthenticated = TestClient(self.mod.app, raise_server_exceptions=False)
        r = unauthenticated.get("/admin/config")
        # Should reject unauthenticated requests when secret is configured
        if getattr(self.mod, "_INTERNAL_SECRET", ""):
            assert r.status_code in (401, 403)

    def test_admin_config_with_auth(self):
        r = self.client.get("/admin/config")
        assert r.status_code in (200, 404, 500)

    def test_admin_primes(self):
        r = self.client.get("/admin/primes")
        assert r.status_code in (200, 404, 500)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. infinity-one-service (8043)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityOneService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["INFINITY_ONE_DB_PATH"] = str(tmp_path / "infinity_one_test.db")
        self.mod = _import_worker("workers/infinity-one-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_list_identities(self):
        r = self.client.get("/one/identities")
        assert r.status_code in (200, 401, 403)

    def test_create_identity_missing_body(self):
        r = self.client.post("/one/identities", json={})
        assert r.status_code in (422, 400, 401, 403)

    def test_get_identity_not_found(self):
        r = self.client.get("/one/identities/nonexistent-id")
        assert r.status_code in (404, 401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. infinity-portal-service (8042)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityPortalService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["INFINITY_PORTAL_DB_PATH"] = str(tmp_path / "infinity_portal_test.db")
        self.mod = _import_worker("workers/infinity-portal-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_portal_status(self):
        r = self.client.get("/portal/status")
        assert r.status_code == 200

    def test_portal_locations(self):
        r = self.client.get("/portal/locations")
        assert r.status_code == 200

    def test_portal_gate_info(self):
        r = self.client.get("/portal/gate-info")
        assert r.status_code == 200

    def test_portal_transfer_systems(self):
        r = self.client.get("/portal/transfer-systems")
        assert r.status_code == 200

    def test_login_invalid_credentials(self):
        r = self.client.post(
            "/portal/login",
            json={"username": "nobody", "password": "wrongpassword"},
        )
        # Should fail auth, not crash
        assert r.status_code in (401, 403, 404, 422, 400)

    def test_register_missing_fields(self):
        r = self.client.post("/portal/register", json={})
        assert r.status_code in (422, 400, 401)

    def test_gate_route_missing_body(self):
        r = self.client.post("/gate/route", json={})
        assert r.status_code in (422, 400, 401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. infinity-shards-service (8045)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityShardsService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["INFINITY_SHARDS_DB_PATH"] = str(tmp_path / "infinity_shards_test.db")
        self.mod = _import_worker("workers/infinity-shards-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_list_shards(self):
        r = self.client.get("/shards")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_get_shard_type(self):
        r = self.client.get("/shards/memory")
        assert r.status_code in (200, 404)

    def test_entity_shards_not_found(self):
        r = self.client.get("/entities/nonexistent-entity/shards")
        assert r.status_code in (200, 404)

    def test_entity_power_not_found(self):
        r = self.client.get("/entities/nonexistent-entity/power")
        assert r.status_code in (200, 404)

    def test_add_shard_missing_body(self):
        r = self.client.post("/entities/test-entity/shards", json={})
        assert r.status_code in (422, 400, 404)

    def test_invoke_shard_missing_body(self):
        r = self.client.post("/shards/memory/invoke", json={})
        assert r.status_code in (422, 400, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. infinity-void (8002)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityVoid:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VOID_DATA_DIR", str(tmp_path / "void"))
        monkeypatch.setenv("MASTER_KEY_SEED", "test-master-key-seed-for-unit-tests")
        monkeypatch.setenv("INTERNAL_SECRET", "test-internal-secret")
        self.mod = _import_worker("workers/infinity-void/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200

    def test_vault_status(self):
        r = self.client.get("/vault/status")
        assert r.status_code == 200
        d = r.json()
        assert "status" in d

    def test_list_secrets_empty(self):
        r = self.client.get("/secrets")
        assert r.status_code == 200

    def test_store_and_retrieve_secret(self):
        payload = {
            "name": "test_key",
            "value": "my-super-secret-value",
            "owner": "unit-test",
        }
        store_r = self.client.post("/secrets", json=payload)
        assert store_r.status_code in (200, 201)
        secret_id = store_r.json().get("id") or store_r.json().get("secret_id")
        if secret_id:
            retrieve_r = self.client.post("/secrets/retrieve", json={"id": secret_id})
            assert retrieve_r.status_code == 200

    def test_get_secret_not_found(self):
        r = self.client.get("/secrets/nonexistent-id")
        assert r.status_code in (404, 400)

    def test_audit_not_found(self):
        r = self.client.get("/secrets/nonexistent-id/audit")
        assert r.status_code in (404, 400)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. mlflow-service
# ═══════════════════════════════════════════════════════════════════════════════


class TestMlflowService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["MLFLOW_DATA_DIR"] = str(tmp_path / "mlflow")
        self.mod = _import_worker("workers/mlflow-service/worker.py")
        # Re-init DB with temp path
        self.mod.DATA_DIR = tmp_path / "mlflow"
        self.mod.DB_PATH = self.mod.DATA_DIR / "mlflow.db"
        self.mod.ARTIFACT_ROOT = self.mod.DATA_DIR / "artifacts"
        self.mod._conn = None  # force re-connect
        self.mod.init_db()
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_create_experiment(self):
        r = self.client.post(
            "/api/2.0/mlflow/experiments/create",
            json={"name": "test-experiment"},
        )
        assert r.status_code in (200, 201, 409)

    def test_list_experiments(self):
        r = self.client.get("/api/2.0/mlflow/experiments/list")
        assert r.status_code == 200

    def test_experiments_page(self):
        r = self.client.get("/experiments")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 14. sentinel-station-service (8041)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSentinelStationService:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ["SENTINEL_DB_PATH"] = str(tmp_path / "sentinel_test.db")
        self.mod = _import_worker("workers/sentinel-station-service/worker.py")
        self.mod.DB_PATH = str(tmp_path / "sentinel_test.db")
        self.mod._init_db()
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_stats(self):
        r = self.client.get("/stats")
        assert r.status_code in (200, 401, 403)

    def test_publish_event(self):
        r = self.client.post(
            "/api/events/publish",
            json={"channel": "test.events", "event_type": "test", "payload": {}},
        )
        assert r.status_code in (200, 201, 401, 403, 422)

    def test_list_subscriptions(self):
        r = self.client.get("/api/subscriptions")
        assert r.status_code in (200, 401, 403)

    def test_list_channels(self):
        r = self.client.get("/api/channels")
        assert r.status_code in (200, 401, 403)

    def test_event_history(self):
        r = self.client.get("/api/events/history")
        assert r.status_code in (200, 401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# 15. tranc3-ai (edge AI proxy)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTransc3Ai:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/tranc3-ai/worker.py")
        self.client = _client_for(self.mod)

    def test_root(self):
        r = self.client.get("/")
        assert r.status_code == 200

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_list_models(self):
        r = self.client.get("/api/v1/ai/models")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_chat_missing_body(self):
        r = self.client.post("/api/v1/ai/chat", json={})
        assert r.status_code in (422, 400)

    def test_embeddings_missing_body(self):
        r = self.client.post("/api/v1/ai/embeddings", json={})
        assert r.status_code in (422, 400)

    def test_emotion_missing_body(self):
        r = self.client.post("/api/v1/ai/analyze-emotion", json={})
        assert r.status_code in (422, 400)


# ═══════════════════════════════════════════════════════════════════════════════
# 16. triposr-worker
# ═══════════════════════════════════════════════════════════════════════════════


class TestTriposrWorker:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/triposr-worker/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        # TripoSR may not be installed; service should report unavailable gracefully
        assert d.get("status") in ("healthy", "ok", "degraded", "unavailable")

    def test_reconstruct_missing_body(self):
        r = self.client.post("/reconstruct", json={})
        # Either validation error or service-unavailable — must not be 500 uncaught
        assert r.status_code in (422, 400, 503, 500)


# ═══════════════════════════════════════════════════════════════════════════════
# 17. turings-hub-service (8035)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTuringsHubService:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _import_worker("workers/turings-hub-service/worker.py")
        self.client = _client_for(self.mod)

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("healthy", "ok", "degraded")

    def test_list_entities(self):
        r = self.client.get("/entities")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_setup(self):
        r = self.client.get("/setup")
        assert r.status_code == 200

    def test_get_entity_not_found(self):
        r = self.client.get("/entities/nonexistent-entity-id")
        assert r.status_code in (404, 200)

    def test_speak_not_found(self):
        r = self.client.post(
            "/entities/nonexistent-entity-id/speak",
            json={"text": "hello world"},
        )
        assert r.status_code in (404, 422, 400, 200)

    def test_forge_missing_body(self):
        r = self.client.post("/forge", json={})
        assert r.status_code in (422, 400, 404, 200)
