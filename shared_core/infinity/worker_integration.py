"""
shared_core.infinity.worker_integration — Smart Worker Integration Helpers
===========================================================================
Tranc3 Phase 22.6 — Drop-in integration utilities for all Infinity workers.

Provides a single `InfinityWorkerKit` that bundles every smart adaptive
layer so each worker only needs one import to gain:

  • InfinityHealthOrchestrator  — pulse + anomaly + repair + config tuner
  • ProactiveDefenseLayer       — IP blocks + threat prediction + incident mgmt
  • InfinityFluidicGateway      — liquid-neural weighted role-based routing
  • Prometheus /metrics endpoint — auto-mounted on the FastAPI app
  • /health/smart endpoint      — richer health with predictive trajectory
  • /defense/stats endpoint     — live defense stats
  • /routing/topology endpoint  — live fluidic routing topology
  • Sentinel bridge             — health + defense events → SentinelStation

Usage::

    from shared_core.infinity.worker_integration import InfinityWorkerKit

    kit = InfinityWorkerKit("infinity-portal")

    # Inside lifespan startup:
    await kit.startup(app, sentinel=sentinel)

    # Inside lifespan shutdown:
    await kit.shutdown()

    # In request handlers:
    result = await kit.defense.evaluate_request(request_dict)
    route  = await kit.gateway.route("admin", user_id)
    kit.health.record_metric("sessions_active", n)
    kit.health.record_request(latency_ms)

    # Register pulse daemons:
    kit.health.register_daemon("session_cleaner", baseline_interval=300.0)
    if kit.health.should_fire("session_cleaner"):
        await clean_sessions()
        kit.health.record_fire("session_cleaner")
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------

try:
    from shared_core.infinity.adaptive_intelligence import (
        InfinityHealthOrchestrator,  # noqa: F401
        create_orchestrator,
        SUBSYSTEM_AVAILABILITY,
    )

    _ORCHESTRATOR_AVAILABLE = True
except ImportError:
    _ORCHESTRATOR_AVAILABLE = False
    SUBSYSTEM_AVAILABILITY: dict = {}

try:
    from shared_core.infinity.proactive_defense import ProactiveDefenseLayer

    _DEFENSE_AVAILABLE = True
except ImportError:
    _DEFENSE_AVAILABLE = False

try:
    from shared_core.infinity.fluidic_gateway import InfinityFluidicGateway

    _GATEWAY_AVAILABLE = True
except ImportError:
    _GATEWAY_AVAILABLE = False


# ---------------------------------------------------------------------------
# InfinityWorkerKit
# ---------------------------------------------------------------------------


class InfinityWorkerKit:
    """Bundles all smart adaptive layers for an Infinity worker.

    Drop-in: instantiate at module level, call startup() in lifespan,
    shutdown() on exit. All layers degrade gracefully if unavailable.
    """

    def __init__(
        self,
        service_name: str,
        *,
        sentinel_publish_fn: Optional[Callable] = None,
        defense_threshold: int = 10,
        defense_window_seconds: int = 300,
        defense_block_seconds: int = 900,
    ) -> None:
        self.service_name = service_name
        self._sentinel_publish_fn = sentinel_publish_fn
        self._started = False
        self._start_time = time.time()

        # Health Orchestrator
        if _ORCHESTRATOR_AVAILABLE:
            self.health: Any = create_orchestrator(
                service_name=service_name,
                sentinel_publish_fn=sentinel_publish_fn,
            )
        else:
            self.health = _NullHealthOrchestrator(service_name)

        # Proactive Defense Layer
        if _DEFENSE_AVAILABLE:
            self.defense: Any = ProactiveDefenseLayer(
                service_name=service_name,
                violation_threshold=defense_threshold,
                violation_window_seconds=defense_window_seconds,
                block_duration_seconds=defense_block_seconds,
            )
        else:
            self.defense = _NullDefenseLayer()

        # Fluidic Gateway
        if _GATEWAY_AVAILABLE:
            self.gateway: Any = InfinityFluidicGateway(node_id=f"{service_name}-gateway")
        else:
            self.gateway = _NullFluidicGateway()

        logger.info(
            "InfinityWorkerKit[%s] created — health=%s defense=%s gateway=%s",
            service_name,
            _ORCHESTRATOR_AVAILABLE,
            _DEFENSE_AVAILABLE,
            _GATEWAY_AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self, app: Any, sentinel: Any = None) -> None:
        """Start all layers and mount smart endpoints on the FastAPI app."""
        if self._started:
            return

        # Wire in sentinel publish function if provided at startup
        if sentinel is not None and self._sentinel_publish_fn is None:
            self._sentinel_publish_fn = _make_sentinel_fn(sentinel)
            if _ORCHESTRATOR_AVAILABLE:
                self.health._sentinel_publish_fn = self._sentinel_publish_fn

        # Start health orchestrator
        try:
            await self.health.start(app)
        except Exception as exc:
            logger.warning("HealthOrchestrator start error: %s", exc)

        # Start fluidic gateway
        try:
            await self.gateway.start()
        except Exception as exc:
            logger.warning("FluidicGateway start error: %s", exc)

        # Mount smart endpoints
        if app is not None:
            self._mount_endpoints(app)

        self._started = True
        logger.info("InfinityWorkerKit[%s] started", self.service_name)

    async def shutdown(self) -> None:
        """Stop all layers cleanly."""
        try:
            await self.health.stop()
        except Exception:
            pass
        try:
            await self.gateway.stop()
        except Exception:
            pass
        self._started = False
        logger.info("InfinityWorkerKit[%s] stopped", self.service_name)

    # ------------------------------------------------------------------
    # Smart Endpoint Mounting
    # ------------------------------------------------------------------

    def _mount_endpoints(self, app: Any) -> None:
        """Mount Prometheus /metrics, /health/smart, /defense/stats, /routing/topology."""
        kit = self

        @app.get("/metrics", include_in_schema=False)
        async def prometheus_metrics():
            """Prometheus-compatible metrics endpoint."""
            from fastapi.responses import PlainTextResponse

            metrics_text = kit.health.get_prometheus_metrics()
            return PlainTextResponse(content=metrics_text, media_type="text/plain; version=0.0.4")

        @app.get("/health/smart")
        async def smart_health():
            """Enhanced health endpoint with predictive trajectory, anomaly status, pulse stats."""
            summary = kit.health.get_health_summary()
            pulse_stats = kit.health.get_pulse_stats()
            defense_stats = kit.defense.get_stats()
            topology = kit.gateway.get_topology()
            return {
                "service": kit.service_name,
                "uptime": time.time() - kit._start_time,
                "health": summary,
                "pulse": pulse_stats,
                "defense": defense_stats,
                "topology": {
                    "active_cells": len(topology),
                    "locations": list(topology.keys()),
                },
                "subsystems": SUBSYSTEM_AVAILABILITY,
            }

        @app.get("/defense/stats")
        async def defense_stats():
            """Live proactive defense statistics."""
            return kit.defense.get_stats()

        @app.get("/defense/blocked-ips")
        async def defense_blocked_ips():
            """Currently blocked IP addresses."""
            return {"blocked_ips": kit.defense.get_blocked_ips()}

        @app.get("/routing/topology")
        async def routing_topology():
            """Live fluidic routing topology with cell weights."""
            topology = kit.gateway.get_topology()
            stats = kit.gateway.get_stats()
            return {
                "node_id": stats.get("node_id", kit.service_name),
                "cells": topology,
                "stats": stats,
            }

        @app.get("/routing/history")
        async def routing_history():
            """Recent routing decisions."""
            return {"history": kit.gateway.get_routing_history()}

        logger.debug("InfinityWorkerKit[%s]: smart endpoints mounted", self.service_name)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_kit_stats(self) -> dict:
        return {
            "service": self.service_name,
            "started": self._started,
            "uptime": time.time() - self._start_time,
            "health": self.health.get_health_summary(),
            "defense": self.defense.get_stats(),
            "gateway": self.gateway.get_stats(),
            "subsystems": SUBSYSTEM_AVAILABILITY,
        }


# ---------------------------------------------------------------------------
# Null / fallback implementations (when subsystems unavailable)
# ---------------------------------------------------------------------------


class _NullHealthOrchestrator:
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self._start_time = time.time()

    async def start(self, app: Any) -> None:
        pass

    async def stop(self) -> None:
        pass

    def register_daemon(self, name: str, **kw) -> None:
        pass

    def should_fire(self, name: str) -> bool:
        return False

    def record_fire(self, name: str) -> None:
        pass

    def record_metric(self, name: str, value: float) -> None:
        pass

    def record_request(self, latency_ms: float = 0.0, error: bool = False) -> None:
        pass

    def update_health(self, score: float) -> None:
        pass

    def get_health_summary(self) -> dict:
        return {"service": self.service_name, "score": 1.0, "tier": "EXCELLENT", "subsystems": {}}

    def get_prometheus_metrics(self) -> str:
        return f'# HELP up Service is up\n# TYPE up gauge\nup{{service="{self.service_name}"}} 1\n'

    def get_pulse_stats(self) -> dict:
        return {}

    def get_defense_incidents(self) -> list:
        return []


class _NullDefenseLayer:
    async def evaluate_request(self, request_dict: dict) -> Any:
        from dataclasses import dataclass

        @dataclass
        class _R:
            allowed: bool = True
            threat_score: float = 0.0
            reason: str = "passthrough"

        return _R()

    def unblock_ip(self, ip: str) -> None:
        pass

    def get_blocked_ips(self) -> list:
        return []

    def get_stats(self) -> dict:
        return {"service": "null", "evaluations": 0}


class _NullFluidicGateway:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def route(self, role: str, user_id: str) -> Any:
        from dataclasses import dataclass

        @dataclass
        class _R:
            target_location: str = "arcadia"
            resolved_url: str = "http://localhost:8042"
            routed: bool = True

        return _R()

    def record_route_success(self, loc: str, ms: float) -> None:
        pass

    def record_route_error(self, loc: str) -> None:
        pass

    def update_location_health(self, loc: str, h: bool) -> None:
        pass

    def get_topology(self) -> dict:
        return {}

    def get_routing_history(self) -> list:
        return []

    def get_stats(self) -> dict:
        return {"route_count": 0}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_sentinel_fn(sentinel: Any) -> Callable:
    """Create a publish callback from a SentinelStation instance."""

    async def _publish(channel: str, event_type: str, payload: dict) -> None:
        try:
            from shared_core.infinity.sentinel_station import SentinelEvent, SentinelChannel

            ch = SentinelChannel(channel) if isinstance(channel, str) else channel
            await sentinel.publish(
                SentinelEvent(
                    channel=ch,
                    event_type=event_type,
                    source="worker_kit",
                    payload=payload,
                )
            )
        except Exception as exc:
            logger.debug("Sentinel publish error: %s", exc)

    return _publish
