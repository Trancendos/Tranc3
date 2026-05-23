"""
Tests for src/observability/health.py — Health Aggregation & Service Registry
==============================================================================
Covers: HealthChecker, SERVICE_REGISTRY, SystemHealth enum, service health checks.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.observability.health import (
    SERVICE_REGISTRY,
    HealthChecker,
    SystemHealth,
)

# ─────────────────────────────────────────────────────────────────────────────
# SystemHealth Enum Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemHealth:
    """System health status enum."""

    def test_values(self):
        assert SystemHealth.healthy.value == "healthy"
        assert SystemHealth.degraded.value == "degraded"
        assert SystemHealth.unhealthy.value == "unhealthy"
        assert SystemHealth.unknown.value == "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE_REGISTRY Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestServiceRegistry:
    """Default service registry contents."""

    def test_registry_not_empty(self):
        assert len(SERVICE_REGISTRY) > 0

    def test_registry_has_p0_services(self):
        p0 = {name for name, svc in SERVICE_REGISTRY.items() if svc["priority"] == "P0"}
        assert len(p0) > 0

    def test_registry_has_p1_services(self):
        p1 = {name for name, svc in SERVICE_REGISTRY.items() if svc["priority"] == "P1"}
        assert len(p1) > 0

    def test_registry_has_p2_services(self):
        p2 = {name for name, svc in SERVICE_REGISTRY.items() if svc["priority"] == "P2"}
        assert len(p2) > 0

    def test_registry_entries_have_url(self):
        for name, svc in SERVICE_REGISTRY.items():
            assert "url" in svc, f"Service {name} missing 'url'"

    def test_registry_entries_have_priority(self):
        for name, svc in SERVICE_REGISTRY.items():
            assert "priority" in svc, f"Service {name} missing 'priority'"

    def test_registry_entries_have_named(self):
        for name, svc in SERVICE_REGISTRY.items():
            assert "named" in svc, f"Service {name} missing 'named'"

    def test_known_services(self):
        assert "infinity-ws" in SERVICE_REGISTRY
        assert "infinity-auth" in SERVICE_REGISTRY
        assert "infinity-ai" in SERVICE_REGISTRY
        assert "the-grid" in SERVICE_REGISTRY

    def test_p0_services_known(self):
        p0 = {name for name, svc in SERVICE_REGISTRY.items() if svc["priority"] == "P0"}
        assert "infinity-ws" in p0
        assert "infinity-auth" in p0


# ─────────────────────────────────────────────────────────────────────────────
# HealthChecker Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthChecker:
    """HealthChecker with custom registry."""

    def test_init_default_registry(self):
        checker = HealthChecker()
        assert checker.registry == SERVICE_REGISTRY

    def test_init_custom_registry(self):
        custom = {
            "test-svc": {"url": "http://localhost:9999/health", "priority": "P0", "named": "Test"},
        }
        checker = HealthChecker(registry=custom)
        assert "test-svc" in checker.registry
        assert len(checker.registry) == 1

    @pytest.mark.asyncio
    async def test_check_unregistered_service(self):
        checker = HealthChecker(registry={})
        result = await checker.check_service("nonexistent")
        assert result["status"] == "unknown"
        assert "Not registered" in result["error"]

    @pytest.mark.asyncio
    async def test_check_service_connection_refused(self):
        """Service that's not running should be unhealthy."""
        custom = {
            "offline-svc": {"url": "http://localhost:1/health", "priority": "P0", "named": "Offline"},
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_service("offline-svc")
        assert result["status"] == "unhealthy"
        assert result["service"] == "offline-svc"

    @pytest.mark.asyncio
    async def test_check_service_caches_result(self):
        """Health check results are cached."""
        custom = {
            "offline-svc": {"url": "http://localhost:1/health", "priority": "P0", "named": "Offline"},
        }
        checker = HealthChecker(registry=custom)
        await checker.check_service("offline-svc")
        assert "offline-svc" in checker._cache

    @pytest.mark.asyncio
    async def test_get_cached(self):
        """get_cached returns last cached results."""
        custom = {
            "offline-svc": {"url": "http://localhost:1/health", "priority": "P0", "named": "Offline"},
        }
        checker = HealthChecker(registry=custom)
        await checker.check_service("offline-svc")
        cached = checker.get_cached()
        assert "services" in cached
        assert "offline-svc" in cached["services"]
        assert "timestamp" in cached

    def test_get_service_list(self):
        custom = {
            "svc-a": {"url": "http://localhost:8000/health", "priority": "P0", "named": "A"},
            "svc-b": {"url": "http://localhost:8001/health", "priority": "P1", "named": "B"},
        }
        checker = HealthChecker(registry=custom)
        services = checker.get_service_list()
        assert len(services) == 2
        names = {s["name"] for s in services}
        assert "svc-a" in names
        assert "svc-b" in names
        for svc in services:
            assert "url" in svc
            assert "priority" in svc
            assert "named" in svc


# ─────────────────────────────────────────────────────────────────────────────
# HealthChecker with Mock HTTP Server
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCheckerWithServer:
    """HealthChecker against a real HTTP server."""

    @pytest.fixture
    def healthy_server(self):
        """Start a mock HTTP server that returns healthy responses."""
        class HealthyHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    body = json.dumps({"status": "ok", "uptime": 123}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress logs

        server = HTTPServer(("127.0.0.1", 0), HealthyHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        yield port
        server.shutdown()

    @pytest.fixture
    def degraded_server(self):
        """Server that returns 403 (degraded)."""
        class DegradedHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(403)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), DegradedHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        yield port
        server.shutdown()

    @pytest.fixture
    def error_server(self):
        """Server that returns 500 (unhealthy)."""
        class ErrorHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(500)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), ErrorHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        yield port
        server.shutdown()

    @pytest.mark.asyncio
    async def test_check_healthy_service(self, healthy_server):
        port = healthy_server
        custom = {
            "healthy-svc": {
                "url": f"http://127.0.0.1:{port}/health",
                "priority": "P0",
                "named": "Healthy",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_service("healthy-svc")
        assert result["status"] == "healthy"
        assert result["service"] == "healthy-svc"
        assert result["named"] == "Healthy"
        assert result["priority"] == "P0"
        assert "checked_at" in result
        assert "details" in result

    @pytest.mark.asyncio
    async def test_check_degraded_service(self, degraded_server):
        port = degraded_server
        custom = {
            "degraded-svc": {
                "url": f"http://127.0.0.1:{port}/health",
                "priority": "P1",
                "named": "Degraded",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_service("degraded-svc")
        assert result["status"] == "degraded"
        assert "HTTP 403" in result["error"]

    @pytest.mark.asyncio
    async def test_check_unhealthy_service(self, error_server):
        port = error_server
        custom = {
            "error-svc": {
                "url": f"http://127.0.0.1:{port}/health",
                "priority": "P0",
                "named": "Error",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_service("error-svc")
        assert result["status"] == "unhealthy"
        assert "HTTP 500" in result["error"]

    @pytest.mark.asyncio
    async def test_check_all_mixed(self, healthy_server, error_server):
        """check_all with a mix of healthy and unhealthy services."""
        custom = {
            "healthy-svc": {
                "url": f"http://127.0.0.1:{healthy_server}/health",
                "priority": "P0",
                "named": "Healthy",
            },
            "error-svc": {
                "url": f"http://127.0.0.1:{error_server}/health",
                "priority": "P0",
                "named": "Error",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_all()
        assert result["overall"] == SystemHealth.unhealthy.value
        assert result["healthy"] == 1
        assert result["unhealthy"] == 1
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_check_all_healthy(self, healthy_server):
        custom = {
            "svc-1": {
                "url": f"http://127.0.0.1:{healthy_server}/health",
                "priority": "P0",
                "named": "Svc1",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_all()
        assert result["overall"] == SystemHealth.healthy.value
        assert result["healthy"] == 1
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_check_all_degraded(self, degraded_server):
        """All services degraded → overall degraded."""
        custom = {
            "svc-1": {
                "url": f"http://127.0.0.1:{degraded_server}/health",
                "priority": "P1",
                "named": "Svc1",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_all()
        assert result["overall"] == SystemHealth.degraded.value

    @pytest.mark.asyncio
    async def test_p0_unhealthy_makes_overall_unhealthy(self, healthy_server, error_server):
        """Even if P1 is healthy, a P0 unhealthy service makes overall unhealthy."""
        custom = {
            "p0-svc": {
                "url": f"http://127.0.0.1:{error_server}/health",
                "priority": "P0",
                "named": "P0Error",
            },
            "p1-svc": {
                "url": f"http://127.0.0.1:{healthy_server}/health",
                "priority": "P1",
                "named": "P1Healthy",
            },
        }
        checker = HealthChecker(registry=custom)
        result = await checker.check_all()
        assert result["overall"] == SystemHealth.unhealthy.value
