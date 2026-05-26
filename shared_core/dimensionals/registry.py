"""
Trancendos Dimensional Service Registry
=========================================
Central registry for Dimensional's — the shared-core services that form
the backbone of the Infinity Ecosystem. Each dimensional service is
associated with a Pillar and governed by a Prime.

The registry tracks:
    - Service identity and metadata
    - Pillar association (which domain this dimensional serves)
    - Tier requirement (minimum tier needed to access this dimensional)
    - Health status and uptime
    - Capabilities offered by the dimensional
    - Underverse modules registered under this dimensional
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from shared_core.infinity.nomenclature import Pillar, Tier

logger = logging.getLogger(__name__)


# ── Dimensional Service Status ──────────────────────────────────────────────


class DimensionalServiceStatus(str, Enum):
    """Status of a dimensional service instance."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    INACTIVE = "inactive"
    STARTING = "starting"
    STOPPING = "stopping"
    MAINTENANCE = "maintenance"


# ── Dimensional Service Definition ──────────────────────────────────────────


@dataclass
class DimensionalService:
    """A Dimensional's service in the Infinity Ecosystem.

    Dimensional's are the shared-core services that provide fundamental
    capabilities across the platform. Each is associated with a Pillar
    and governed by a Prime.

    Attributes:
        id: Unique identifier (e.g., "gateway", "sentinel_station")
        name: Human-readable name (e.g., "Gateway Dimensional")
        description: What this dimensional service provides
        pillar: The Pillar this dimensional belongs to
        tier: Minimum Tier required to access this dimensional
        status: Current operational status
        capabilities: List of capability names this dimensional offers
        endpoint: HTTP endpoint URL (if applicable)
        port: Service port number (if applicable)
        prime_id: The Prime that governs this dimensional
        metadata: Additional metadata key-value pairs
        registered_at: ISO timestamp of when this dimensional was registered
        last_heartbeat: ISO timestamp of last health check
    """

    id: str
    name: str
    description: str = ""
    pillar: Pillar = Pillar.ARCHITECTURAL
    tier: Tier = Tier.HUMAN
    status: DimensionalServiceStatus = DimensionalServiceStatus.INACTIVE
    capabilities: List[str] = field(default_factory=list)
    endpoint: str = ""
    port: int = 0
    prime_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        # Auto-assign prime based on pillar if not explicitly set
        if self.prime_id is None:
            from shared_core.infinity.nomenclature import PILLAR_PRIME_MAP

            self.prime_id = PILLAR_PRIME_MAP.get(self.pillar)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "pillar": self.pillar.value,
            "pillar_display": self.pillar.display_name,
            "tier": self.tier.value,
            "tier_display": self.tier.display_name,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "port": self.port,
            "prime_id": self.prime_id,
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
        }


# ── Dimensional Service Registry ────────────────────────────────────────────


