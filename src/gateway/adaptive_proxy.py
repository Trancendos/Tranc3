# src/gateway/adaptive_proxy.py
# Health-aware adaptive proxy with circuit breaker and load balancing
# Routes requests through the fluidic router with resilience patterns

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from Dimensional.models import ServiceHealth, ServiceInfo
from Dimensional.registry import ServiceRegistry
from Dimensional.sanitize import sanitize_for_log
from src.fluidic.fluid_router import FluidicRouter, fluid_router
from src.resilience.circuit_breaker import CircuitBreakerConfig, resilience

logger = logging.getLogger(__name__)


class AdaptiveProxy:
    """
    Adaptive gateway proxy that combines fluidic routing with circuit breaking.
    Provides a unified entry point for all inter-service communication.
    """

    def __init__(
        self,
        registry: Optional[ServiceRegistry] = None,
        router: Optional[FluidicRouter] = None,
    ):
        self.registry = registry or ServiceRegistry()
        self.router = router or fluid_router
        self._session = None

    async def _get_session(self):
        """Lazy-initialize aiohttp session"""
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession()
        return self._session

    async def call(
        self,
        capability: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
        retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Call a service by capability with full resilience:
        1. Fluidic routing selects best service
        2. Circuit breaker prevents cascading failures
        3. Retry on transient failures
        4. Fallback to alternative services
        """
        last_error = None

        for attempt in range(retries + 1):
            # Select best service via fluidic routing
            service = self.router.select(capability)
            if not service:
                raise RuntimeError(f"No service available for capability: {capability}")

            # Get circuit breaker for this service
            breaker = resilience.get_breaker(
                service.name,
                CircuitBreakerConfig(failure_threshold=3, recovery_timeout=15.0),
            )

            # Check circuit breaker
            if not breaker.can_execute():
                logger.warning(
                    "Circuit open for %s, trying alternatives", sanitize_for_log(service.name),
                )
                # Try to find an alternative service
                alternatives = self.registry.find_by_capability(capability)
                service = next(
                    (
                        s
                        for s in alternatives
                        if s.name != service.name and s.health != ServiceHealth.UNHEALTHY
                    ),
                    None,
                )
                if not service:
                    raise RuntimeError(
                        f"All services for capability '{capability}' are unavailable",
                    )
                breaker = resilience.get_breaker(service.name)

            # Make the call
            start_time = time.time()
            try:
                result = await breaker.call(
                    self._make_request,
                    service,
                    payload,
                    timeout,
                )
                elapsed = time.time() - start_time
                self.router.record_success(service.name, elapsed * 1000)
                return result

            except Exception as e:
                elapsed = time.time() - start_time
                self.router.record_error(service.name)
                last_error = e
                logger.warning(
                    f"Call to {service.name} failed (attempt {attempt + 1}/{retries + 1}): {e}",
                )

                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff

        raise RuntimeError(f"All attempts failed for capability '{capability}': {last_error}")

    async def _make_request(
        self,
        service: ServiceInfo,
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """Make an HTTP request to a service"""
        import aiohttp

        session = await self._get_session()
        url = service.endpoint

        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Service {service.name} returned {resp.status}: {text}")
            return await resp.json()

    async def health_check(self) -> Dict[str, Any]:
        """Get overall proxy health"""
        return {
            "router": self.router.stats,
            "resilience": resilience.health(),
        }

    async def close(self) -> None:
        """Clean up resources"""
        if self._session:
            await self._session.close()
            self._session = None


# Singleton
adaptive_proxy = AdaptiveProxy()
