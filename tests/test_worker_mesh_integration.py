"""
Worker-to-Worker Communication via ServiceMesh
===============================================
Integration tests for inter-worker communication using ServiceMesh.

Tests:
1. ServiceMesh registration and discovery
2. In-process handler calls (bypassing HTTP)
3. Circuit breaker behavior with worker failures
4. Health checks across workers
5. Retry behavior with transient failures
6. Multi-worker communication patterns
"""

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

from src.mesh import (
    CircuitBreakerConfig,
    CircuitState,
    HealthStatus,
    ServiceCategory,
    ServiceDescriptor,
    ServiceMesh,
    ServiceMeshConfig,
)

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


def _import_worker(module_dotted: str, file_path: Path):
    """Import a worker module with hyphenated path using importlib."""
    spec = importlib.util.spec_from_file_location(module_dotted, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_dotted] = mod
    spec.loader.exec_module(mod)
    return mod


# ───────────────────────────────────────────────────────────────────────────────
# ServiceMesh Registration Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestServiceMeshWorkerRegistration:
    """Test registering workers in the service mesh."""

    def test_register_single_worker(self):
        """Register a single worker in the mesh."""
        mesh = ServiceMesh()
        desc = ServiceDescriptor(
            name="infinity-auth",
            url="http://localhost",
            port=8002,
            category=ServiceCategory.AUTH,
            health_endpoint="/health",
        )
        mesh.register(desc)
        assert mesh.get_service("infinity-auth") is not None
        assert mesh.get_service("infinity-auth").name == "infinity-auth"
        assert mesh.get_service("infinity-auth").port == 8002

    def test_register_multiple_workers(self):
        """Register multiple workers in the mesh."""
        mesh = ServiceMesh()
        workers = [
            ("infinity-auth", 8002, ServiceCategory.AUTH),
            ("users-service", 8003, ServiceCategory.CORE),
            ("monitoring", 8004, ServiceCategory.OBSERVABILITY),
            ("infinity-ai", 8009, ServiceCategory.AI),
        ]
        for name, port, category in workers:
            mesh.register(ServiceDescriptor(
                name=name,
                url="http://localhost",
                port=port,
                category=category,
            ))
        assert len(mesh.get_services()) == 4
        for name, port, category in workers:
            service = mesh.get_service(name)
            assert service.port == port
            assert service.category == category

    def test_unregister_worker(self):
        """Unregister a worker from the mesh."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="test-worker", url="http://localhost", port=8000))
        assert mesh.unregister("test-worker") is True
        assert mesh.get_service("test-worker") is None

    def test_register_creates_circuit_breaker(self):
        """Verify circuit breaker is created for each registered worker."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="test-worker", url="http://localhost", port=8000))
        cb = mesh.get_circuit_breaker("test-worker")
        assert cb is not None
        assert cb.state == CircuitState.CLOSED

    def test_register_with_custom_circuit_breaker_config(self):
        """Register worker with custom circuit breaker configuration."""
        custom_config = CircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout_ms=60000,
            half_open_request_percentage=20.0,
        )
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(
            name="test-worker",
            url="http://localhost",
            port=8000,
            circuit_breaker_config=custom_config,
        ))
        cb = mesh.get_circuit_breaker("test-worker")
        assert cb.config.failure_threshold == 10
        assert cb.config.reset_timeout_ms == 60000
        assert cb.config.half_open_request_percentage == 20.0


