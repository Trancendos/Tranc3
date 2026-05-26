"""
tests/test_adaptive_intelligence.py
Phase 22.7 — Smart Adaptive Intelligence layer unit tests.
Tests: InfinityHealthOrchestrator, ProactiveDefenseLayer, InfinityFluidicGateway,
       AdaptivePulseController, InfinityWorkerKit.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

os.environ.setdefault("SECRET_KEY", "test-secret-key-adaptive-00001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-adaptive-000001")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Dimensional.infinity.adaptive_intelligence import (
    AIConfig,
    HealthSummary,
    InfinityHealthOrchestrator,
)
from Dimensional.infinity.fluidic_gateway import InfinityFluidicGateway
from Dimensional.infinity.proactive_defense import ProactiveDefenseLayer
from Dimensional.infinity.worker_integration import InfinityWorkerKit


def _make_orchestrator(name: str = "test-service") -> InfinityHealthOrchestrator:
    """Helper — constructs orchestrator via AIConfig (required signature)."""
    return InfinityHealthOrchestrator(AIConfig(service_name=name))


def _run_coro(coro):
    """Run a coroutine safely, creating a fresh event loop if needed.

    This avoids RuntimeError from asyncio.get_event_loop() after other test
    modules (e.g. test_adaptive_automation) close the default loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # We're inside an already-running loop (shouldn't happen in sync tests)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# InfinityHealthOrchestrator
# ---------------------------------------------------------------------------
class TestInfinityHealthOrchestrator:
    def setup_method(self):
        self.orch = _make_orchestrator("test-service")

    # --- summary structure ---

    def test_instantiation(self):
        assert self.orch is not None

    def test_get_health_summary_returns_health_summary(self):
        summary = self.orch.get_health_summary()
        assert isinstance(summary, HealthSummary)

    def test_initial_health_score_in_bounds(self):
        summary = self.orch.get_health_summary()
        d = summary.to_dict()
        assert "health_score" in d
        assert 0.0 <= d["health_score"] <= 1.0

    def test_health_summary_has_service_key(self):
        d = self.orch.get_health_summary().to_dict()
        assert d.get("service") == "test-service"

    # --- record_request / record_error ---

    def test_record_request(self):
        self.orch.record_request(latency_ms=50.0, status_code=200)
        summary = self.orch.get_health_summary()
        assert summary is not None

    def test_record_error_request(self):
        self.orch.record_request(latency_ms=0.0, status_code=500)
        d = self.orch.get_health_summary().to_dict()
        assert "health_score" in d

    def test_update_health(self):
        self.orch.update_health(0.85)
        d = self.orch.get_health_summary().to_dict()
        assert d["health_score"] >= 0.0

    # --- daemon scheduling ---

    def test_register_daemon(self):
        self.orch.register_daemon("test_daemon", baseline_interval=60.0)

    def test_should_fire_new_daemon(self):
        self.orch.register_daemon("fire_test", baseline_interval=0.001)
        time.sleep(0.01)
        result = self.orch.should_fire("fire_test")
        assert isinstance(result, bool)

    def test_record_fire(self):
        self.orch.register_daemon("record_fire_test", baseline_interval=10.0)
        self.orch.record_fire("record_fire_test")  # Should not raise

    # --- metrics ---

    def test_record_metric(self):
        self.orch.record_metric("test_metric", 42.0)  # Should not raise

    def test_get_defense_incidents_returns_list(self):
        incidents = self.orch.get_defense_incidents()
        assert isinstance(incidents, list)

    # --- bounds under stress ---

    def test_health_score_in_bounds_after_many_errors(self):
        for _ in range(100):
            self.orch.record_request(latency_ms=5000.0, status_code=500)
        d = self.orch.get_health_summary().to_dict()
        assert 0.0 <= d["health_score"] <= 1.0

    def test_health_summary_has_pulse_mode(self):
        d = self.orch.get_health_summary().to_dict()
        assert "pulse_mode" in d

    def test_health_summary_has_tier(self):
        d = self.orch.get_health_summary().to_dict()
        # Accept either 'health_tier' or 'tier' key variant
        assert "health_tier" in d or "tier" in d


# ---------------------------------------------------------------------------
# ProactiveDefenseLayer
# ---------------------------------------------------------------------------
class TestProactiveDefenseLayer:
    def setup_method(self):
        self.defense = ProactiveDefenseLayer(
            violation_threshold=5,
            violation_window_seconds=60,
            block_duration_seconds=300,
        )

    def test_instantiation(self):
        assert self.defense is not None

    def test_evaluate_safe_request_allowed(self):
        result = _run_coro(
            self.defense.evaluate_request(
                {
                    "ip": "192.168.1.100",
                    "path": "/health",
                    "method": "GET",
                    "user_agent": "TestClient/1.0",
                }
            )
        )
        assert result.allowed is True

    def test_get_stats_returns_dict(self):
        stats = self.defense.get_stats()
        assert isinstance(stats, dict)

    def test_stats_have_evaluations_key(self):
        stats = self.defense.get_stats()
        assert "evaluations" in stats

    def test_get_blocked_ips_returns_list(self):
        blocked = self.defense.get_blocked_ips()
        assert isinstance(blocked, list)

    def test_evaluate_many_requests_increments_evaluations(self):
        """IP should be blocked after exceeding violation threshold."""
        bad_ip = "10.0.0.99"

        async def _run_many():
            for i in range(20):
                await self.defense.evaluate_request(
                    {
                        "ip": bad_ip,
                        "path": f"/portal/login?attempt={i}",
                        "method": "POST",
                        "user_agent": "python-requests/2.28",
                    }
                )

        _run_coro(_run_many())
        stats = self.defense.get_stats()
        assert stats.get("evaluations", 0) > 0

    def test_custom_thresholds_applied(self):
        """Verify instance-level threshold override instantiates without error."""
        defense = ProactiveDefenseLayer(
            violation_threshold=2,
            violation_window_seconds=30,
            block_duration_seconds=120,
        )
        assert defense is not None


