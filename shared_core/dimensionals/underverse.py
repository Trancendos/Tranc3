"""
Trancendos Underverse Registry
================================
Per-app nanoservice registry that organizes domain-specific microservices
under their parent Dimensional's (Shared-Core) services in the Infinity
Ecosystem.

The Underverse is the innermost layer of the service architecture:

    Dimensional's (Shared-Core) --> Service Bus --> Underverse --> Per-App Nanoservices

Each Underverse module is a lightweight, domain-specific nanoservice that
operates under the governance of a parent Dimensional. Underverse modules
inherit the pillar and tier associations of their parent dimensional, but
can also define their own capability scope.

Architecture:
    Infinity Ecosystem
    └── Dimensional's (Shared-Core Services)
        └── Underverse (Per-App Nanoservices)
            └── Module (Individual nanoservice instance)

Naming Convention:
    "Underverse" = the collection of per-app nanoservice registries
    in the Trancendos Universe. Each Underverse module is a
    domain-specific microservice operating under a Dimensional.

OWASP Alignment:
    A01 (Broken Access Control): Tier-aware module access
    A09 (Security Logging): All module operations are audit-logged

Usage:
    from shared_core.dimensionals.underverse import UnderverseRegistry, get_underverse_registry

    registry = get_underverse_registry()

    # Register an underverse module
    module = registry.register_module(UnderverseModule(
        id="agent_scheduler",
        name="Agent Scheduler",
        parent_dimensional="deepagents",
        description="Schedules and dispatches agent tasks",
        capabilities=["scheduling", "dispatch", "priority_queue"],
    ))

    # Get all modules under a dimensional
    modules = registry.get_by_dimensional("deepagents")

    # Get modules by capability
    schedulers = registry.get_by_capability("scheduling")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from shared_core.dimensionals.registry import (
    get_dimensional_registry,
)
from shared_core.infinity.nomenclature import Pillar, Tier

logger = logging.getLogger(__name__)


# ── Underverse Module Status ──────────────────────────────────────────────


class UnderverseModuleStatus(str, Enum):
    """Status of an Underverse module instance."""

    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"
    STARTING = "starting"


# ── Underverse Module Definition ──────────────────────────────────────────


@dataclass
class UnderverseModule:
    """An Underverse module: a per-app nanoservice in the Infinity Ecosystem.

    Underverse modules are lightweight, domain-specific nanoservices that
    operate under the governance of a parent Dimensional's service. They
    inherit pillar and tier associations from their parent, but can also
    define their own capability scope and metadata.

    Attributes:
        id: Unique module identifier (e.g., "agent_scheduler")
        name: Human-readable name (e.g., "Agent Scheduler")
        description: What this underverse module provides
        parent_dimensional: The Dimensional's service this module belongs to
        pillar: Inherited from parent dimensional (can be overridden)
        tier: Minimum tier required to access this module
        status: Current operational status
        capabilities: List of capability names this module offers
        endpoint: HTTP endpoint URL (if applicable)
        port: Service port number (if applicable)
        version: Module version string
        metadata: Additional metadata key-value pairs
        registered_at: ISO timestamp of when this module was registered
        last_active: ISO timestamp of last activity
    """

    id: str
    name: str
    description: str = ""
    parent_dimensional: str = ""
    pillar: Optional[Pillar] = None
    tier: Tier = Tier.AGENT
    status: UnderverseModuleStatus = UnderverseModuleStatus.STOPPED
    capabilities: List[str] = field(default_factory=list)
    endpoint: str = ""
    port: int = 0
    version: str = "0.1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Auto-inherit pillar from parent dimensional if not explicitly set."""
        if self.pillar is None and self.parent_dimensional:
            try:
                registry = get_dimensional_registry()
                parent = registry.get(self.parent_dimensional)
                if parent:
                    self.pillar = parent.pillar
                    # Only inherit tier if it's still the default
                    if self.tier == Tier.AGENT and parent.tier != Tier.AGENT:
                        self.tier = parent.tier
            except Exception:
                pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_dimensional": self.parent_dimensional,
            "pillar": self.pillar.value if self.pillar else None,
            "pillar_display": self.pillar.display_name if self.pillar else None,
            "tier": self.tier.value,
            "tier_display": self.tier.display_name,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "port": self.port,
            "version": self.version,
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "last_active": self.last_active,
        }