class DimensionalServiceRegistry:
    """Central registry for Dimensional's services.

    Manages the lifecycle and discovery of dimensional services across
    the Infinity Ecosystem. Supports registration, deregistration,
    health tracking, pillar-based queries, and capability routing.

    The registry integrates with the existing ServiceRegistry from
    shared_core.registry, providing an additional layer of pillar
    and tier semantics on top of the basic service discovery.
    """

    def __init__(self) -> None:
        self._services: Dict[str, DimensionalService] = {}
        self._watchers: List[Callable] = []
        self._stats = {
            "total_registrations": 0,
            "total_deregistrations": 0,
            "total_status_changes": 0,
        }

    def register(self, service: DimensionalService) -> None:
        """Register a dimensional service.

        If a service with the same ID already exists, it is updated.
        """
        is_update = service.id in self._services
        self._services[service.id] = service
        service.status = DimensionalServiceStatus.ACTIVE

        self._stats["total_registrations"] += 1

        if is_update:
            logger.info("Updated dimensional service: %s", service.id)
        else:
            logger.info(
                "Registered dimensional service: %s (pillar=%s, tier=%s)",
                service.id,
                service.pillar.value,
                service.tier.display_name,
            )

        self._notify_watchers("register" if not is_update else "update", service.id)

    def deregister(self, service_id: str) -> Optional[DimensionalService]:
        """Remove a dimensional service from the registry."""
        service = self._services.pop(service_id, None)
        if service:
            self._stats["total_deregistrations"] += 1
            logger.info("Deregistered dimensional service: %s", service_id)
            self._notify_watchers("deregister", service_id)
        return service

    def get(self, service_id: str) -> Optional[DimensionalService]:
        """Look up a dimensional service by ID."""
        return self._services.get(service_id)

    def get_by_pillar(self, pillar: Pillar) -> List[DimensionalService]:
        """Get all dimensional services associated with a pillar."""
        return [s for s in self._services.values() if s.pillar == pillar]

    def get_by_tier(self, tier: Tier) -> List[DimensionalService]:
        """Get all dimensional services accessible at a given tier."""
        return [s for s in self._services.values() if s.tier <= tier]

    def get_by_capability(self, capability: str) -> List[DimensionalService]:
        """Find all dimensional services offering a specific capability."""
        return [
            s
            for s in self._services.values()
            if capability in s.capabilities and s.status == DimensionalServiceStatus.ACTIVE
        ]

    def get_by_status(self, status: DimensionalServiceStatus) -> List[DimensionalService]:
        """Get all dimensional services with a specific status."""
        return [s for s in self._services.values() if s.status == status]

    def update_status(self, service_id: str, status: DimensionalServiceStatus) -> bool:
        """Update a dimensional service's status."""
        service = self._services.get(service_id)
        if not service:
            return False
        old_status = service.status
        service.status = status
        service.last_heartbeat = datetime.now(timezone.utc).isoformat()
        if old_status != status:
            self._stats["total_status_changes"] += 1
            logger.info(
                "Dimensional %s: %s → %s",
                service_id,
                old_status.value,
                status.value,
            )
            self._notify_watchers("status_change", service_id)
        return True

    def heartbeat(self, service_id: str) -> bool:
        """Record a heartbeat for a dimensional service."""
        service = self._services.get(service_id)
        if not service:
            return False
        service.last_heartbeat = datetime.now(timezone.utc).isoformat()
        if service.status == DimensionalServiceStatus.INACTIVE:
            service.status = DimensionalServiceStatus.ACTIVE
        return True

    def list_all(self) -> List[Dict[str, Any]]:
        """List all registered dimensional services."""
        return [s.to_dict() for s in self._services.values()]

    def get_pillar_summary(self) -> Dict[str, Any]:
        """Get a summary of dimensional services organized by pillar."""
        summary: Dict[str, Any] = {}
        for pillar in Pillar:
            services = self.get_by_pillar(pillar)
            summary[pillar.value] = {
                "display_name": pillar.display_name,
                "accent_color": pillar.accent_color,
                "prime_id": pillar.prime_id,
                "services": [s.to_dict() for s in services],
                "total_services": len(services),
                "active_services": sum(
                    1 for s in services if s.status == DimensionalServiceStatus.ACTIVE
                ),
            }
        return summary

    def add_watcher(self, callback: Callable) -> None:
        """Register a callback for registry change events."""
        self._watchers.append(callback)

    def _notify_watchers(self, event: str, service_id: str) -> None:
        """Notify all watchers of a registry change."""
        for watcher in self._watchers:
            try:
                watcher(event, service_id)
            except Exception as e:
                logger.warning("Watcher error: %s", str(e)[:200])

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            **self._stats,
            "total_services": len(self._services),
            "active_services": sum(
                1 for s in self._services.values() if s.status == DimensionalServiceStatus.ACTIVE
            ),
            "pillars_represented": len({s.pillar for s in self._services.values()}),
        }


# ── Module-level Singleton ──────────────────────────────────────────────────

_dimensional_registry: Optional[DimensionalServiceRegistry] = None


def get_dimensional_registry() -> DimensionalServiceRegistry:
    """Get or create the Dimensional Service Registry singleton."""
    global _dimensional_registry
    if _dimensional_registry is None:
        _dimensional_registry = DimensionalServiceRegistry()
        _register_default_dimensionals(_dimensional_registry)
    return _dimensional_registry


