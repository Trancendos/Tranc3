"""
Tests for src/mesh/ — CircuitBreaker + ServiceMesh
====================================================
Validates the core service mesh components ported from infinity-adminOS.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.mesh.circuit_breaker import CircuitBreaker
from src.mesh.service_mesh import ServiceMesh
from src.mesh.types import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitState,
    HealthStatus,
    ServiceCallResult,
    ServiceCategory,
    ServiceDescriptor,
    ServiceMeshConfig,
)

# ──────────────────────────────────────────────────────────────────────
# CircuitBreaker Tests
# ──────────────────────────────────────────────────────────────────────


class TestCircuitBreakerInit:
    """CircuitBreaker initialisation and defaults."""

    def test_default_state_is_closed(self):
        cb = CircuitBreaker("test-service")
        assert cb.state == CircuitState.CLOSED

    def test_custom_config(self):
        config = CircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout_ms=5000,
            half_open_request_percentage=20.0,
            half_open_success_threshold=5,
        )
        cb = CircuitBreaker("test-service", config=config)
        assert cb.config.failure_threshold == 10
        assert cb.config.reset_timeout_ms == 5000
        assert cb.config.half_open_request_percentage == 20.0
        assert cb.config.half_open_success_threshold == 5

    def test_get_state_returns_snapshot(self):
        cb = CircuitBreaker("test-service")
        state = cb.get_state()
        assert isinstance(state, CircuitBreakerState)
        assert state.state == CircuitState.CLOSED
        assert state.failure_count == 0
        assert state.success_count == 0


class TestCircuitBreakerClosedState:
    """CircuitBreaker in CLOSED state — normal operation."""

    def test_can_execute_when_closed(self):
        cb = CircuitBreaker("test-service")
        assert cb.can_execute() is True

    def test_record_success_resets_failure_count(self):
        cb = CircuitBreaker("test-service")
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state().failure_count == 2
        cb.record_success()
        assert cb.get_state().failure_count == 0

    def test_record_success_increments_success_count(self):
        cb = CircuitBreaker("test-service")
        cb.record_success()
        cb.record_success()
        assert cb.get_state().success_count == 2

    def test_record_failure_increments_failure_count(self):
        cb = CircuitBreaker("test-service")
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state().failure_count == 3

    def test_opens_after_failure_threshold(self):
        cb = CircuitBreaker(
            "test-service",
            config=CircuitBreakerConfig(failure_threshold=3),
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerOpenState:
    """CircuitBreaker in OPEN state — failing."""

    def test_cannot_execute_when_open(self):
        cb = CircuitBreaker(
            "test-service",
            config=CircuitBreakerConfig(failure_threshold=1),
        )
        cb.record_failure()  # Opens the circuit
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_opens_sets_timestamp(self):
        cb = CircuitBreaker(
            "test-service",
            config=CircuitBreakerConfig(failure_threshold=1),
        )
        before = datetime.now(timezone.utc)
        cb.record_failure()
        after = datetime.now(timezone.utc)
        state = cb.get_state()
        assert state.opened_at is not None
        assert before <= state.opened_at <= after

    def test_transitions_to_half_open_after_timeout(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,  # Very short timeout for testing
        )
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()  # Opens the circuit
        assert cb.state == CircuitState.OPEN

        # Wait for timeout to elapse
        time.sleep(0.1)
        # Access state via property to trigger auto-transition
        assert cb.state == CircuitState.HALF_OPEN


class TestCircuitBreakerHalfOpenState:
    """CircuitBreaker in HALF_OPEN state — testing recovery."""

    def test_half_open_allows_some_requests(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,  # Allow all for testing
        )
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()  # Opens
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True  # 100% allowed

    def test_half_open_closes_after_enough_successes(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,
            half_open_success_threshold=3,
        )
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()  # Opens
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # Not enough yet
        cb.record_success()
        assert cb.state == CircuitState.CLOSED  # Threshold reached

    def test_half_open_reopens_on_failure(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,
        )
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()  # Opens
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()  # Failure in half-open → back to open
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerReset:
    """CircuitBreaker manual reset."""

    def test_reset_returns_to_closed(self):
        cb = CircuitBreaker(
            "test-service",
            config=CircuitBreakerConfig(failure_threshold=1),
        )
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_counters(self):
        cb = CircuitBreaker("test-service")
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.reset()
        state = cb.get_state()
        assert state.failure_count == 0
        assert state.success_count == 0
        assert state.half_open_attempts == 0


class TestCircuitBreakerStateTransitions:
    """Full state machine transition tests."""

    def test_closed_to_open(self):
        cb = CircuitBreaker(
            "test-service",
            config=CircuitBreakerConfig(failure_threshold=2),
        )
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open(self):
        config = CircuitBreakerConfig(failure_threshold=1, reset_timeout_ms=50)
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,
            half_open_success_threshold=1,
        )
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()
        time.sleep(0.1)
        # Access state property to trigger OPEN→HALF_OPEN transition
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,
        )
        cb = CircuitBreaker("test-service", config=config)
        cb.record_failure()
        time.sleep(0.1)
        # Access state property to trigger OPEN→HALF_OPEN transition
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_full_cycle_closed_open_halfopen_closed(self):
        config = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout_ms=50,
            half_open_request_percentage=100.0,
            half_open_success_threshold=2,
        )
        cb = CircuitBreaker("test-service", config=config)

        # CLOSED → OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # OPEN → HALF_OPEN
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # HALF_OPEN → CLOSED
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


# ──────────────────────────────────────────────────────────────────────
# ServiceMesh Tests
# ──────────────────────────────────────────────────────────────────────


class TestServiceMeshRegistration:
    """ServiceMesh service registration."""

    def test_register_service(self):
        mesh = ServiceMesh()
        desc = ServiceDescriptor(
            name="auth-api",
            url="http://localhost",
            port=8005,
            category=ServiceCategory.AUTH,
        )
        mesh.register(desc)
        assert mesh.get_service("auth-api") is not None
        assert mesh.get_service("auth-api").name == "auth-api"
        assert mesh.get_service("auth-api").port == 8005

    def test_register_multiple_services(self):
        mesh = ServiceMesh()
        for name, port in [("auth-api", 8005), ("users-api", 8006), ("ai-api", 8009)]:
            mesh.register(ServiceDescriptor(name=name, url="http://localhost", port=port))
        assert len(mesh.get_services()) == 3

    def test_unregister_service(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))
        assert mesh.unregister("auth-api") is True
        assert mesh.get_service("auth-api") is None

    def test_unregister_nonexistent_service(self):
        mesh = ServiceMesh()
        assert mesh.unregister("nonexistent") is False

    def test_register_creates_circuit_breaker(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))
        cb = mesh.get_circuit_breaker("auth-api")
        assert cb is not None
        assert cb.state == CircuitState.CLOSED

    def test_register_with_custom_circuit_breaker_config(self):
        custom_config = CircuitBreakerConfig(failure_threshold=10, reset_timeout_ms=60000)
        mesh = ServiceMesh()
        mesh.register(
            ServiceDescriptor(
                name="auth-api",
                url="http://localhost",
                port=8005,
                circuit_breaker_config=custom_config,
            )
        )
        cb = mesh.get_circuit_breaker("auth-api")
        assert cb.config.failure_threshold == 10
        assert cb.config.reset_timeout_ms == 60000

    def test_register_initialises_health_cache(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))
        health = mesh.get_health("auth-api")
        assert health is not None
        assert health.status == HealthStatus.UNKNOWN


class TestServiceMeshInProcessCalls:
    """ServiceMesh in-process call handlers (bypass HTTP)."""

    @pytest.mark.asyncio
    async def test_call_with_handler(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))

        async def mock_handler(path, payload):
            return {"authenticated": True, "path": path}

        mesh.register_handler("auth-api", mock_handler)
        result = await mesh.call("auth-api", "/verify", {"token": "test"})
        assert result.success is True
        assert result.data["authenticated"] is True
        assert result.data["path"] == "/verify"
        return None

    @pytest.mark.asyncio
    async def test_call_handler_failure(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))

        async def failing_handler(path, payload):
            raise ValueError("authentication failed")

        mesh.register_handler("auth-api", failing_handler)
        result = await mesh.call("auth-api", "/verify", {"token": "bad"})
        assert result.success is False
        assert "authentication failed" in result.error

    @pytest.mark.asyncio
    async def test_call_unregistered_service(self):
        mesh = ServiceMesh()
        result = await mesh.call("nonexistent", "/test")
        assert result.success is False
        assert "not registered" in result.error

    @pytest.mark.asyncio
    async def test_call_records_success_on_circuit_breaker(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))
        mesh.register_handler("auth-api", AsyncMock(return_value={"ok": True}))

        await mesh.call("auth-api", "/test")
        cb = mesh.get_circuit_breaker("auth-api")
        assert cb.get_state().success_count == 1

    @pytest.mark.asyncio
    async def test_call_records_failure_on_circuit_breaker(self):
        mesh = ServiceMesh()
        mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost", port=8005))

        async def failing(path, payload):
            raise RuntimeError("boom")

        mesh.register_handler("auth-api", failing)
        await mesh.call("auth-api", "/test")
        cb = mesh.get_circuit_breaker("auth-api")
        assert cb.get_state().failure_count == 1


class TestServiceMeshDependencyGraph:
    """ServiceMesh dependency graph building."""

    def test_empty_dependency_graph(self):
        mesh = ServiceMesh()
        assert mesh.get_dependency_graph() == {}

    def test_dependency_graph(self):
        mesh = ServiceMesh()
        mesh.register(
            ServiceDescriptor(
                name="auth-api",
                url="http://localhost",
                port=8005,
                dependencies=["users-api"],
            )
        )
        mesh.register(
            ServiceDescriptor(
                name="users-api",
                url="http://localhost",
                port=8006,
                dependencies=[],
            )
        )
        graph = mesh.get_dependency_graph()
        assert graph["auth-api"] == ["users-api"]
        assert graph["users-api"] == []


class TestServiceMeshCleanup:
    """ServiceMesh resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        mesh = ServiceMesh()
        # Register a service to create the client
        mesh.register(ServiceDescriptor(name="test", url="http://localhost", port=8000))
        # Close should not raise
        await mesh.close()