# ── Underverse Registry ──────────────────────────────────────────────────


class UnderverseRegistry:
    """Registry for Underverse modules: per-app nanoservices in the Infinity Ecosystem.

    The Underverse Registry manages the lifecycle and discovery of Underverse
    modules, which are lightweight nanoservices organized under their parent
    Dimensional's services. It provides:

    - Module registration and deregistration
    - Discovery by parent dimensional, capability, pillar, or tier
    - Health tracking and status management
    - Module activation/deactivation
    - Statistics and monitoring

    The Underverse is the innermost layer of the service hierarchy:

        Dimensional's --> Underverse --> Per-App Nanoservices

    Each Underverse module inherits pillar and tier associations from
    its parent Dimensional, ensuring consistent access control and
    routing semantics throughout the hierarchy.
    """

    def __init__(self) -> None:
        self._modules: Dict[str, UnderverseModule] = {}
        self._watchers: List[Callable] = []
        self._stats = {
            "total_registrations": 0,
            "total_deregistrations": 0,
            "total_activations": 0,
            "total_deactivations": 0,
        }

    # ── Registration ──────────────────────────────────────────────────────

    def register_module(self, module: UnderverseModule) -> UnderverseModule:
        """Register an Underverse module.

        If a module with the same ID already exists, it is updated.

        Args:
            module: The UnderverseModule to register

        Returns:
            The registered module (with auto-inherited pillar/tier if applicable)
        """
        is_update = module.id in self._modules
        self._modules[module.id] = module
        module.status = UnderverseModuleStatus.ACTIVE

        self._stats["total_registrations"] += 1

        if is_update:
            logger.info("Updated underverse module: %s", module.id)
        else:
            logger.info(
                "Registered underverse module: %s (parent=%s, pillar=%s)",
                module.id,
                module.parent_dimensional,
                module.pillar.value if module.pillar else "none",
            )

        self._notify_watchers("register" if not is_update else "update", module.id)
        return module

    def deregister_module(self, module_id: str) -> Optional[UnderverseModule]:
        """Remove an Underverse module from the registry.

        Args:
            module_id: The module ID to remove

        Returns:
            The removed module, or None if not found
        """
        module = self._modules.pop(module_id, None)
        if module:
            self._stats["total_deregistrations"] += 1
            logger.info("Deregistered underverse module: %s", module_id)
            self._notify_watchers("deregister", module_id)
        return module

    def get(self, module_id: str) -> Optional[UnderverseModule]:
        """Look up an Underverse module by ID.

        Args:
            module_id: The module ID to look up

        Returns:
            The UnderverseModule, or None if not found
        """
        return self._modules.get(module_id)

    # ── Discovery ─────────────────────────────────────────────────────────

    def get_by_dimensional(self, parent_dimensional: str) -> List[UnderverseModule]:
        """Get all Underverse modules belonging to a specific Dimensional.

        Args:
            parent_dimensional: The parent Dimensional's service ID

        Returns:
            List of UnderverseModule instances under the given dimensional
        """
        return [m for m in self._modules.values() if m.parent_dimensional == parent_dimensional]

    def get_by_capability(self, capability: str) -> List[UnderverseModule]:
        """Find all Underverse modules offering a specific capability.

        Only returns active modules.

        Args:
            capability: The capability name to search for

        Returns:
            List of active UnderverseModule instances with the capability
        """
        return [
            m
            for m in self._modules.values()
            if capability in m.capabilities
            and m.status
            in (
                UnderverseModuleStatus.ACTIVE,
                UnderverseModuleStatus.IDLE,
                UnderverseModuleStatus.BUSY,
            )
        ]

    def get_by_pillar(self, pillar: Pillar) -> List[UnderverseModule]:
        """Get all Underverse modules associated with a pillar.

        Args:
            pillar: The Pillar to filter by

        Returns:
            List of UnderverseModule instances with the given pillar
        """
        return [m for m in self._modules.values() if m.pillar == pillar]

    def get_by_tier(self, tier: Tier) -> List[UnderverseModule]:
        """Get all Underverse modules accessible at a given tier.

        Returns modules whose tier requirement is at or below the given tier.

        Args:
            tier: The Tier to filter by

        Returns:
            List of UnderverseModule instances accessible at the given tier
        """
        return [m for m in self._modules.values() if m.tier <= tier]

    def get_by_status(self, status: UnderverseModuleStatus) -> List[UnderverseModule]:
        """Get all Underverse modules with a specific status.

        Args:
            status: The status to filter by

        Returns:
            List of UnderverseModule instances with the given status
        """
        return [m for m in self._modules.values() if m.status == status]

    # ── Lifecycle Management ──────────────────────────────────────────────

    def activate(self, module_id: str) -> bool:
        """Activate an Underverse module.

        Args:
            module_id: The module ID to activate

        Returns:
            True if the module was activated, False if not found
        """
        module = self._modules.get(module_id)
        if not module:
            return False
        module.status = UnderverseModuleStatus.ACTIVE
        module.last_active = datetime.now(timezone.utc).isoformat()
        self._stats["total_activations"] += 1
        self._notify_watchers("activate", module_id)
        return True

    def deactivate(self, module_id: str) -> bool:
        """Deactivate an Underverse module.

        Args:
            module_id: The module ID to deactivate

        Returns:
            True if the module was deactivated, False if not found
        """
        module = self._modules.get(module_id)
        if not module:
            return False
        module.status = UnderverseModuleStatus.STOPPED
        self._stats["total_deactivations"] += 1
        self._notify_watchers("deactivate", module_id)
        return True

    def set_status(self, module_id: str, status: UnderverseModuleStatus) -> bool:
        """Set the status of an Underverse module.

        Args:
            module_id: The module ID
            status: The new status

        Returns:
            True if the status was updated, False if not found
        """
        module = self._modules.get(module_id)
        if not module:
            return False
        old_status = module.status
        module.status = status
        module.last_active = datetime.now(timezone.utc).isoformat()
        if old_status != status:
            logger.info(
                "Underverse module %s: %s -> %s",
                module_id,
                old_status.value,
                status.value,
            )
            self._notify_watchers("status_change", module_id)
        return True

    def heartbeat(self, module_id: str) -> bool:
        """Record a heartbeat for an Underverse module.

        Args:
            module_id: The module ID

        Returns:
            True if the heartbeat was recorded, False if not found
        """
        module = self._modules.get(module_id)
        if not module:
            return False
        module.last_active = datetime.now(timezone.utc).isoformat()
        if module.status == UnderverseModuleStatus.STOPPED:
            module.status = UnderverseModuleStatus.ACTIVE
        return True

    # ── Listing & Summaries ───────────────────────────────────────────────

    def list_all(self) -> List[Dict[str, Any]]:
        """List all registered Underverse modules.

        Returns:
            List of module dictionaries
        """
        return [m.to_dict() for m in self._modules.values()]

    def get_dimensional_summary(self, parent_dimensional: str) -> Dict[str, Any]:
        """Get a summary of Underverse modules organized under a specific Dimensional.

        Args:
            parent_dimensional: The parent Dimensional's service ID

        Returns:
            Summary dictionary with module counts and details
        """
        modules = self.get_by_dimensional(parent_dimensional)
        active_count = sum(
            1
            for m in modules
            if m.status
            in (
                UnderverseModuleStatus.ACTIVE,
                UnderverseModuleStatus.IDLE,
                UnderverseModuleStatus.BUSY,
            )
        )
        return {
            "parent_dimensional": parent_dimensional,
            "total_modules": len(modules),
            "active_modules": active_count,
            "modules": [m.to_dict() for m in modules],
            "capabilities": list({cap for m in modules for cap in m.capabilities}),
        }

    def get_pillar_summary(self) -> Dict[str, Any]:
        """Get a summary of all Underverse modules organized by pillar.

        Returns:
            Dictionary keyed by pillar value with module summaries
        """
        summary: Dict[str, Any] = {}
        for pillar in Pillar:
            modules = self.get_by_pillar(pillar)
            summary[pillar.value] = {
                "display_name": pillar.display_name,
                "accent_color": pillar.accent_color,
                "prime_id": pillar.prime_id,
                "total_modules": len(modules),
                "active_modules": sum(
                    1
                    for m in modules
                    if m.status
                    in (
                        UnderverseModuleStatus.ACTIVE,
                        UnderverseModuleStatus.IDLE,
                        UnderverseModuleStatus.BUSY,
                    )
                ),
                "module_ids": [m.id for m in modules],
            }
        return summary

    def get_capabilities_index(self) -> Dict[str, List[str]]:
        """Get an index of capabilities to module IDs.

        Returns:
            Dictionary mapping capability names to lists of module IDs
        """
        index: Dict[str, List[str]] = {}
        for module in self._modules.values():
            for cap in module.capabilities:
                if cap not in index:
                    index[cap] = []
                index[cap].append(module.id)
        return index

    # ── Watchers ──────────────────────────────────────────────────────────

    def add_watcher(self, callback: Callable) -> None:
        """Register a callback for registry change events.

        Args:
            callback: Function to call with (event_type, module_id) arguments
        """
        self._watchers.append(callback)

    def _notify_watchers(self, event: str, module_id: str) -> None:
        """Notify all watchers of a registry change."""
        for watcher in self._watchers:
            try:
                watcher(event, module_id)
            except Exception as e:
                logger.warning("Underverse watcher error: %s", str(e)[:200])

    # ── Statistics ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get Underverse Registry statistics."""
        return {
            **self._stats,
            "total_modules": len(self._modules),
            "active_modules": sum(
                1
                for m in self._modules.values()
                if m.status
                in (
                    UnderverseModuleStatus.ACTIVE,
                    UnderverseModuleStatus.IDLE,
                    UnderverseModuleStatus.BUSY,
                )
            ),
            "pillars_represented": len({m.pillar for m in self._modules.values() if m.pillar}),
            "dimensionals_with_modules": len(
                {m.parent_dimensional for m in self._modules.values() if m.parent_dimensional}
            ),
            "total_capabilities": len(self.get_capabilities_index()),
        }


