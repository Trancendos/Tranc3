"""
Trancendos Service Mesh — Inter-Worker Communication Layer
============================================================
Provides service discovery, circuit breaking, health monitoring,
retries, and distributed tracing for the Trancendos worker mesh.

Ported from: @trancendos/service-mesh (infinity-adminOS, TypeScript)
Zero-cost: Pure Python asyncio + httpx. No external dependencies.

Usage:
    from src.mesh import ServiceMesh, CircuitBreaker

    mesh = ServiceMesh()
    mesh.register("auth-api", url="http://localhost:8002", ...)
    result = await mesh.call("auth-api", "/verify-token", {"token": "..."})
"""

from src.mesh.circuit_breaker import CircuitBreaker, CircuitState
from src.mesh.service_mesh import ServiceDescriptor, ServiceHealth, ServiceMesh
from src.mesh.types import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    HealthStatus,
    RPCMethodDescriptor,
    ServiceCallOptions,
    ServiceCallResult,
    ServiceCategory,
    ServiceMeshConfig,
)

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "ServiceMesh",
    "ServiceDescriptor",
    "ServiceHealth",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "ServiceCallOptions",
    "ServiceCallResult",
    "ServiceCategory",
    "ServiceMeshConfig",
    "HealthStatus",
    "RPCMethodDescriptor",
]