# ───────────────────────────────────────────────────────────────────────────────
# In-Process Handler Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestServiceMeshInProcessHandlers:
    """Test in-process call handlers (bypassing HTTP)."""

    @pytest.mark.asyncio
    async def test_call_with_handler(self):
        """Call a worker via registered handler."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-worker", url="http://localhost", port=8002))

        async def mock_auth_handler(path, payload):
            return {"authenticated": True, "user_id": "user-123", "path": path}

        mesh.register_handler("auth-worker", mock_auth_handler)
        result = await mesh.call("auth-worker", "/verify", {"token": "test-token"})
        assert result.success is True
        assert result.data["authenticated"] is True
        assert result.data["user_id"] == "user-123"
        assert result.data["path"] == "/verify"
        return None

    @pytest.mark.asyncio
    async def test_call_handler_failure(self):
        """Test handler failure is recorded correctly."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="failing-worker", url="http://localhost", port=8000))

        async def failing_handler(path, payload):
            raise ValueError("authentication failed")

        mesh.register_handler("failing-worker", failing_handler)
        result = await mesh.call("failing-worker", "/test", {})
        assert result.success is False
        assert "authentication failed" in result.error

    @pytest.mark.asyncio
    async def test_call_unregistered_worker(self):
        """Test calling unregistered worker returns error."""
        mesh = ServiceMesh()
        result = await mesh.call("nonexistent", "/test", {})
        assert result.success is False
        assert "not registered" in result.error

    @pytest.mark.asyncio
    async def test_call_records_success_on_circuit_breaker(self):
        """Verify successful calls record success on circuit breaker."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="test-worker", url="http://localhost", port=8000))

        async def success_handler(path, payload):
            return {"ok": True}

        mesh.register_handler("test-worker", success_handler)
        await mesh.call("test-worker", "/test", {})
        cb = mesh.get_circuit_breaker("test-worker")
        assert cb.get_state().success_count == 1
        return None

    @pytest.mark.asyncio
    async def test_call_records_failure_on_circuit_breaker(self):
        """Verify failed calls record failure on circuit breaker."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="test-worker", url="http://localhost", port=8000))

        async def failing_handler(path, payload):
            raise RuntimeError("boom")

        mesh.register_handler("test-worker", failing_handler)
        await mesh.call("test-worker", "/test", {})
        cb = mesh.get_circuit_breaker("test-worker")
        assert cb.get_state().failure_count == 1


# ───────────────────────────────────────────────────────────────────────────────
# Circuit Breaker Integration Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestCircuitBreakerWorkerIntegration:
    """Test circuit breaker behavior with worker calls."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Circuit breaker opens after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="flaky-worker", url="http://localhost", port=9999))

        async def failing_handler(path, payload):
            raise ConnectionError("service down")

        mesh.register_handler("flaky-worker", failing_handler)

        # Trigger failures
        await mesh.call("flaky-worker", "/test", {})
        await mesh.call("flaky-worker", "/test", {})
        await mesh.call("flaky-worker", "/test", {})

        cb = mesh.get_circuit_breaker("flaky-worker")
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_calls_when_open(self):
        """Circuit breaker blocks calls when open."""
        config = CircuitBreakerConfig(failure_threshold=2)
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="flaky-worker", url="http://localhost", port=9999))

        async def failing_handler(path, payload):
            raise ConnectionError("service down")

        mesh.register_handler("flaky-worker", failing_handler)

        # Trigger failures to open circuit
        await mesh.call("flaky-worker", "/test", {})
        await mesh.call("flaky-worker", "/test", {})

        # Next call should be blocked
        result = await mesh.call("flaky-worker", "/test", {})
        assert result.success is False
        assert "Circuit breaker OPEN" in result.error
        assert result.circuit_state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_allows_call_when_closed(self):
        """Circuit breaker allows calls when closed."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="healthy-worker", url="http://localhost", port=8000))

        async def success_handler(path, payload):
            return {"ok": True}

        mesh.register_handler("healthy-worker", success_handler)
        result = await mesh.call("healthy-worker", "/test", {})
        assert result.success is True
        assert result.circuit_state == CircuitState.CLOSED
        return None

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_after_successes(self):
        """Circuit breaker closes after enough successes in half-open."""
        import time

        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,
            half_open_success_threshold=2,
        )
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="flaky-worker", url="http://localhost", port=9999))

        # Start with failing handler
        async def failing_handler(path, payload):
            raise ConnectionError("service down")

        mesh.register_handler("flaky-worker", failing_handler)

        # Open the circuit
        await mesh.call("flaky-worker", "/test", {})
        assert mesh.get_circuit_breaker("flaky-worker").state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.1)

        # Switch to success handler
        async def success_handler(path, payload):
            return {"ok": True}

        mesh.register_handler("flaky-worker", success_handler)

        # Two successes should close the circuit
        await mesh.call("flaky-worker", "/test", {})
        await mesh.call("flaky-worker", "/test", {})
        assert mesh.get_circuit_breaker("flaky-worker").state == CircuitState.CLOSED
        return None


