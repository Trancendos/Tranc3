# shared_core/registry.py
# Service discovery and registration — the heart of nanoservice architecture

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional

from .models import ServiceHealth, ServiceInfo

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Central registry for Trancendos nanoservices.
    Handles discovery, health tracking, capability routing, and event notifications.
    Supports watcher callbacks for reactive service mesh updates.
    """

    def __init__(self):
        self._services: Dict[str, ServiceInfo] = {}
        self._capability_index: Dict[str, List[str]] = {}
        self._watchers: List[Callable] = []
        self._health_check_interval: float = 30.0
        self._health_task: Optional[asyncio.Task] = None

    def register(self, service: ServiceInfo) -> None:
        """Register a service and index its capabilities"""
        self._services[service.name] = service
        for cap in service.capabilities:
            self._capability_index.setdefault(cap.name, []).append(service.name)
        logger.info(f"Registered service: {service.name} @ {service.endpoint}")
        self._notify_watchers("register", service.name)

    def deregister(self, name: str) -> Optional[ServiceInfo]:
        """Remove a service from the registry"""
        service = self._services.pop(name, None)
        if service:
            # Clean up capability index
            for cap in service.capabilities:
                if cap.name in self._capability_index:
                    self._capability_index[cap.name] = [
                        n for n in self._capability_index[cap.name] if n != name
                    ]
                    if not self._capability_index[cap.name]:
                        del self._capability_index[cap.name]
            logger.info(f"Deregistered service: {name}")
            self._notify_watchers("deregister", name)
        return service

    def get(self, name: str) -> Optional[ServiceInfo]:
        """Look up a service by name"""
        return self._services.get(name)

    def find_by_capability(self, capability: str) -> List[ServiceInfo]:
        """Find all healthy services offering a capability"""
        names = self._capability_index.get(capability, [])
        return [
            self._services[n]
            for n in names
            if n in self._services and self._services[n].health != ServiceHealth.UNHEALTHY
        ]

    def find_healthy(self, capability: str) -> Optional[ServiceInfo]:
        """Find the best healthy service for a capability (weighted by last_seen)"""
        candidates = self.find_by_capability(capability)
        if not candidates:
            return None
        # Prefer healthy over degraded, then most recently seen
        healthy = [s for s in candidates if s.health == ServiceHealth.HEALTHY]
        pool = healthy if healthy else candidates
        return max(pool, key=lambda s: s.last_seen)

    def list_all(self) -> List[Dict]:
        """List all registered services"""
        return [s.to_dict() for s in self._services.values()]

    def update_health(self, name: str, health: ServiceHealth) -> None:
        """Update a service's health status"""
        service = self._services.get(name)
        if service:
            old_health = service.health
            service.health = health
            service.last_seen = time.time()
            if old_health != health:
                logger.info(f"Service {name}: {old_health.value} → {health.value}")
                self._notify_watchers("health_change", name)

    def add_watcher(self, callback: Callable) -> None:
        """Register a callback for registry change events"""
        self._watchers.append(callback)

    def _notify_watchers(self, event: str, service_name: str) -> None:
        """Notify all watchers of a registry change"""
        for watcher in self._watchers:
            try:
                watcher(event, service_name)
            except Exception as e:
                logger.error(f"Watcher error: {e}")

    async def start_health_monitor(self) -> None:
        """Start periodic health checking"""
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop_health_monitor(self) -> None:
        """Stop periodic health checking"""
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None

    async def _health_loop(self) -> None:
        """Periodically check service health via HTTP"""
        import aiohttp

        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                async with aiohttp.ClientSession() as session:
                    for name, service in list(self._services.items()):
                        try:
                            async with session.get(
                                service.health_url, timeout=aiohttp.ClientTimeout(total=5)
                            ) as resp:
                                if resp.status == 200:
                                    self.update_health(name, ServiceHealth.HEALTHY)
                                else:
                                    self.update_health(name, ServiceHealth.DEGRADED)
                        except Exception:
                            self.update_health(name, ServiceHealth.UNHEALTHY)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")


# Singleton instance
registry = ServiceRegistry()