# ── Module-level Singleton ────────────────────────────────────────────────

_underverse_registry: Optional[UnderverseRegistry] = None


def get_underverse_registry() -> UnderverseRegistry:
    """Get or create the Underverse Registry singleton."""
    global _underverse_registry
    if _underverse_registry is None:
        _underverse_registry = UnderverseRegistry()
        _register_default_underverse_modules(_underverse_registry)
    return _underverse_registry


def _register_default_underverse_modules(registry: UnderverseRegistry) -> None:
    """Register the built-in Underverse modules.

    These are the default per-app nanoservices that ship with the
    Infinity Ecosystem. Each is organized under its parent Dimensional's
    service and inherits the pillar and tier associations.
    """
    defaults = [
        # ── Under Gateway Dimensional ────────────────────────────────────
        UnderverseModule(
            id="cache_manager",
            name="Cache Manager",
            description="Manages the gateway aggregation cache with TTL and invalidation",
            parent_dimensional="gateway",
            capabilities=["caching", "invalidation", "ttl_management"],
        ),
        UnderverseModule(
            id="circuit_monitor",
            name="Circuit Breaker Monitor",
            description="Monitors upstream worker circuit breaker states and health",
            parent_dimensional="gateway",
            capabilities=["circuit_breaker", "health_monitor", "upstream_check"],
        ),
        # ── Under Sentinel Station Dimensional ───────────────────────────
        UnderverseModule(
            id="event_persister",
            name="Event Persister",
            description="Persists Sentinel Station events to SQLite for audit trail",
            parent_dimensional="sentinel_station",
            capabilities=["persistence", "audit", "sqlite"],
        ),
        UnderverseModule(
            id="channel_manager",
            name="Channel Manager",
            description="Manages Sentinel Station channel configuration and subscriptions",
            parent_dimensional="sentinel_station",
            capabilities=["channels", "subscription", "configuration"],
        ),
        # ── Under Infinity Auth Dimensional ──────────────────────────────
        UnderverseModule(
            id="jwt_validator",
            name="JWT Validator",
            description="Validates and decodes JWT tokens for authentication",
            parent_dimensional="infinity_auth",
            capabilities=["jwt", "validation", "token_decode"],
        ),
        UnderverseModule(
            id="oauth2_handler",
            name="OAuth2 Handler",
            description="Handles OAuth2 authentication flows and token exchange",
            parent_dimensional="infinity_auth",
            capabilities=["oauth2", "token_exchange", "flow_handler"],
        ),
        # ── Under Vault Dimensional ──────────────────────────────────────
        UnderverseModule(
            id="secret_encryptor",
            name="Secret Encryptor",
            description="Encrypts and decrypts secrets stored in the vault",
            parent_dimensional="vault",
            capabilities=["encryption", "decryption", "key_management"],
        ),
        UnderverseModule(
            id="audit_recorder",
            name="Audit Recorder",
            description="Records security audit entries for vault access events",
            parent_dimensional="vault",
            capabilities=["audit", "recording", "compliance"],
        ),
        # ── Under Topology Dimensional ───────────────────────────────────
        UnderverseModule(
            id="node_tracker",
            name="Node Tracker",
            description="Tracks and manages topology node registration and health",
            parent_dimensional="topology",
            capabilities=["node_tracking", "health_check", "registration"],
        ),
        UnderverseModule(
            id="mode_switcher",
            name="Mode Switcher",
            description="Handles topology mode switching (mesh, star, ring, hybrid)",
            parent_dimensional="topology",
            capabilities=["mode_switching", "topology_config", "mesh_config"],
        ),
        # ── Under Model Router Dimensional ───────────────────────────────
        UnderverseModule(
            id="model_registry",
            name="Model Registry",
            description="Registers and manages AI models available for routing",
            parent_dimensional="model_router",
            capabilities=["model_registration", "model_discovery", "model_metadata"],
        ),
        UnderverseModule(
            id="inference_dispatcher",
            name="Inference Dispatcher",
            description="Dispatches inference requests to appropriate model endpoints",
            parent_dimensional="model_router",
            capabilities=["inference", "dispatch", "load_balancing"],
        ),
        # ── Under Workflow Dimensional ───────────────────────────────────
        UnderverseModule(
            id="step_executor",
            name="Step Executor",
            description="Executes individual workflow steps with dependency resolution",
            parent_dimensional="workflow",
            capabilities=["step_execution", "dependency_resolution", "parallel_steps"],
        ),
        UnderverseModule(
            id="workflow_monitor",
            name="Workflow Monitor",
            description="Monitors workflow execution progress and status",
            parent_dimensional="workflow",
            capabilities=["monitoring", "progress_tracking", "status_reporting"],
        ),
        # ── Under DeepAgents Dimensional ─────────────────────────────────
        UnderverseModule(
            id="skill_engine",
            name="Skill Engine",
            description="Manages and dispatches agent skills for task execution",
            parent_dimensional="deepagents",
            capabilities=["skills", "dispatch", "task_assignment"],
        ),
        UnderverseModule(
            id="agent_lifecycle",
            name="Agent Lifecycle Manager",
            description="Manages the full lifecycle of AI agents from creation to retirement",
            parent_dimensional="deepagents",
            capabilities=["lifecycle", "creation", "retirement", "state_management"],
        ),
        # ── Under Ledger Dimensional ─────────────────────────────────────
        UnderverseModule(
            id="chain_verifier",
            name="Chain Verifier",
            description="Verifies the integrity of the immutable audit chain",
            parent_dimensional="ledger",
            capabilities=["verification", "chain_integrity", "hash_validation"],
        ),
        # ── Under Infinity Portal Dimensional ────────────────────────────
        UnderverseModule(
            id="gate_router",
            name="Gate Router",
            description="Routes authenticated users to their appropriate Infinity location",
            parent_dimensional="infinity_portal",
            capabilities=["routing", "gate", "role_based_redirect"],
            tier=Tier.HUMAN,
        ),
        UnderverseModule(
            id="session_manager",
            name="Session Manager",
            description="Manages user sessions and authentication state",
            parent_dimensional="infinity_portal",
            capabilities=["sessions", "authentication_state", "token_refresh"],
            tier=Tier.HUMAN,
        ),
        # ── Under Infinity-One Dimensional ───────────────────────────────
        UnderverseModule(
            id="identity_resolver",
            name="Identity Resolver",
            description="Resolves and manages user identity across the Infinity Ecosystem",
            parent_dimensional="infinity_one",
            capabilities=["identity", "resolution", "user_profiles"],
            tier=Tier.HUMAN,
        ),
        # ── Under Infinity-Admin Dimensional ─────────────────────────────
        UnderverseModule(
            id="config_manager",
            name="Configuration Manager",
            description="Manages system configuration and environment settings",
            parent_dimensional="infinity_admin",
            capabilities=["configuration", "environment", "settings"],
            tier=Tier.ORCHESTRATOR,
        ),
    ]

    for module in defaults:
        registry.register_module(module)