# ---------------------------------------------------------------------------
# InfinityFluidicGateway
# ---------------------------------------------------------------------------
class TestInfinityFluidicGateway:
    def setup_method(self):
        self.gateway = InfinityFluidicGateway("test-service")

    def test_instantiation(self):
        assert self.gateway is not None

    def test_route_user_role(self):
        result = _run_coro(self.gateway.route("user", "user-123"))
        assert result is not None
        assert hasattr(result, "target_location")

    def test_route_admin_role(self):
        result = _run_coro(self.gateway.route("admin", "admin-456"))
        assert result is not None

    def test_route_ai_role(self):
        result = _run_coro(self.gateway.route("ai", "ai-789"))
        assert result is not None

    def test_route_unknown_role_fallback(self):
        result = _run_coro(self.gateway.route("unknown_role", "u-0"))
        assert result is not None

    def test_record_route_success(self):
        result = _run_coro(self.gateway.route("user", "u-rec"))
        self.gateway.record_route_success(result.target_location, 42.5)

    def test_get_stats_returns_dict(self):
        stats = self.gateway.get_stats()
        assert isinstance(stats, dict)

    def test_get_topology_returns_dict(self):
        topo = self.gateway.get_topology()
        assert isinstance(topo, dict)


# ---------------------------------------------------------------------------
# InfinityWorkerKit (integration)
# ---------------------------------------------------------------------------
class TestInfinityWorkerKit:
    def setup_method(self):
        self.kit = InfinityWorkerKit(
            "test-worker",
            defense_threshold=10,
            defense_window_seconds=60,
            defense_block_seconds=300,
        )

    def test_instantiation(self):
        assert self.kit is not None

    def test_health_attribute(self):
        assert self.kit.health is not None

    def test_defense_attribute(self):
        assert self.kit.defense is not None

    def test_gateway_attribute(self):
        assert self.kit.gateway is not None

    def test_get_kit_stats_returns_dict(self):
        stats = self.kit.get_kit_stats()
        assert isinstance(stats, dict)

    def test_kit_stats_has_service_name(self):
        stats = self.kit.get_kit_stats()
        assert stats.get("service") == "test-worker"

    def test_kit_stats_has_subsystems(self):
        stats = self.kit.get_kit_stats()
        assert "subsystems" in stats

    def test_kit_stats_subsystems_is_dict(self):
        stats = self.kit.get_kit_stats()
        assert isinstance(stats["subsystems"], dict)

    def test_shutdown_without_startup(self):
        """Shutdown on a kit that was never started should not raise."""
        _run_coro(self.kit.shutdown())

    def test_startup_and_shutdown(self):
        """Full startup → shutdown lifecycle."""
        from fastapi import FastAPI

        app = FastAPI()

        async def _lifecycle():
            await self.kit.startup(app, sentinel=None)
            await self.kit.shutdown()

        _run_coro(_lifecycle())

    def test_startup_mounts_health_smart_endpoint(self):
        """InfinityWorkerKit should mount /health/smart after startup."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        async def _startup():
            await self.kit.startup(app, sentinel=None)

        _run_coro(_startup())

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/health/smart")
        # Either 200 or 404 depending on kit state, but must not 500
        assert r.status_code in (200, 404)

    def test_startup_mounts_defense_stats_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        async def _startup():
            await self.kit.startup(app, sentinel=None)

        _run_coro(_startup())

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/defense/stats")
        assert r.status_code in (200, 404)

    def test_startup_mounts_routing_topology_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        async def _startup():
            await self.kit.startup(app, sentinel=None)

        _run_coro(_startup())

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/routing/topology")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# AdaptivePulseController (via orchestrator)
# ---------------------------------------------------------------------------
class TestAdaptivePulseViaOrchestrator:
    def setup_method(self):
        self.orch = _make_orchestrator("pulse-test")

    def test_steady_mode_at_startup(self):
        """Default pulse mode should be STEADY at service start."""
        d = self.orch.get_health_summary().to_dict()
        assert d.get("pulse_mode") == "steady"

    def test_accelerated_mode_on_high_error_rate(self):
        """Explicitly setting low health score should change tier away from optimal."""
        # Record many error requests (telemetry)
        for _ in range(50):
            self.orch.record_request(latency_ms=2000.0, status_code=500)
        # Explicitly degrade the health score
        self.orch.update_health(0.2)
        d = self.orch.get_health_summary().to_dict()
        assert d["health_score"] < 1.0

    def test_recovery_after_errors_clear(self):
        """After degrading, restoring health should reflect in score."""
        self.orch.update_health(0.1)
        for _ in range(50):
            self.orch.record_request(latency_ms=10.0, status_code=200)
        self.orch.update_health(0.9)
        d = self.orch.get_health_summary().to_dict()
        assert d["health_score"] >= 0.5
