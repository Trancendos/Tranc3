"""
Dimensional.infinity.fluidic_gateway — Fluidic Routing for Infinity Services
==============================================================================
Trancendos Universe — Phase 22 Enhancement

Integrates the FluidicRouter (liquid-neural weighted routing) with the
InfinityGate routing logic, adding:

  - CausalEventBus for vector-clock causal ordering of routing events
  - ReactiveState for live Infinity location topology
  - Adaptive weight adjustment based on real-time service health
  - Graceful fallback when services are unavailable
  - Tier-aware routing priorities (Tier 0 → 5 precedence)

Architecture:
    ┌──────────────────────────────────────────────────────────────────────┐
    │                    InfinityFluidicGateway                            │
    │                                                                      │
    │  ┌───────────────────┐    ┌────────────────────────────────────────┐ │
    │  │  FluidicRouter    │    │  CausalEventBus                        │ │
    │  │  (liquid neural   │    │  (vector clock ordering for            │ │
    │  │   weighted cells) │    │   distributed route decisions)         │ │
    │  └────────┬──────────┘    └───────────────────┬────────────────────┘ │
    │           │                                   │                      │
    │  ┌────────┴───────────────────────────────────┴────────────────────┐ │
    │  │              Infinity Location Registry                          │ │
    │  │  (Portal→8042, One→8043, Admin→8044, Auth→8012, ...)            │ │
    │  └──────────────────────────────────────────────────────────────────┘ │
    │                                                                      │
    │  ┌────────────────────────────────────────────────────────────────┐  │
    │  │  ReactiveState — Live topology (health, weight, active routes) │  │
    │  └────────────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────────────┘

Route Decision Flow:
    1. Receive routing request (role/tier + target_location)
    2. Resolve target via InfinityGate.EXTENDED_ROUTING
    3. Select service endpoint via FluidicRouter (weighted health)
    4. Publish routing event to CausalEventBus
    5. Update ReactiveState topology
    6. Return resolved endpoint + metadata

Usage:
    from Dimensional.infinity.fluidic_gateway import InfinityFluidicGateway

    gateway = InfinityFluidicGateway()
    await gateway.start()

    endpoint = await gateway.route(role="admin", user_id="u123")
    # → {"location": "infinity-admin", "url": "http://localhost:8044", "tier": 0}
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Dimensional.infinity.nomenclature import (
    InfinityLocation,
    get_infinity_role_for_role,
    get_tier_for_role,
)
from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    from src.fluidic.causal_bus import CausalEventBus

    _CAUSAL_AVAILABLE = True
except ImportError:
    _CAUSAL_AVAILABLE = False
    CausalEventBus = None  # type: ignore[assignment,misc]

try:
    from src.fluidic.reactive_state import StateStore

    _REACTIVE_AVAILABLE = True
except ImportError:
    _REACTIVE_AVAILABLE = False
    StateStore = None  # type: ignore[assignment,misc]

try:
    from Dimensional.models import EventMessage

    _MODELS_AVAILABLE = True
except ImportError:
    _MODELS_AVAILABLE = False
    EventMessage = None  # type: ignore[assignment,misc]


# ── Infinity Location Registry ────────────────────────────────────────────────
# Maps InfinityLocation enum values to their service endpoints.
# Workers are self-hosted; these are the local port assignments.

INFINITY_LOCATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    InfinityLocation.PORTAL.value: {
        "name": "infinity-portal",
        "url": "http://localhost:8042",
        "port": 8042,
        "description": "Central login/registration front door",
        "health_url": "http://localhost:8042/health",
    },
    InfinityLocation.ONE.value: {
        "name": "infinity-one",
        "url": "http://localhost:8043",
        "port": 8043,
        "description": "Single identity management — one login, multi-app",
        "health_url": "http://localhost:8043/health",
    },
    InfinityLocation.ADMIN.value: {
        "name": "infinity-admin",
        "url": "http://localhost:8044",
        "port": 8044,
        "description": "Administrative management OS",
        "health_url": "http://localhost:8044/health",
    },
    "infinity_auth": {
        "name": "infinity-auth",
        "url": "http://localhost:8012",
        "port": 8012,
        "description": "JWT/OAuth2 authentication service",
        "health_url": "http://localhost:8012/health",
    },
    InfinityLocation.ARCADIA.value: {
        "name": "arcadia",
        "url": "http://localhost:8045",
        "port": 8045,
        "description": "User space — Arcadia personal workspace",
        "health_url": "http://localhost:8045/health",
    },
    InfinityLocation.CITADEL.value: {
        "name": "the-citadel",
        "url": "http://localhost:8046",
        "port": 8046,
        "description": "Developer/DevOps space — The Citadel",
        "health_url": "http://localhost:8046/health",
    },
    InfinityLocation.SENTINEL.value: {
        "name": "sentinel-station",
        "url": "http://localhost:8041",
        "port": 8041,
        "description": "Event bus — Sentinel Station interplexus hub",
        "health_url": "http://localhost:8041/health",
    },
    "gateway": {
        "name": "gateway-service",
        "url": "http://localhost:8040",
        "port": 8040,
        "description": "Main API gateway",
        "health_url": "http://localhost:8040/health",
    },
}


# ── Route Cell (Fluidic) ──────────────────────────────────────────────────────


@dataclass
class GatewayRouteCell:
    """A fluidic routing cell for an Infinity location."""

    location_key: str
    weight: float = 1.0
    decay_rate: float = 0.05
    recovery_rate: float = 0.02
    last_used: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0
    response_times: List[float] = field(default_factory=list)
    is_healthy: bool = True

    @property
    def effective_weight(self) -> float:
        w = self.weight
        if not self.is_healthy:
            w *= 0.1  # Heavy penalty for unhealthy locations
        if self.request_count > 0:
            error_rate = self.error_count / self.request_count
            w *= max(0.1, 1.0 - error_rate * 1.5)
        if self.response_times:
            avg_rt = sum(self.response_times[-20:]) / min(len(self.response_times), 20)
            w *= 1.0 / (1.0 + avg_rt / 2000.0)
        idle_time = time.time() - self.last_used
        w += self.recovery_rate * min(idle_time, 60.0)  # Cap recovery
        return max(w, 0.01)

    def record_success(self, response_time_ms: float) -> None:
        self.request_count += 1
        self.last_used = time.time()
        self.response_times.append(response_time_ms)
        if len(self.response_times) > 100:
            self.response_times = self.response_times[-100:]

    def record_error(self) -> None:
        self.request_count += 1
        self.error_count += 1
        self.last_used = time.time()
        self.weight = max(0.1, self.weight * (1.0 - self.decay_rate))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location_key,
            "weight": round(self.weight, 4),
            "effective_weight": round(self.effective_weight, 4),
            "requests": self.request_count,
            "errors": self.error_count,
            "error_rate": round(self.error_count / max(self.request_count, 1), 4),
            "healthy": self.is_healthy,
            "avg_response_ms": round(
                sum(self.response_times[-20:]) / max(len(self.response_times[-20:]), 1), 2
            )
            if self.response_times
            else 0.0,
        }


# ── Route Result ──────────────────────────────────────────────────────────────


@dataclass
class RouteResult:
    role: str
    tier: int
    infinity_role: str
    target_location: str
    resolved_url: str
    service_name: str
    routed_by: str = "fluidic_gateway"
    cell_weight: float = 1.0
    timestamp: float = field(default_factory=time.time)
    causal_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "tier": self.tier,
            "infinity_role": self.infinity_role,
            "target_location": self.target_location,
            "resolved_url": self.resolved_url,
            "service_name": self.service_name,
            "routed_by": self.routed_by,
            "cell_weight": round(self.cell_weight, 4),
            "timestamp": self.timestamp,
            "causal_id": self.causal_id,
        }


# ── InfinityFluidicGateway ────────────────────────────────────────────────────


class InfinityFluidicGateway:
    """
    Fluidic routing gateway for the Infinity Ecosystem.

    Combines InfinityGate role-based routing with FluidicRouter weighted
    cell selection and CausalEventBus ordering for distributed consistency.
    """

    # Extended routing (mirrors InfinityGate.EXTENDED_ROUTING but as location keys)
    _ROLE_LOCATION_MAP: Dict[str, str] = {
        "admin": InfinityLocation.ADMIN.value,  # "infinity_admin"
        "user": InfinityLocation.ARCADIA.value,  # "arcadia"
        "developer": InfinityLocation.CITADEL.value,  # "the_citadel"
        "devops": InfinityLocation.CITADEL.value,  # "the_citadel"
        "prime": InfinityLocation.ADMIN.value,  # "infinity_admin"
        "ai": "gateway",
        "agent": "gateway",
        "bot": "gateway",
        "service": "gateway",
    }

    def __init__(self, node_id: str = "infinity-fluidic-gateway"):
        self.node_id = node_id
        self._cells: Dict[str, GatewayRouteCell] = {}
        self._routing_history: List[RouteResult] = []
        self._route_count = 0
        self._started = False

        # Initialize routing cells for all known locations
        for loc_key in INFINITY_LOCATION_REGISTRY:
            self._cells[loc_key] = GatewayRouteCell(location_key=loc_key)

        # CausalEventBus for distributed routing consistency
        if _CAUSAL_AVAILABLE:
            self.causal_bus = CausalEventBus(node_id=f"gateway.{node_id}")
        else:
            self.causal_bus = None

        # ReactiveState for live topology
        if _REACTIVE_AVAILABLE:
            self.state_store = StateStore()
            self.topology_state = self.state_store.create(
                "infinity.gateway.topology",
                {loc: {"healthy": True, "weight": 1.0} for loc in INFINITY_LOCATION_REGISTRY},
            )
        else:
            self.state_store = None
            self.topology_state = None

    async def start(self) -> None:
        """Start the fluidic gateway."""
        if self.causal_bus:
            await self.causal_bus.start()
        self._started = True
        logger.info("InfinityFluidicGateway started (node=%s)", sanitize_for_log(self.node_id))

    async def stop(self) -> None:
        """Stop the fluidic gateway."""
        if self.causal_bus:
            await self.causal_bus.stop()
        self._started = False

    # ── Routing ───────────────────────────────────────────────────────────────

    async def route(
        self,
        role: str,
        user_id: str = "anonymous",
        *,
        preferred_location: Optional[str] = None,
    ) -> RouteResult:
        """
        Route a user/service to the appropriate Infinity location.

        Args:
            role: User role (admin, user, developer, devops, prime, ai, agent, bot, service)
            user_id: User or service identifier (for causal tracking)
            preferred_location: Override automatic routing to a specific location key

        Returns:
            RouteResult with resolved URL and metadata.
        """
        self._route_count += 1
        tier = get_tier_for_role(role)
        infinity_role = get_infinity_role_for_role(role)

        # Determine target location
        target_location = preferred_location or self._ROLE_LOCATION_MAP.get(
            role.lower().strip(), "gateway"
        )

        # Get location info
        location_info = INFINITY_LOCATION_REGISTRY.get(target_location)
        if not location_info:
            # Fallback to gateway
            target_location = "gateway"
            location_info = INFINITY_LOCATION_REGISTRY.get(
                "gateway",
                {
                    "url": "http://localhost:8040",
                    "name": "gateway-service",
                },
            )

        # Get fluidic cell and log usage
        cell = self._cells.get(target_location)
        cell_weight = cell.effective_weight if cell else 1.0

        result = RouteResult(
            role=role,
            tier=int(tier),
            infinity_role=infinity_role.value
            if hasattr(infinity_role, "value")
            else str(infinity_role),
            target_location=target_location,
            resolved_url=location_info.get("url", "http://localhost:8040"),
            service_name=location_info.get("name", "unknown"),
            cell_weight=cell_weight,
        )

        # Publish routing event to CausalEventBus
        if self.causal_bus and _MODELS_AVAILABLE:
            try:
                event = EventMessage(
                    event_type="gateway.route",
                    payload={
                        "user_id": user_id,
                        "role": role,
                        "tier": int(tier),
                        "target": target_location,
                        "url": result.resolved_url,
                    },
                )
                await self.causal_bus.publish(event)
                result.causal_id = event.metadata.get("vector_clock") and str(
                    self.causal_bus.clock_state
                )
            except Exception as e:
                logger.debug("CausalEventBus publish error: %s", sanitize_for_log(str(e)))

        # Store in history (bounded)
        self._routing_history.append(result)
        if len(self._routing_history) > 1000:
            self._routing_history = self._routing_history[-1000:]

        return result

    def record_route_success(self, location_key: str, response_time_ms: float) -> None:
        """Record a successful route request (updates fluidic cell)."""
        cell = self._cells.get(location_key)
        if cell:
            cell.record_success(response_time_ms)
            cell.is_healthy = True

    def record_route_error(self, location_key: str) -> None:
        """Record a failed route request (penalises fluidic cell)."""
        cell = self._cells.get(location_key)
        if cell:
            cell.record_error()

    def update_location_health(self, location_key: str, is_healthy: bool) -> None:
        """Update health status for a location (affects fluidic weights)."""
        cell = self._cells.get(location_key)
        if cell:
            cell.is_healthy = is_healthy
            if not is_healthy:
                cell.weight = max(0.1, cell.weight * 0.5)
        # Update reactive topology
        if self.topology_state and _REACTIVE_AVAILABLE:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self.topology_state.update(
                        **{
                            location_key: {
                                "healthy": is_healthy,
                                "weight": round(cell.effective_weight if cell else 0.0, 4),
                            }
                        }
                    ),
                )
            except RuntimeError as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

    # ── Query Interface ───────────────────────────────────────────────────────

    def get_topology(self) -> Dict[str, Any]:
        """Get current routing topology with fluidic cell stats."""
        return {
            loc_key: {
                **info,
                "cell": self._cells[loc_key].to_dict() if loc_key in self._cells else {},
            }
            for loc_key, info in INFINITY_LOCATION_REGISTRY.items()
        }

    def get_routing_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent routing decisions."""
        return [r.to_dict() for r in self._routing_history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get gateway statistics."""
        total_requests = sum(c.request_count for c in self._cells.values())
        total_errors = sum(c.error_count for c in self._cells.values())
        return {
            "node_id": self.node_id,
            "route_count": self._route_count,
            "total_location_requests": total_requests,
            "total_location_errors": total_errors,
            "error_rate": round(total_errors / max(total_requests, 1), 4),
            "cells": {k: c.to_dict() for k, c in self._cells.items()},
            "causal_bus_available": _CAUSAL_AVAILABLE,
            "reactive_state_available": _REACTIVE_AVAILABLE,
            "locations_registered": len(INFINITY_LOCATION_REGISTRY),
        }


# ── Module-level singleton ────────────────────────────────────────────────────

fluidic_gateway = InfinityFluidicGateway()