def _register_default_dimensionals(registry: DimensionalServiceRegistry) -> None:
    """Register the built-in Dimensional's services.

    These are the core services of the Infinity Ecosystem that
    are always available as dimensional services.
    """

    defaults = [
        DimensionalService(
            id="gateway",
            name="Gateway Dimensional",
            description="Unified aggregation gateway for the Tranc3 AI Platform",
            pillar=Pillar.ARCHITECTURAL,
            tier=Tier.HUMAN,
            capabilities=["aggregation", "proxy", "cache", "sse", "websocket"],
            endpoint="http://localhost:8040",
            port=8040,
        ),
        DimensionalService(
            id="sentinel_station",
            name="Sentinel Station Dimensional",
            description="Event bus bridge (interplexus hub) for cross-gateway event distribution",
            pillar=Pillar.DEVOPS,
            tier=Tier.AGENT,
            capabilities=["pubsub", "events", "sse", "redis", "fallback"],
            endpoint="http://localhost:8041",
            port=8041,
        ),
        DimensionalService(
            id="infinity_auth",
            name="Infinity Auth Dimensional",
            description="Authentication and authorization service for the Infinity Portal",
            pillar=Pillar.SECURITY,
            tier=Tier.HUMAN,
            capabilities=["jwt", "oauth2", "authentication", "authorization"],
            endpoint="http://localhost:8039",
            port=8039,
        ),
        DimensionalService(
            id="infinity_portal",
            name="Infinity Portal Dimensional",
            description="Central login and gateway routing service",
            pillar=Pillar.ARCHITECTURAL,
            tier=Tier.HUMAN,
            capabilities=["login", "routing", "gate"],
            endpoint="http://localhost:8042",
            port=8042,
        ),
        DimensionalService(
            id="infinity_one",
            name="Infinity-One Dimensional",
            description="User management and identity service",
            pillar=Pillar.SECURITY,
            tier=Tier.HUMAN,
            capabilities=["users", "identity", "profiles"],
            endpoint="http://localhost:8043",
            port=8043,
        ),
        DimensionalService(
            id="infinity_admin",
            name="Infinity-Admin Dimensional",
            description="Administrative management OS for the Trancendos Universe",
            pillar=Pillar.ARCHITECTURAL,
            tier=Tier.ORCHESTRATOR,
            capabilities=["admin", "management", "configuration"],
            endpoint="http://localhost:8044",
            port=8044,
        ),
        DimensionalService(
            id="vault",
            name="Vault Dimensional",
            description="Secret management and security audit service",
            pillar=Pillar.SECURITY,
            tier=Tier.PRIME,
            capabilities=["secrets", "audit", "encryption"],
            endpoint="http://localhost:8030",
            port=8030,
        ),
        DimensionalService(
            id="topology",
            name="Topology Dimensional",
            description="Network topology and node management service",
            pillar=Pillar.DEVOPS,
            tier=Tier.PRIME,
            capabilities=["topology", "nodes", "mesh"],
            endpoint="http://localhost:8031",
            port=8031,
        ),
        DimensionalService(
            id="ledger",
            name="Ledger Dimensional",
            description="Immutable audit ledger and chain verification service",
            pillar=Pillar.SECURITY,
            tier=Tier.PRIME,
            capabilities=["ledger", "chain", "audit"],
            endpoint="http://localhost:8032",
            port=8032,
        ),
        DimensionalService(
            id="model_router",
            name="Model Router Dimensional",
            description="AI model routing and inference service",
            pillar=Pillar.CREATIVITY,
            tier=Tier.AI,
            capabilities=["models", "routing", "inference"],
            endpoint="http://localhost:8033",
            port=8033,
        ),
        DimensionalService(
            id="workflow",
            name="Workflow Dimensional",
            description="Workflow engine for orchestration and automation",
            pillar=Pillar.DEVELOPMENT,
            tier=Tier.AI,
            capabilities=["workflows", "orchestration", "automation"],
            endpoint="http://localhost:8034",
            port=8034,
        ),
        DimensionalService(
            id="deepagents",
            name="DeepAgents Dimensional",
            description="AI agent orchestration and lifecycle management",
            pillar=Pillar.DEVELOPMENT,
            tier=Tier.AI,
            capabilities=["agents", "skills", "tasks", "orchestration"],
            endpoint="http://localhost:8037",
            port=8037,
        ),
    ]

    for svc in defaults:
        registry.register(svc)