# ───────────────────────────────────────────────────────────────────────────────
# Health Check Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestServiceMeshHealthChecks:
    """Test health check functionality across workers."""

    @pytest.mark.asyncio
    async def test_health_check_single_worker(self):
        """Check health of a single worker using in-process handler."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(
            name="test-worker",
            url="http://localhost",
            port=8000,
            health_endpoint="/health",
        ))

        # Register a handler that simulates health check
        async def health_handler(path, payload):
            return {"status": "healthy", "service": "test-worker"}

        mesh.register_handler("test-worker", health_handler)

        # Call the health endpoint via handler
        result = await mesh.call("test-worker", "/health")
        assert result.success is True
        assert result.data["status"] == "healthy"
        return None

    @pytest.mark.asyncio
    async def test_health_check_cached(self):
        """Test cached health status after registration."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(
            name="test-worker",
            url="http://localhost",
            port=8000,
            health_endpoint="/health",
        ))

        # Initial health should be UNKNOWN
        health = mesh.get_health("test-worker")
        assert health is not None
        assert health.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        """Check health when worker is unreachable via HTTP."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(
            name="unreachable-worker",
            url="http://localhost",
            port=19999,
            health_endpoint="/health",
        ))

        # This will actually try to connect and fail (no server on 19999)
        # Use a very short timeout
        from unittest.mock import AsyncMock, patch
        with patch.object(mesh, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.side_effect = ConnectionError("connection refused")
            mock_get_client.return_value = mock_client

            health = await mesh.health_check("unreachable-worker")
            assert health.status == HealthStatus.UNHEALTHY
            assert "connection refused" in health.error

    @pytest.mark.asyncio
    async def test_health_check_all_workers_via_handlers(self):
        """Check health of all registered workers via in-process handlers."""
        mesh = ServiceMesh()
        for i in range(3):
            mesh.register(ServiceDescriptor(
                name=f"worker-{i}",
                url="http://localhost",
                port=8000 + i,
                health_endpoint="/health",
            ))

            async def health_handler(path, payload, wid=i):
                return {"status": "healthy", "worker_id": wid}

            mesh.register_handler(f"worker-{i}", health_handler)

        # Call each worker's health endpoint
        for i in range(3):
            result = await mesh.call(f"worker-{i}", "/health")
            assert result.success is True
            assert result.data["status"] == "healthy"
            assert result.data["worker_id"] == i
        return None


# ───────────────────────────────────────────────────────────────────────────────
# Retry Behavior Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestServiceMeshRetryBehavior:
    """Test retry behavior with transient failures.

    Note: In-process handlers (_call_handler) don't implement retries —
    retries are only in the HTTP call path (_call_http). Handler failures
    are recorded on the circuit breaker immediately. These tests verify
    the circuit breaker behavior with repeated handler failures.
    """

    @pytest.mark.asyncio
    async def test_handler_failure_triggers_circuit_breaker(self):
        """Test that repeated handler failures trigger circuit breaker opening."""
        config = CircuitBreakerConfig(failure_threshold=3)
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="flaky-worker", url="http://localhost", port=8000))

        call_count = 0

        async def flaky_handler(path, payload):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise ConnectionError("temporary failure")
            return {"ok": True}

        mesh.register_handler("flaky-worker", flaky_handler)

        # First 3 calls fail
        result1 = await mesh.call("flaky-worker", "/test", {})
        assert result1.success is False
        result2 = await mesh.call("flaky-worker", "/test", {})
        assert result2.success is False
        result3 = await mesh.call("flaky-worker", "/test", {})
        assert result3.success is False

        # Circuit should be open now
        cb = mesh.get_circuit_breaker("flaky-worker")
        assert cb.state == CircuitState.OPEN
        return None

    @pytest.mark.asyncio
    async def test_handler_succeeds_after_initial_failures(self):
        """Test that a handler can succeed after initial failures if circuit stays closed."""
        config = CircuitBreakerConfig(failure_threshold=5)
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="flaky-worker", url="http://localhost", port=8000))

        call_count = 0

        async def recovering_handler(path, payload):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("temporary failure")
            return {"ok": True, "attempt": call_count}

        mesh.register_handler("flaky-worker", recovering_handler)

        # First 2 calls fail (below threshold, circuit stays closed)
        result1 = await mesh.call("flaky-worker", "/test", {})
        assert result1.success is False
        result2 = await mesh.call("flaky-worker", "/test", {})
        assert result2.success is False

        # Circuit should still be closed
        cb = mesh.get_circuit_breaker("flaky-worker")
        assert cb.state == CircuitState.CLOSED

        # Third call succeeds
        result3 = await mesh.call("flaky-worker", "/test", {})
        assert result3.success is True
        assert result3.data["attempt"] == 3
        return None

    @pytest.mark.asyncio
    async def test_circuit_breaker_reset_after_opening(self):
        """Test circuit breaker can be reset after opening."""
        config = CircuitBreakerConfig(failure_threshold=1)
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="failing-worker", url="http://localhost", port=8000))

        async def always_failing(path, payload):
            raise ConnectionError("always fails")

        mesh.register_handler("failing-worker", always_failing)

        # Trigger circuit open
        await mesh.call("failing-worker", "/test", {})
        cb = mesh.get_circuit_breaker("failing-worker")
        assert cb.state == CircuitState.OPEN

        # Reset circuit breaker
        cb.reset()
        assert cb.state == CircuitState.CLOSED

        # Next call should go through (but still fail)
        result = await mesh.call("failing-worker", "/test", {})
        assert result.success is False
        assert "always fails" in result.error


# ───────────────────────────────────────────────────────────────────────────────
# Multi-Worker Communication Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestMultiWorkerCommunication:
    """Test communication patterns between multiple workers."""

    @pytest.mark.asyncio
    async def test_auth_to_users_communication(self):
        """Test auth worker calling users worker."""
        mesh = ServiceMesh()

        # Register auth worker
        mesh.register(ServiceDescriptor(
            name="infinity-auth",
            url="http://localhost",
            port=8002,
            category=ServiceCategory.AUTH,
        ))

        # Register users worker
        mesh.register(ServiceDescriptor(
            name="users-service",
            url="http://localhost",
            port=8003,
            category=ServiceCategory.CORE,
        ))

        # Mock users worker handler
        async def users_handler(path, payload):
            if path == "/users/get":
                return {"user_id": payload.get("user_id"), "email": "test@example.com"}
            return {}

        mesh.register_handler("users-service", users_handler)

        # Auth worker calls users worker
        result = await mesh.call("users-service", "/users/get", {"user_id": "user-123"})
        assert result.success is True
        assert result.data["user_id"] == "user-123"
        assert result.data["email"] == "test@example.com"
        return None

    @pytest.mark.asyncio
    async def test_cascading_worker_calls(self):
        """Test cascading calls through multiple workers."""
        mesh = ServiceMesh()

        # Register three workers
        for name, port in [("worker-a", 8001), ("worker-b", 8002), ("worker-c", 8003)]:
            mesh.register(ServiceDescriptor(name=name, url="http://localhost", port=port))

        # Worker A calls Worker B, which calls Worker C
        async def worker_c_handler(path, payload):
            return {"result": "C", "data": payload}

        async def worker_b_handler(path, payload):
            # Worker B calls Worker C
            result = await mesh.call("worker-c", "/process", {"from": "B", "original": payload})
            return {"result": "B", "upstream": result.data}

        async def worker_a_handler(path, payload):
            # Worker A calls Worker B
            result = await mesh.call("worker-b", "/process", {"from": "A", "original": payload})
            return {"result": "A", "upstream": result.data}

        mesh.register_handler("worker-c", worker_c_handler)
        mesh.register_handler("worker-b", worker_b_handler)
        mesh.register_handler("worker-a", worker_a_handler)

        # Start the cascade
        result = await mesh.call("worker-a", "/process", {"input": "test"})
        assert result.success is True
        assert result.data["result"] == "A"
        assert result.data["upstream"]["result"] == "B"
        assert result.data["upstream"]["upstream"]["result"] == "C"
        return None

    @pytest.mark.asyncio
    async def test_parallel_worker_calls(self):
        """Test parallel calls to multiple workers."""
        mesh = ServiceMesh()

        for i in range(3):
            mesh.register(ServiceDescriptor(
                name=f"worker-{i}",
                url="http://localhost",
                port=8000 + i,
            ))

        async def worker_handler(path, payload):
            import asyncio
            await asyncio.sleep(0.1)  # Simulate work
            return {"worker": payload.get("worker_id")}

        for i in range(3):
            mesh.register_handler(f"worker-{i}", worker_handler)

        # Call all workers in parallel
        tasks = [
            mesh.call(f"worker-{i}", "/process", {"worker_id": i})
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)

        assert all(r.success for r in results)
        assert [r.data["worker"] for r in results] == [0, 1, 2]
        return None

    @pytest.mark.asyncio
    async def test_dependency_graph(self):
        """Test building dependency graph from worker registrations."""
        mesh = ServiceMesh()

        # Register workers with dependencies
        mesh.register(ServiceDescriptor(
            name="api-gateway",
            url="http://localhost",
            port=8000,
            dependencies=["infinity-auth", "users-service"],
        ))
        mesh.register(ServiceDescriptor(
            name="infinity-auth",
            url="http://localhost",
            port=8002,
            dependencies=[],
        ))
        mesh.register(ServiceDescriptor(
            name="users-service",
            url="http://localhost",
            port=8003,
            dependencies=["infinity-auth"],
        ))

        graph = mesh.get_dependency_graph()
        assert graph["api-gateway"] == ["infinity-auth", "users-service"]
        assert graph["infinity-auth"] == []
        assert graph["users-service"] == ["infinity-auth"]


# ───────────────────────────────────────────────────────────────────────────────
# ServiceMesh Cleanup Tests
# ───────────────────────────────────────────────────────────────────────────────

class TestServiceMeshCleanup:
    """Test ServiceMesh resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_cleans_up_resources(self):
        """Test close cleans up HTTP client and health task."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="test", url="http://localhost", port=8000))
        await mesh.close()
        # Should not raise any errors
        await mesh.close()  # Idempotent

    @pytest.mark.asyncio
    async def test_unregister_removes_all_resources(self):
        """Test unregister removes circuit breaker and health cache."""
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="test", url="http://localhost", port=8000))

        # Verify resources exist
        assert mesh.get_service("test") is not None
        assert mesh.get_circuit_breaker("test") is not None
        assert mesh.get_health("test") is not None

        # Unregister
        mesh.unregister("test")

        # Verify resources removed
        assert mesh.get_service("test") is None
        assert mesh.get_circuit_breaker("test") is None
        assert mesh.get_health("test") is None
