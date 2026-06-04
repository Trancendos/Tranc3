"""
Service Mesh Types — Data models and configuration
====================================================
Ported from @trancendos/service-mesh TypeScript types.
All Pydantic v2 models for validation and serialisation.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────


class CircuitState(str, enum.Enum):
    """Circuit breaker states — closed (healthy), open (failing), half-open (testing)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class HealthStatus(str, enum.Enum):
    """Service health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceCategory(str, enum.Enum):
    """Service category for routing and dependency management."""

    CORE = "core"
    AI = "ai"
    AUTH = "auth"
    DATA = "data"
    MESSAGING = "messaging"
    OBSERVABILITY = "observability"
    FINANCIAL = "financial"
    GATEWAY = "gateway"


# ── Configuration ────────────────────────────────────────────


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration — controls failure detection and recovery."""

    failure_threshold: int = Field(default=5, description="Failures before opening circuit")
    reset_timeout_ms: int = Field(default=30000, description="Time before half-open retry (ms)")
    half_open_request_percentage: float = Field(
        default=10.0,
        description="% of requests allowed in half-open",
    )
    half_open_success_threshold: int = Field(
        default=3,
        description="Successes needed to close circuit",
    )
    request_timeout_ms: int = Field(default=10000, description="Per-request timeout (ms)")

    model_config = {"frozen": True}


class ServiceMeshConfig(BaseModel):
    """Service mesh global configuration."""

    max_retries: int = Field(default=3, description="Max retry attempts per call")
    retry_base_delay_ms: int = Field(
        default=1000,
        description="Base delay for exponential backoff (ms)",
    )
    retry_max_delay_ms: int = Field(default=30000, description="Max delay between retries (ms)")
    health_check_interval_ms: int = Field(default=30000, description="Health check interval (ms)")
    health_check_timeout_ms: int = Field(default=5000, description="Health check timeout (ms)")
    trace_propagation: bool = Field(default=True, description="Propagate trace IDs across services")
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    model_config = {"frozen": True}


# ── Data Models ──────────────────────────────────────────────


class CircuitBreakerState(BaseModel):
    """Current state of a circuit breaker for a service."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    half_open_attempts: int = 0


class ServiceDescriptor(BaseModel):
    """Registration info for a service in the mesh."""

    name: str
    url: str
    port: int = 8000
    category: ServiceCategory = ServiceCategory.CORE
    health_endpoint: str = "/health"
    version: str = "1.0.0"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None


class ServiceHealth(BaseModel):
    """Health status of a registered service."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    latency_ms: float = 0.0
    last_checked: Optional[datetime] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceCallOptions(BaseModel):
    """Options for a service-to-service call."""

    timeout_ms: int = Field(default=10000, description="Request timeout (ms)")
    retries: int = Field(default=3, description="Number of retry attempts")
    headers: dict[str, str] = Field(default_factory=dict)
    circuit_breaker_enabled: bool = True
    trace_id: Optional[str] = None
    skip_cache: bool = False


class ServiceCallResult(BaseModel):
    """Result of a service-to-service call."""

    success: bool
    status_code: int = 0
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    retries_used: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    trace_id: Optional[str] = None
    provider: Optional[str] = None


class RPCMethodDescriptor(BaseModel):
    """Descriptor for an RPC method exposed by a service."""

    name: str
    path: str
    method: str = "POST"
    input_schema: Optional[dict[str, Any]] = None
    output_schema: Optional[dict[str, Any]] = None
    description: str = ""


# ── Defaults ─────────────────────────────────────────────────

DEFAULT_MESH_CONFIG = ServiceMeshConfig()
DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig()
