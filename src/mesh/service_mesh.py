"""
Service Mesh — Inter-Worker Communication Layer
=================================================
Ported from @trancendos/service-mesh ServiceMesh class.

Provides service discovery, circuit breaking, health monitoring,
retries with exponential backoff, and distributed tracing.

Zero-cost: Pure Python asyncio + httpx. No external dependencies.

Usage:
    mesh = ServiceMesh()
    await mesh.register(ServiceDescriptor(name="auth-api", url="http://localhost:8002"))
    result = await mesh.call("auth-api", "/verify-token", payload={"token": "..."})
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from shared_core.sanitize import sanitize_for_log
from src.mesh.circuit_breaker import CircuitBreaker
from src.mesh.types import (
    DEFAULT_MESH_CONFIG,
    CircuitState,
    HealthStatus,
    ServiceCallOptions,
    ServiceCallResult,
    ServiceDescriptor,
    ServiceHealth,
    ServiceMeshConfig,
)

logger = logging.getLogger("tranc3.mesh.service_mesh")


class ServiceMesh:
    """
    Service mesh for inter-worker communication.

    Manages service registration, circuit breaking, health checks,
    retries with exponential backoff, and distributed tracing.

    All calls are async and use httpx for HTTP transport.
    """

    def __init__(self, config: ServiceMeshConfig | None = None) -> None:
        self.config = config or DEFAULT_MESH_CONFIG
        self._services: dict[str, ServiceDescriptor] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._health_cache: dict[str, ServiceHealth] = {}
        self._call_handlers: dict[str, Callable] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._health_task: asyncio.Task | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.circuit_breaker.request_timeout_ms / 1000.0),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Clean up resources."""
        if self._health_task:
            self._health_task.cancel()
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ── Registration ─────────────────────────────────────────

    def register(self, descriptor: ServiceDescriptor) -> None:
        """
        Register a service with the mesh.

        Creates a circuit breaker for the service and initialises
        health tracking.
        """
        self._services[descriptor.name] = descriptor

        # Create circuit breaker with service-specific config or default
        cb_config = descriptor.circuit_breaker_config or self.config.circuit_breaker
        self._circuit_breakers[descriptor.name] = CircuitBreaker(
            service_name=descriptor.name,
            config=cb_config,
        )

        # Initialise health cache
        self._health_cache[descriptor.name] = ServiceHealth(
            name=descriptor.name,
            status=HealthStatus.UNKNOWN,
        )

        logger.info(
            "service_registered",
            extra={
                "service": descriptor.name,
                "url": descriptor.url,
                "category": descriptor.category.value,
            },
        )

    def unregister(self, service_name: str) -> bool:
        """Remove a service from the mesh."""
        removed = service_name in self._services
        self._services.pop(service_name, None)
        self._circuit_breakers.pop(service_name, None)
        self._health_cache.pop(service_name, None)
        self._call_handlers.pop(service_name, None)
        return removed

    def register_handler(self, service_name: str, handler: Callable) -> None:
        """Register a direct call handler (bypasses HTTP, for in-process calls)."""
        self._call_handlers[service_name] = handler

    # ── Service Calls ────────────────────────────────────────

    async def call(
        self,
        service_name: str,
        path: str,
        payload: dict[str, Any] | None = None,
        options: ServiceCallOptions | None = None,
    ) -> ServiceCallResult:
        """
        Call a service through the mesh.

        Features:
        - Circuit breaker protection
        - Automatic retries with exponential backoff
        - Distributed trace propagation
        - Latency tracking
        """
        opts = options or ServiceCallOptions()
        trace_id = opts.trace_id or str(uuid.uuid4())

        # Check service exists
        descriptor = self._services.get(service_name)
        if not descriptor:
            return ServiceCallResult(
                success=False,
                error=f"Service '{service_name}' not registered",
                trace_id=trace_id,
            )

        # Check circuit breaker
        if opts.circuit_breaker_enabled:
            cb = self._circuit_breakers.get(service_name)
            if cb and not cb.can_execute():
                cb_state = cb.get_state()
                return ServiceCallResult(
                    success=False,
                    error=f"Circuit breaker OPEN for '{service_name}'",
                    circuit_state=cb_state.state,
                    trace_id=trace_id,
                    provider=service_name,
                )

        # Try direct handler first (in-process call)
        handler = self._call_handlers.get(service_name)
        if handler:
            return await self._call_handler(
                handler, service_name, path, payload, opts, trace_id
            )

        # HTTP call with retries
        return await self._call_http(
            descriptor, service_name, path, payload, opts, trace_id
        )

    async def _call_handler(
        self,
        handler: Callable,
        service_name: str,
        path: str,
        payload: dict[str, Any] | None,
        options: ServiceCallOptions,
        trace_id: str,
    ) -> ServiceCallResult:
        """Execute an in-process call handler."""
        start = time.monotonic()
        try:
            result = await handler(path, payload)
            latency_ms = (time.monotonic() - start) * 1000

            cb = self._circuit_breakers.get(service_name)
            if cb:
                cb.record_success()

            return ServiceCallResult(
                success=True,
                data=result,
                latency_ms=latency_ms,
                trace_id=trace_id,
                provider=service_name,
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            cb = self._circuit_breakers.get(service_name)
            if cb:
                cb.record_failure()

            return ServiceCallResult(
                success=False,
                error=str(e),
                latency_ms=latency_ms,
                trace_id=trace_id,
                provider=service_name,
            )
        return None

    async def _call_http(
        self,
        descriptor: ServiceDescriptor,
        service_name: str,
        path: str,
        payload: dict[str, Any] | None,
        options: ServiceCallOptions,
        trace_id: str,
    ) -> ServiceCallResult:
        """Execute an HTTP call with retries and circuit breaking."""
        max_retries = min(options.retries, self.config.max_retries)
        last_error: str | None = None
        retries_used = 0

        for attempt in range(max_retries + 1):
            start = time.monotonic()

            try:
                client = await self._get_client()
                url = f"{descriptor.url}:{descriptor.port}{path}"

                headers = {
                    **options.headers,
                    "X-Trace-ID": trace_id,
                    "X-Service-Source": "tranc3-mesh",
                }
                if self.config.trace_propagation:
                    headers["X-Request-ID"] = str(uuid.uuid4())

                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=options.timeout_ms / 1000.0,
                )

                latency_ms = (time.monotonic() - start) * 1000

                if response.status_code < 400:
                    # Success
                    cb = self._circuit_breakers.get(service_name)
                    if cb:
                        cb.record_success()

                    return ServiceCallResult(
                        success=True,
                        status_code=response.status_code,
                        data=response.json() if response.content else None,
                        latency_ms=latency_ms,
                        retries_used=retries_used,
                        circuit_state=CircuitState.CLOSED,
                        trace_id=trace_id,
                        provider=service_name,
                    )
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                    retries_used = attempt

                    # Don't retry client errors (4xx) except 429
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        break

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = str(e)
                retries_used = attempt
                latency_ms = (time.monotonic() - start) * 1000

            # Record failure for circuit breaker
            cb = self._circuit_breakers.get(service_name)
            if cb:
                cb.record_failure()

            # Check if we should retry
            if attempt < max_retries:
                # Exponential backoff with jitter
                delay = min(
                    self.config.retry_base_delay_ms * (2 ** attempt),
                    self.config.retry_max_delay_ms,
                ) / 1000.0
                # Add jitter (±25%)
                jitter = delay * 0.25 * (2 * (0.5 - asyncio.get_event_loop().time() % 1))
                await asyncio.sleep(max(0.1, delay + jitter))

        # All retries exhausted
        cb = self._circuit_breakers.get(service_name)
        cb_state = cb.get_state().state if cb else CircuitState.CLOSED

        return ServiceCallResult(
            success=False,
            error=last_error or "All retries exhausted",
            retries_used=retries_used,
            circuit_state=cb_state,
            trace_id=trace_id,
            provider=service_name,
        )

    # ── Health Checks ────────────────────────────────────────

    async def health_check(self, service_name: str) -> ServiceHealth:
        """Check the health of a specific service."""
        descriptor = self._services.get(service_name)
        if not descriptor:
            return ServiceHealth(
                name=service_name,
                status=HealthStatus.UNKNOWN,
                error="Service not registered",
            )

        start = time.monotonic()
        try:
            client = await self._get_client()
            url = f"{descriptor.url}:{descriptor.port}{descriptor.health_endpoint}"
            response = await client.get(url, timeout=self.config.health_check_timeout_ms / 1000.0)
            latency_ms = (time.monotonic() - start) * 1000

            status = HealthStatus.HEALTHY if response.status_code == 200 else HealthStatus.DEGRADED
            health = ServiceHealth(
                name=service_name,
                status=status,
                latency_ms=latency_ms,
                last_checked=datetime.now(timezone.utc),
                metadata=response.json() if response.content else {},
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            health = ServiceHealth(
                name=service_name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                last_checked=datetime.now(timezone.utc),
                error=str(e),
            )

        self._health_cache[service_name] = health
        return health

    async def health_check_all(self) -> dict[str, ServiceHealth]:
        """Run health checks on all registered services concurrently."""
        results = {}
        tasks = {
            name: self.health_check(name) for name in self._services
        }
        for name, task in tasks.items():
            results[name] = await task
        return results

    def get_health(self, service_name: str) -> ServiceHealth | None:
        """Get the cached health status for a service."""
        return self._health_cache.get(service_name)

    # ── Query ────────────────────────────────────────────────

    def get_services(self) -> list[ServiceDescriptor]:
        """Get all registered services."""
        return list(self._services.values())

    def get_service(self, name: str) -> ServiceDescriptor | None:
        """Get a specific service descriptor."""
        return self._services.get(name)

    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker | None:
        """Get the circuit breaker for a service."""
        return self._circuit_breakers.get(service_name)

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Build a dependency graph from service registrations."""
        return {
            name: desc.dependencies
            for name, desc in self._services.items()
        }

    # ── Background Health Monitoring ─────────────────────────

    async def start_health_monitor(self) -> None:
        """Start background health monitoring for all services."""
        self._health_task = asyncio.create_task(self._health_monitor_loop())

    async def _health_monitor_loop(self) -> None:
        """Periodically check health of all services."""
        while True:
            try:
                await self.health_check_all()
            except Exception as e:
                logger.error("health_monitor_error: %s", sanitize_for_log(e))
            await asyncio.sleep(self.config.health_check_interval_ms / 1000.0)
