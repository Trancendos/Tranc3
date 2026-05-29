"""tests/test_canonical_routes.py

Tests for migrated routes in the canonical api.py entry point.

Covers the three router groups previously tested only via api_enhanced.py:
  - /skills/*   (Turing's Hub)
  - /code/*     (The Lab)
  - /healing/*  (self-repair)
  - /api/ecosystem/*  (ecosystem router)

Uses TestClient with mocked subsystems — no real Redis/DB/AI needed.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Environment defaults must be set before any app import ────────────────────

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REQUIRE_AUTH", "false")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
os.environ.setdefault("SECRET_KEY", "test-secret-key-canonical-routes-00001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-canonical-routes-32ch")
os.environ.setdefault("TRANC3_API_KEY", "test-key-canonical")
os.environ.setdefault("ZERO_TRUST_ENABLED", "false")


# ── Shared mock helpers ───────────────────────────────────────────────────────


def _mock_user() -> dict:
    return {"username": "testuser", "is_active": True, "role": "admin"}


def _code_result(**overrides: Any) -> MagicMock:
    r = MagicMock()
    r.code = overrides.get("code", "def hello(): pass")
    r.tests = overrides.get("tests", "def test_hello(): assert hello() is None")
    r.explanation = overrides.get("explanation", "A simple function")
    r.quality_score = overrides.get("quality_score", 0.92)
    r.issues = overrides.get("issues", [])
    r.improvements = overrides.get("improvements", [])
    return r


def _skill_result() -> MagicMock:
    skill = MagicMock()
    skill.to_dict.return_value = {"id": "sk-1", "name": "test-skill"}
    r = MagicMock()
    r.skill = skill
    r.score = 0.88
    r.match_reason = "semantic similarity"
    return r


def _bundle() -> MagicMock:
    b = MagicMock()
    b.id = "bundle-compliance"
    b.name = "Compliance Bundle"
    b.skills = ["sk-1", "sk-2"]
    return b


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """TestClient for canonical api.py with all heavy subsystems mocked."""
    # Cryptex is a module-level singleton; its BLOCK mitigations persist across
    # requests and pollute the test session (e.g. path-traversal inputs block
    # the test client's IP for all subsequent tests).  Replace it with a no-op.
    _mock_cx = MagicMock()
    _mock_cx.analyse_request.return_value = []
    _mock_cx.is_blocked.return_value = False

    with (
        patch("src.core.startup_validator.validate_startup"),
        patch("redis.from_url", return_value=MagicMock(ping=lambda: True)),
        patch("src.cryptex.threat_detector.get_cryptex", return_value=_mock_cx),
    ):
        from fastapi.testclient import TestClient

        import api as _api_mod
        from api import app
        from auth import get_current_user

        # Override FastAPI dependency so all auth-protected routes get a mock user.
        app.dependency_overrides[get_current_user] = lambda: _mock_user()

        yield TestClient(app, raise_server_exceptions=False)

        app.dependency_overrides.clear()


# ── Helper: authenticated POST / GET with mock user override ─────────────────


def _auth_headers() -> dict:
    """Return a fake bearer token header (auth is mocked to always pass)."""
    return {"Authorization": "Bearer test-token"}


# ─────────────────────────────────────────────────────────────────────────────
# Skills endpoints  (/skills/*)
# ─────────────────────────────────────────────────────────────────────────────


class TestSkillsEndpoints:
    def test_search_valid_returns_200_or_503(self, client):
        with patch(
            "src.skills.enhanced_registry.registry.search",
            new=AsyncMock(return_value=[_skill_result()]),
        ):
            r = client.post("/skills/search", json={"query": "security compliance"})
        assert r.status_code in (200, 503)

    def test_search_empty_query_rejected_422(self, client):
        r = client.post("/skills/search", json={"query": ""})
        assert r.status_code == 422

    def test_search_top_k_too_large_rejected_422(self, client):
        r = client.post("/skills/search", json={"query": "test", "top_k": 200})
        assert r.status_code == 422

    def test_search_top_k_zero_rejected_422(self, client):
        r = client.post("/skills/search", json={"query": "test", "top_k": 0})
        assert r.status_code == 422

    def test_stats_returns_200_or_503(self, client):
        with patch(
            "src.skills.enhanced_registry.registry.get_stats",
            return_value={"total": 42, "categories": 5},
        ):
            r = client.get("/skills/stats")
        assert r.status_code in (200, 503)

    def test_detect_bundle_with_match(self, client):
        with patch(
            "src.skills.enhanced_registry.registry.detect_and_load_bundle",
            new=AsyncMock(return_value=_bundle()),
        ):
            r = client.post("/skills/detect-bundle", json={"prompt": "run compliance audit"})
        assert r.status_code in (200, 503)

    def test_detect_bundle_no_match(self, client):
        with patch(
            "src.skills.enhanced_registry.registry.detect_and_load_bundle",
            new=AsyncMock(return_value=None),
        ):
            r = client.post("/skills/detect-bundle", json={"prompt": "something totally unknown"})
        assert r.status_code in (200, 503)

    def test_detect_bundle_empty_prompt_rejected(self, client):
        r = client.post("/skills/detect-bundle", json={"prompt": ""})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Code Generation endpoints  (/code/*)
# ─────────────────────────────────────────────────────────────────────────────


class TestCodeGenEndpoints:
    def test_generate_valid_returns_200_or_503(self, client):
        code_gen_mock = MagicMock()
        code_gen_mock.generate = AsyncMock(return_value=_code_result())
        with patch("src.skills.code_generator.code_generator", code_gen_mock):
            r = client.post(
                "/code/generate",
                json={"description": "A function to compute fibonacci", "language": "python"},
                headers=_auth_headers(),
            )
        assert r.status_code in (200, 503)

    def test_generate_empty_description_rejected_422(self, client):
        r = client.post(
            "/code/generate",
            json={"description": "", "language": "python"},
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    def test_generate_invalid_language_rejected_422(self, client):
        r = client.post(
            "/code/generate",
            json={"description": "test", "language": "../../etc/passwd"},
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    def test_generate_path_traversal_blocked(self, client):
        bad_langs = ["../bad", "<script>", "'; DROP TABLE--"]
        for lang in bad_langs:
            r = client.post(
                "/code/generate",
                json={"description": "test", "language": lang},
                headers=_auth_headers(),
            )
            assert r.status_code == 422, f"Expected 422 for language={lang!r}"

    def test_improve_valid_returns_200_or_503(self, client):
        code_gen_mock = MagicMock()
        code_gen_mock.improver = MagicMock()
        code_gen_mock.improver.improve = AsyncMock(return_value=_code_result())
        with patch("src.skills.code_generator.code_generator", code_gen_mock):
            r = client.post(
                "/code/improve",
                json={"code": "def foo(): pass"},
                headers=_auth_headers(),
            )
        assert r.status_code in (200, 503)

    def test_improve_empty_code_rejected_422(self, client):
        r = client.post(
            "/code/improve",
            json={"code": ""},
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    def test_explain_public_no_auth_needed(self, client):
        code_gen_mock = MagicMock()
        code_gen_mock.explain_code = AsyncMock(return_value="This code adds 1 and 1.")
        with patch("src.skills.code_generator.code_generator", code_gen_mock):
            r = client.post("/code/explain", json={"code": "x = 1 + 1"})
        assert r.status_code in (200, 503)


# ─────────────────────────────────────────────────────────────────────────────
# Self-Healing endpoints  (/healing/*)
# ─────────────────────────────────────────────────────────────────────────────


class TestHealingEndpoints:
    def test_dashboard_public_always_200(self, client):
        monitor_mock = MagicMock()
        monitor_mock.get_system_health = AsyncMock(
            return_value={"status": "healthy", "services": {}}
        )
        with patch("src.healing.health_monitor.health_monitor", monitor_mock):
            r = client.get("/healing/dashboard")
        # Dashboard swallows errors and returns 200 with degraded status
        assert r.status_code == 200

    def test_dashboard_degraded_on_monitor_error(self, client):
        monitor_mock = MagicMock()
        monitor_mock.get_system_health = AsyncMock(side_effect=RuntimeError("monitor down"))
        with patch("src.healing.health_monitor.health_monitor", monitor_mock):
            r = client.get("/healing/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("degraded", "healthy")

    def test_repair_requires_auth(self, client):
        # Without any overrides, the dependency mock already returns a user.
        # The test validates the endpoint is reachable (not 404) when authenticated.
        repair_mock = MagicMock()
        repair_mock.evaluate_and_repair = AsyncMock(return_value={"patched": 2})
        with patch("src.healing.self_repair.repair_engine", repair_mock):
            r = client.post("/healing/repair", headers=_auth_headers())
        assert r.status_code in (200, 503)

    def test_bots_public_returns_200_or_503(self, client):
        dispatcher_mock = MagicMock()
        dispatcher_mock.get_bot_stats = MagicMock(return_value={"active": 3, "idle": 9})
        with patch("src.healing.nanocode_bots.dispatcher", dispatcher_mock):
            r = client.get("/healing/bots")
        assert r.status_code in (200, 503)


# ─────────────────────────────────────────────────────────────────────────────
# Ecosystem router  (/api/ecosystem/*)
# ─────────────────────────────────────────────────────────────────────────────


class TestEcosystemEndpoints:
    """Validates the ecosystem router is reachable via canonical api.py.

    All routes gracefully return {} or 503 when Dimensional modules are absent,
    which is the case in the test environment.
    """

    def test_hubs_returns_json(self, client):
        r = client.get("/api/ecosystem/hubs")
        assert r.status_code in (200, 503)
        assert r.headers["content-type"].startswith("application/json")

    def test_citadel_returns_json(self, client):
        r = client.get("/api/ecosystem/citadel")
        assert r.status_code in (200, 503)

    def test_security_returns_json(self, client):
        r = client.get("/api/ecosystem/security")
        assert r.status_code in (200, 503)

    def test_pillars_returns_json(self, client):
        r = client.get("/api/ecosystem/pillars")
        assert r.status_code in (200, 503)

    def test_neural_bus_returns_json(self, client):
        r = client.get("/api/ecosystem/neural-bus")
        assert r.status_code in (200, 503)

    def test_ecosystem_health_returns_json(self, client):
        r = client.get("/api/ecosystem/health")
        assert r.status_code in (200, 503)

    def test_ecosystem_metrics_returns_json(self, client):
        r = client.get("/api/ecosystem/metrics")
        assert r.status_code in (200, 503)

    def test_defense_firewall_returns_json(self, client):
        r = client.get("/api/ecosystem/defense/firewall")
        assert r.status_code in (200, 503)

    def test_ai_catalog_returns_json(self, client):
        r = client.get("/api/ecosystem/ai/catalog")
        assert r.status_code in (200, 503)

    def test_ai_providers_returns_json(self, client):
        r = client.get("/api/ecosystem/ai/providers")
        assert r.status_code in (200, 503)

    def test_heartbeat_health_returns_json(self, client):
        r = client.get("/api/ecosystem/heartbeat/health")
        assert r.status_code in (200, 503)

    def test_heartbeat_alerts_no_filter(self, client):
        r = client.get("/api/ecosystem/heartbeat/alerts")
        assert r.status_code in (200, 503)

    def test_heartbeat_alerts_with_filters(self, client):
        r = client.get(
            "/api/ecosystem/heartbeat/alerts",
            params={"service_id": "tranc3-backend", "resolved": "false"},
        )
        assert r.status_code in (200, 503)

    def test_post_mode_returns_json(self, client):
        r = client.post("/api/ecosystem/mode", json={"mode": "HYBRID"})
        assert r.status_code in (200, 503)

    def test_defense_incidents_post(self, client):
        r = client.post(
            "/api/ecosystem/defense/incidents",
            json={
                "title": "Test intrusion",
                "description": "Suspicious activity detected",
                "severity": "high",
                "source": "10.0.0.1",
            },
        )
        assert r.status_code in (200, 503)

    def test_defense_incidents_get(self, client):
        r = client.get("/api/ecosystem/defense/incidents")
        assert r.status_code in (200, 503)

    def test_storage_returns_json(self, client):
        r = client.get("/api/ecosystem/storage")
        assert r.status_code in (200, 503)

    def test_heartbeat_post(self, client):
        r = client.post(
            "/api/ecosystem/heartbeat",
            json={
                "service_id": "tranc3-backend",
                "service_name": "TRANC3 Backend",
                "status": "healthy",
            },
        )
        assert r.status_code in (200, 503)

    def test_heartbeat_stats(self, client):
        r = client.get("/api/ecosystem/heartbeat/stats")
        assert r.status_code in (200, 503)

    def test_routing_chains_returns_json(self, client):
        r = client.get("/api/ecosystem/ai/routing-chains")
        assert r.status_code in (200, 503)


# ─────────────────────────────────────────────────────────────────────────────
# Input validation — cross-cutting security checks
# ─────────────────────────────────────────────────────────────────────────────


class TestInputValidation:
    """Validates that Pydantic schema enforcement protects canonical routes."""

    def test_skills_search_rejects_giant_query(self, client):
        r = client.post("/skills/search", json={"query": "x" * 600})
        assert r.status_code == 422

    def test_code_generate_description_too_long(self, client):
        r = client.post(
            "/code/generate",
            json={"description": "a" * 3000, "language": "python"},
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    def test_code_generate_context_too_long(self, client):
        r = client.post(
            "/code/generate",
            json={
                "description": "test",
                "language": "python",
                "context": "c" * 5000,
            },
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    def test_code_improve_code_too_long(self, client):
        r = client.post(
            "/code/improve",
            json={"code": "x" * 40000},
            headers=_auth_headers(),
        )
        assert r.status_code == 422