class TestCircuitBreakerIntegration:
    """CircuitBreaker + ServiceMesh integration."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_calls_when_open(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        mesh = ServiceMesh(config=ServiceMeshConfig(circuit_breaker=config))
        mesh.register(ServiceDescriptor(name="flaky-api", url="http://localhost", port=9999))

        async def failing(path, payload):
            raise ConnectionError("service down")

        mesh.register_handler("flaky-api", failing)

        # Trigger failures to open the circuit
        await mesh.call("flaky-api", "/test")
        await mesh.call("flaky-api", "/test")
        cb = mesh.get_circuit_breaker("flaky-api")
        assert cb.state == CircuitState.OPEN

        # Next call should be blocked by circuit breaker
        result = await mesh.call("flaky-api", "/test")
        assert result.success is False
        assert "Circuit breaker OPEN" in result.error


class TestServiceMeshTypes:
    """Pydantic model validation for mesh types."""

    def test_circuit_breaker_config_defaults(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.reset_timeout_ms == 30000
        assert config.half_open_request_percentage == 10.0
        assert config.half_open_success_threshold == 3
        assert config.request_timeout_ms == 10000

    def test_service_descriptor_defaults(self):
        desc = ServiceDescriptor(name="test", url="http://localhost")
        assert desc.port == 8000
        assert desc.category == ServiceCategory.CORE
        assert desc.health_endpoint == "/health"
        assert desc.version == "1.0.0"
        assert desc.tags == []
        assert desc.dependencies == []

    def test_service_descriptor_serialization(self):
        desc = ServiceDescriptor(
            name="auth-api",
            url="http://localhost",
            port=8005,
            category=ServiceCategory.AUTH,
        )
        data = desc.model_dump()
        assert data["name"] == "auth-api"
        assert data["category"] == "auth"

    def test_service_call_result_defaults(self):
        result = ServiceCallResult(success=True)
        assert result.status_code == 0
        assert result.data is None
        assert result.error is None
        assert result.latency_ms == 0.0
        assert result.retries_used == 0
        assert result.circuit_state == CircuitState.CLOSED

    def test_circuit_state_enum_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        # TASD-001 Phase 1: canonicalised from "half-open" to "half_open".
        assert CircuitState.HALF_OPEN.value == "half_open"
        # Backward compatibility: the legacy hyphenated value still resolves
        # (via CircuitState._missing_) so older serialised data keeps parsing.
        assert CircuitState("half-open") == CircuitState.HALF_OPEN

    def test_circuit_state_is_str_enum(self):
        # str-Enum: members compare equal to their string value and are str
        # instances, so every existing `state == "open"` call site keeps working.
        assert CircuitState.OPEN == "open"
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.HALF_OPEN == "half_open"
        assert isinstance(CircuitState.OPEN, str)

    def test_circuit_state_canonical_identity(self):
        # TASD-001 Phase 1: all subsystems must re-export the *same* enum object
        # so the 3-state machine cannot drift again (catches future regressions).
        from src.mesh.types import CircuitState as MeshCircuitState
        from src.nanoservices.circuit_breaker.circuit_breaker import (
            CircuitState as NanoCircuitState,
        )
        from src.resilience.circuit_breaker import CircuitState as ResilienceCircuitState
        from src.resilience.circuit_state import CircuitState as CanonicalCircuitState
        from src.validation.loop_validator import CircuitState as ValidatorCircuitState

        assert (
            MeshCircuitState
            is ResilienceCircuitState
            is NanoCircuitState
            is ValidatorCircuitState
            is CanonicalCircuitState
        )

        canonical_members = {m.name: m.value for m in CanonicalCircuitState}
        for enum_cls in (
            MeshCircuitState,
            ResilienceCircuitState,
            NanoCircuitState,
            ValidatorCircuitState,
        ):
            assert {m.name: m.value for m in enum_cls} == canonical_members

    def test_health_status_enum_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"

    def test_service_category_enum_values(self):
        assert ServiceCategory.CORE.value == "core"
        assert ServiceCategory.AI.value == "ai"
        assert ServiceCategory.AUTH.value == "auth"
        assert ServiceCategory.FINANCIAL.value == "financial"
