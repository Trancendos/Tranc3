"""
Dimensional.architecture.proactive_wiring — Unified Integration Wiring for Tranc3.

The ProactiveSystemBootstrap wires all intelligent subsystems into the
ProactiveOrchestrator, creating a cohesive, self-healing, adaptive platform.
It establishes bidirectional communication channels between every subsystem
and the central orchestrator, enabling:

    - Health metric flow: Each subsystem reports its health to the orchestrator
    - Action dispatch: The orchestrator sends corrective actions back to subsystems
    - Event propagation: All subsystem events flow through the EventBus
    - Adaptive pulsing: System health drives daemon interval adjustment
    - Zero-cost modulation: Storage usage triggers proactive tier migration
    - Auto-configuration: Environment changes trigger profile-based reconfiguration
    - Predictive scaling: Load patterns trigger proactive resource scaling

Universal ID Taxonomy:
    PID (Product/Location ID)  — identifies locations/products in the 8 pillars
    AID (AI ID)                — identifies AI entities (e.g., tAImra Lead AI)
    SID (Service/Agent ID)     — identifies services and agents
    NID (Nano-ID/Bot ID)       — identifies nanoservice bots

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                   ProactiveSystemBootstrap                    │
    │                                                              │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
    │  │ EventBus │  │ Sentinel │  │ Defense  │  │ Foresight│    │
    │  │  Bridge  │  │  Bridge  │  │  Bridge  │  │  Bridge  │    │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
    │       │              │             │              │          │
    │  ┌────┴──────────────┴─────────────┴──────────────┴────┐    │
    │  │              ProactiveOrchestrator                    │    │
    │  │  (unified brain — predictive, adaptive, proactive)  │    │
    │  └────┬──────────────┬─────────────┬──────────────┬────┘    │
    │       │              │             │              │          │
    │  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐   │
    │  │ Storage  │  │ Fluidic  │  │ Enhanced │  │ Resilien-│   │
    │  │  Bridge  │  │  Router  │  │ Registry │  │   ceMgr  │   │
    │  │          │  │  Bridge  │  │  Bridge  │  │  Bridge  │   │
    │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
    │                                                              │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
    │  │ Adaptive │  │  Auto    │  │Predictive│                  │
    │  │  Pulse   │  │  Config  │  │ Scaler   │                  │
    │  │Controller│  │ Manager  │  │          │                  │
    │  └──────────┘  └──────────┘  └──────────┘                  │
    └──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wiring Status
# ---------------------------------------------------------------------------


class WiringStatus(str, Enum):
    """Status of a subsystem wiring connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class BridgeType(str, Enum):
    """Type of integration bridge."""

    EVENT_BUS = "event_bus"
    STORAGE = "storage"
    SENTINEL = "sentinel"
    DEFENSE = "defense"
    FORESIGHT = "foresight"
    ROUTING = "routing"
    REGISTRY = "registry"
    RESILIENCE = "resilience"
    PULSE = "pulse"
    CONFIG = "config"
    SCALER = "scaler"


@dataclass
class BridgeConnection:
    """Tracks the state of a single subsystem bridge connection."""

    bridge_type: BridgeType
    subsystem_name: str
    status: WiringStatus = WiringStatus.DISCONNECTED
    connected_at: Optional[float] = None
    last_activity: Optional[float] = None
    events_processed: int = 0
    actions_dispatched: int = 0
    errors: int = 0
    last_error: Optional[str] = None

    def mark_connected(self) -> None:
        self.status = WiringStatus.CONNECTED
        self.connected_at = time.time()
        self.last_activity = time.time()

    def mark_active(self) -> None:
        self.status = WiringStatus.ACTIVE
        self.last_activity = time.time()

    def mark_error(self, error: str) -> None:
        self.status = WiringStatus.ERROR
        self.errors += 1
        self.last_error = error
        self.last_activity = time.time()

    def record_event(self) -> None:
        self.events_processed += 1
        self.last_activity = time.time()
        if self.status == WiringStatus.CONNECTED:
            self.status = WiringStatus.ACTIVE

    def record_action(self) -> None:
        self.actions_dispatched += 1
        self.last_activity = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bridge_type": self.bridge_type.value,
            "subsystem_name": self.subsystem_name,
            "status": self.status.value,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "events_processed": self.events_processed,
            "actions_dispatched": self.actions_dispatched,
            "errors": self.errors,
            "last_error": self.last_error,
        }


# ---------------------------------------------------------------------------
# Proactive System Bootstrap
# ---------------------------------------------------------------------------


class ProactiveSystemBootstrap:
    """Wires all Tranc3 intelligent subsystems into the ProactiveOrchestrator.

    This is the single entry point for bootstrapping the entire intelligent
    adaptive proactive system. It:

    1. Attaches all subsystems to the ProactiveOrchestrator
    2. Subscribes to EventBus channels for bidirectional communication
    3. Registers action handlers for each subsystem
    4. Configures the AdaptivePulseController for all daemons
    5. Triggers AutoConfigManager for environment-driven configuration
    6. Connects the PredictiveAutoscaler for resource scaling
    7. Starts the orchestrator's orchestration loop

    Usage:
        bootstrap = ProactiveSystemBootstrap()
        await bootstrap.wire_all(subsystems_dict)
        await bootstrap.start()

    The subsystems_dict should contain any or all of:
        - "event_bus": EventBus instance
        - "storage": SmartStorageOrchestrator instance
        - "sentinel": Sentinel instance
        - "defense": DefenseEngine instance
        - "foresight": ForesightEngine instance
        - "router": FluidicRouter instance
        - "registry": EnhancedServiceRegistry instance
        - "resilience": ResilienceManager instance
        - "pulse": AdaptivePulseController instance (or None for auto-create)
        - "config": AutoConfigManager instance (or None for auto-create)
        - "scaler": PredictiveAutoscaler instance (or None for auto-create)
    """

    def __init__(self) -> None:
        self._bridges: Dict[BridgeType, BridgeConnection] = {}
        self._wired: bool = False
        self._started: bool = False
        self._subsystems: Dict[str, Any] = {}
        self._event_handlers: List[Callable] = []

        # Lazy imports — avoid circular dependencies
        self._orchestrator: Any = None
        self._pulse: Any = None
        self._config: Any = None
        self._scaler: Any = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_wired(self) -> bool:
        return self._wired

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def bridge_status(self) -> Dict[str, Dict[str, Any]]:
        return {bt.value: bc.to_dict() for bt, bc in self._bridges.items()}

    # ------------------------------------------------------------------
    # Core Wiring
    # ------------------------------------------------------------------

    async def wire_all(self, subsystems: Dict[str, Any]) -> None:
        """Wire all provided subsystems into the ProactiveOrchestrator.

        Args:
            subsystems: Dictionary of subsystem_name → instance.
                        Missing subsystems are gracefully skipped.
        """
        if self._wired:
            logger.warning("ProactiveSystemBootstrap already wired — skipping")
            return

        self._subsystems = subsystems
        start_time = time.time()
        logger.info("ProactiveSystemBootstrap: Beginning system wiring...")

        # Lazy-load orchestrator and auxiliary systems
        from Dimensional.architecture.adaptive_pulse import adaptive_pulse
        from Dimensional.architecture.auto_config import auto_config
        from Dimensional.architecture.proactive_orchestrator import (
            proactive_orchestrator,
        )
        from src.adaptive.predictive_scaler import predictive_scaler

        self._orchestrator = subsystems.get("orchestrator", proactive_orchestrator)
        self._pulse = subsystems.get("pulse", adaptive_pulse)
        self._config = subsystems.get("config", auto_config)
        self._scaler = subsystems.get("scaler", predictive_scaler)

        # Wire each subsystem
        await self._wire_event_bus(subsystems.get("event_bus"))
        await self._wire_storage(subsystems.get("storage"))
        await self._wire_sentinel(subsystems.get("sentinel"))
        await self._wire_defense(subsystems.get("defense"))
        await self._wire_foresight(subsystems.get("foresight"))
        await self._wire_router(subsystems.get("router"))
        await self._wire_registry(subsystems.get("registry"))
        await self._wire_resilience(subsystems.get("resilience"))

        # Wire auxiliary systems
        await self._wire_pulse_controller()
        await self._wire_auto_config()
        await self._wire_predictive_scaler()

        # Register proactive action handlers
        await self._register_action_handlers()

        # Register pulse-controlled daemons
        self._register_pulse_daemons()

        self._wired = True
        elapsed = time.time() - start_time
        active_count = sum(
            1
            for b in self._bridges.values()
            if b.status in (WiringStatus.CONNECTED, WiringStatus.ACTIVE)
        )
        logger.info(
            "ProactiveSystemBootstrap: Wiring complete — %d/%d bridges active (%.2fs)",
            active_count,
            len(self._bridges),
            elapsed,
        )

    async def start(self) -> None:
        """Start the proactive system after wiring."""
        if not self._wired:
            logger.error("ProactiveSystemBootstrap: Cannot start — not wired yet")
            return
        if self._started:
            logger.warning("ProactiveSystemBootstrap: Already started — skipping")
            return

        logger.info("ProactiveSystemBootstrap: Starting proactive system...")

        # Start the orchestrator
        await self._orchestrator.start()

        # Run auto-configuration if available
        if self._config and hasattr(self._config, "auto_configure"):
            try:
                profile = self._config.auto_configure()
                logger.info(
                    "ProactiveSystemBootstrap: Auto-configured profile: %s",
                    sanitize_for_log(str(profile)),
                )
            except Exception as e:
                logger.warning(
                    "ProactiveSystemBootstrap: Auto-configuration failed: %s",
                    sanitize_for_log(str(e)),
                )

        self._started = True
        logger.info("ProactiveSystemBootstrap: System started successfully")

    async def stop(self) -> None:
        """Stop the proactive system gracefully."""
        if not self._started:
            return

        logger.info("ProactiveSystemBootstrap: Stopping proactive system...")

        # Stop the orchestrator
        if self._orchestrator and hasattr(self._orchestrator, "stop"):
            await self._orchestrator.stop()

        # Unsubscribe all event handlers
        event_bus = self._subsystems.get("event_bus")
        if event_bus:
            for handler in self._event_handlers:
                try:
                    event_bus.unsubscribe("*", handler)
                except Exception:
                    pass

        # Mark all bridges as disconnected
        for bridge in self._bridges.values():
            bridge.status = WiringStatus.DISCONNECTED

        self._started = False
        self._wired = False
        logger.info("ProactiveSystemBootstrap: System stopped")

    # ------------------------------------------------------------------
    # Subsystem Wiring Methods
    # ------------------------------------------------------------------

    async def _wire_event_bus(self, event_bus: Any) -> None:
        """Wire EventBus for bidirectional nanoservice communication.

        The EventBus is the nervous system of the platform. All subsystem
        events flow through it, and the ProactiveOrchestrator both publishes
        and subscribes to relevant event channels.
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.EVENT_BUS,
            subsystem_name="EventBus",
        )

        if event_bus is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.EVENT_BUS] = bridge
            logger.info("ProactiveSystemBootstrap: EventBus not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach EventBus to orchestrator
            self._orchestrator.attach_event_bus(event_bus)

            # Subscribe orchestrator to all events (wildcard)
            async def _on_proactive_event(event: Any) -> None:
                """Route EventBus events into the orchestrator."""
                bridge.record_event()
                try:
                    event_type = getattr(event, "event_type", "unknown")
                    source = getattr(event, "source", "unknown")
                    data = getattr(event, "data", {})

                    # Route specific event types to orchestrator actions
                    if event_type.startswith("storage."):
                        await self._handle_storage_event(event_type, source, data)
                    elif event_type.startswith("security."):
                        await self._handle_security_event(event_type, source, data)
                    elif event_type.startswith("service."):
                        await self._handle_service_event(event_type, source, data)
                    elif event_type.startswith("circuit."):
                        await self._handle_circuit_event(event_type, source, data)
                    elif event_type.startswith("health."):
                        await self._handle_health_event(event_type, source, data)
                except Exception as e:
                    bridge.mark_error(str(e))
                    logger.error(
                        "ProactiveSystemBootstrap: EventBus handler error: %s",
                        sanitize_for_log(str(e)),
                    )

            event_bus.subscribe("*", _on_proactive_event)
            self._event_handlers.append(_on_proactive_event)

            # Publish wiring event
            from Dimensional.models import EventMessage

            await event_bus.publish(
                EventMessage(
                    event_type="proactive.system_wired",
                    source="ProactiveSystemBootstrap",
                    data={"component": "event_bus", "status": "connected"},
                )
            )

            bridge.mark_connected()
            self._bridges[BridgeType.EVENT_BUS] = bridge
            logger.info("ProactiveSystemBootstrap: EventBus bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.EVENT_BUS] = bridge
            logger.error(
                "ProactiveSystemBootstrap: EventBus wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_storage(self, storage: Any) -> None:
        """Wire SmartStorageOrchestrator for zero-cost storage modulation.

        The storage bridge enables the ProactiveOrchestrator to:
        - Monitor tier capacity and health in real time
        - Proactively migrate data before free-tier limits are reached
        - Auto-heal storage failures by failing over to alternate tiers
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.STORAGE,
            subsystem_name="SmartStorageOrchestrator",
        )

        if storage is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.STORAGE] = bridge
            logger.info("ProactiveSystemBootstrap: Storage not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach storage to orchestrator
            self._orchestrator.attach_storage(storage)

            # Also attach to ZeroCostModulator within the orchestrator
            if hasattr(self._orchestrator, "_zero_cost_modulator"):
                self._orchestrator._zero_cost_modulator.attach_storage(storage)

            bridge.mark_connected()
            self._bridges[BridgeType.STORAGE] = bridge
            logger.info("ProactiveSystemBootstrap: Storage bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.STORAGE] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Storage wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_sentinel(self, sentinel: Any) -> None:
        """Wire Sentinel for continuous verification and drift detection.

        The sentinel bridge enables the ProactiveOrchestrator to:
        - Receive real-time verification reports
        - React to configuration drift, secret rotation needs, and security scans
        - Adjust daemon intervals based on sentinel findings
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.SENTINEL,
            subsystem_name="Sentinel",
        )

        if sentinel is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.SENTINEL] = bridge
            logger.info("ProactiveSystemBootstrap: Sentinel not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach sentinel to orchestrator
            self._orchestrator.attach_sentinel(sentinel)

            bridge.mark_connected()
            self._bridges[BridgeType.SENTINEL] = bridge
            logger.info("ProactiveSystemBootstrap: Sentinel bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.SENTINEL] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Sentinel wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_defense(self, defense: Any) -> None:
        """Wire DefenseEngine for active security and threat response.

        The defense bridge enables the ProactiveOrchestrator to:
        - Monitor threat levels and active incidents
        - Trigger hardening actions in response to elevated threats
        - Quarantine compromised services automatically
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.DEFENSE,
            subsystem_name="DefenseEngine",
        )

        if defense is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.DEFENSE] = bridge
            logger.info("ProactiveSystemBootstrap: Defense not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach defense to orchestrator
            self._orchestrator.attach_defense(defense)

            bridge.mark_connected()
            self._bridges[BridgeType.DEFENSE] = bridge
            logger.info("ProactiveSystemBootstrap: Defense bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.DEFENSE] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Defense wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_foresight(self, foresight: Any) -> None:
        """Wire ForesightEngine for predictive intelligence.

        The foresight bridge enables the ProactiveOrchestrator to:
        - Receive trajectory predictions and probability vectors
        - Use adaptive parameter recommendations for system tuning
        - Feed foresight-derived metrics into the health predictor
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.FORESIGHT,
            subsystem_name="ForesightEngine",
        )

        if foresight is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.FORESIGHT] = bridge
            logger.info("ProactiveSystemBootstrap: Foresight not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach foresight to orchestrator
            self._orchestrator.attach_foresight(foresight)

            bridge.mark_connected()
            self._bridges[BridgeType.FORESIGHT] = bridge
            logger.info("ProactiveSystemBootstrap: Foresight bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.FORESIGHT] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Foresight wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_router(self, router: Any) -> None:
        """Wire FluidicRouter for adaptive request routing.

        The routing bridge enables the ProactiveOrchestrator to:
        - Monitor routing weights and service response times
        - Trigger rebalancing actions when routing health degrades
        - Feed routing metrics into the predictive health analyzer
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.ROUTING,
            subsystem_name="FluidicRouter",
        )

        if router is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.ROUTING] = bridge
            logger.info("ProactiveSystemBootstrap: Router not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach router to orchestrator
            self._orchestrator.attach_router(router)

            bridge.mark_connected()
            self._bridges[BridgeType.ROUTING] = bridge
            logger.info("ProactiveSystemBootstrap: Router bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.ROUTING] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Router wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_registry(self, registry: Any) -> None:
        """Wire EnhancedServiceRegistry for capability-based service discovery.

        The registry bridge enables the ProactiveOrchestrator to:
        - Track service registration, health, and load metrics
        - React to service discovery events (new services, lost services)
        - Feed service health data into the composite health profile
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.REGISTRY,
            subsystem_name="EnhancedServiceRegistry",
        )

        if registry is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.REGISTRY] = bridge
            logger.info("ProactiveSystemBootstrap: Registry not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach registry to orchestrator
            self._orchestrator.attach_registry(registry)

            # Subscribe to discovery events from the registry
            if hasattr(registry, "add_discovery_watcher"):

                def _on_discovery_event(event: Any) -> None:
                    bridge.record_event()
                    event_type = getattr(event, "event_type", "unknown")
                    service_name = getattr(event, "service_name", "unknown")

                    if event_type == "lost":
                        logger.warning(
                            "ProactiveSystemBootstrap: Service LOST: %s",
                            sanitize_for_log(service_name),
                        )
                    elif event_type == "discovered":
                        logger.info(
                            "ProactiveSystemBootstrap: Service discovered: %s",
                            sanitize_for_log(service_name),
                        )

                registry.add_discovery_watcher(_on_discovery_event)

            bridge.mark_connected()
            self._bridges[BridgeType.REGISTRY] = bridge
            logger.info("ProactiveSystemBootstrap: Registry bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.REGISTRY] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Registry wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_resilience(self, resilience: Any) -> None:
        """Wire ResilienceManager for circuit breaker and bulkhead protection.

        The resilience bridge enables the ProactiveOrchestrator to:
        - Monitor circuit breaker states (closed, open, half-open)
        - Track bulkhead capacity utilization
        - Trigger healing actions when circuits open or bulkheads saturate
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.RESILIENCE,
            subsystem_name="ResilienceManager",
        )

        if resilience is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.RESILIENCE] = bridge
            logger.info("ProactiveSystemBootstrap: Resilience not provided — bridge disabled")
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Attach resilience to orchestrator
            self._orchestrator.attach_resilience(resilience)

            bridge.mark_connected()
            self._bridges[BridgeType.RESILIENCE] = bridge
            logger.info("ProactiveSystemBootstrap: Resilience bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.RESILIENCE] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Resilience wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    # ------------------------------------------------------------------
    # Auxiliary System Wiring
    # ------------------------------------------------------------------

    async def _wire_pulse_controller(self) -> None:
        """Wire AdaptivePulseController for dynamic interval adjustment.

        The pulse controller adjusts daemon intervals based on system health:
        - STEADY: Normal intervals during healthy operation
        - ACCELERATED: Compressed intervals during degradation
        - EMERGENCY: Maximum compression during critical issues
        - RECOVERY: Gradual return to baseline after resolution
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.PULSE,
            subsystem_name="AdaptivePulseController",
        )

        if self._pulse is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.PULSE] = bridge
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Register key daemons with the pulse controller
            # (pulse daemon registration happens in _register_pulse_daemons)
            # Subscribe pulse to orchestrator health updates
            if hasattr(self._orchestrator, "attach_pulse"):
                self._orchestrator.attach_pulse(self._pulse)

            bridge.mark_connected()
            self._bridges[BridgeType.PULSE] = bridge
            logger.info("ProactiveSystemBootstrap: Pulse controller bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.PULSE] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Pulse wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_auto_config(self) -> None:
        """Wire AutoConfigManager for environment-driven configuration.

        The auto-config manager:
        - Auto-detects the runtime environment (TRUE_NAS, HYBRID, CLOUD_ONLY)
        - Applies the optimal configuration profile
        - Supports hot-reload of configuration changes
        - Validates and rolls back on failure
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.CONFIG,
            subsystem_name="AutoConfigManager",
        )

        if self._config is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.CONFIG] = bridge
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Subscribe to config changes
            if hasattr(self._config, "add_change_listener"):

                def _on_config_change(key: str, old_value: Any, new_value: Any) -> None:
                    bridge.record_event()
                    # Propagate config changes to orchestrator
                    if key.startswith("proactive.") or key.startswith("orchestrator."):
                        self._apply_orchestrator_config(key, new_value)
                    elif key.startswith("pulse."):
                        self._apply_pulse_config(key, new_value)
                    elif key.startswith("scaler."):
                        self._apply_scaler_config(key, new_value)

                self._config.add_change_listener(_on_config_change)

            bridge.mark_connected()
            self._bridges[BridgeType.CONFIG] = bridge
            logger.info("ProactiveSystemBootstrap: Auto-config bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.CONFIG] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Auto-config wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    async def _wire_predictive_scaler(self) -> None:
        """Wire PredictiveAutoscaler for zero-cost-aware resource scaling.

        The predictive scaler:
        - Forecasts load using Holt's double exponential smoothing
        - Generates scaling decisions (UP, DOWN, MAINTAIN)
        - Enforces zero-cost compliance (never exceeds free-tier limits)
        - Provides confidence intervals on all predictions
        """
        bridge = BridgeConnection(
            bridge_type=BridgeType.SCALER,
            subsystem_name="PredictiveAutoscaler",
        )

        if self._scaler is None:
            bridge.status = WiringStatus.DISABLED
            self._bridges[BridgeType.SCALER] = bridge
            return

        try:
            bridge.status = WiringStatus.CONNECTING

            # Register storage tiers as scalable resources
            storage = self._subsystems.get("storage")
            if storage and hasattr(storage, "_get_priority_order"):
                from Dimensional.architecture.smart_storage import StorageTier

                tier_limits = {
                    StorageTier.R2: 10,  # 10GB free
                    StorageTier.OCI: 20,  # 20GB free
                    StorageTier.GCP: 5,  # 5GB free
                    StorageTier.AZURE: 25,  # 25GB free
                    StorageTier.AWS: 25,  # 25GB free
                }
                for tier, free_limit in tier_limits.items():
                    try:
                        self._scaler.register_resource(
                            resource_name=f"storage_{tier.name.lower()}",
                            min_units=0,
                            max_units=free_limit,
                            free_tier_limit=free_limit,
                        )
                    except Exception:
                        pass  # Resource may already be registered

            bridge.mark_connected()
            self._bridges[BridgeType.SCALER] = bridge
            logger.info("ProactiveSystemBootstrap: Predictive scaler bridge connected")

        except Exception as e:
            bridge.mark_error(str(e))
            self._bridges[BridgeType.SCALER] = bridge
            logger.error(
                "ProactiveSystemBootstrap: Scaler wiring failed: %s",
                sanitize_for_log(str(e)),
            )

    # ------------------------------------------------------------------
    # Action Handler Registration
    # ------------------------------------------------------------------

    async def _register_action_handlers(self) -> None:
        """Register proactive action handlers with the ActionDispatcher.

        Each action type (HEAL, SCALE_UP, MIGRATE_STORAGE, etc.) gets a
        dedicated handler that routes the action to the appropriate subsystem.
        """
        from Dimensional.architecture.proactive_orchestrator import ProactiveAction

        dispatcher = getattr(self._orchestrator, "_action_dispatcher", None)
        if dispatcher is None:
            logger.warning("ProactiveSystemBootstrap: No action dispatcher found")
            return

        # HEAL → AutoHealingEngine (with subsystem-specific strategies)
        dispatcher.register_handler(ProactiveAction.HEAL, self._handle_heal)

        # SCALE_UP / SCALE_DOWN → PredictiveAutoscaler
        dispatcher.register_handler(ProactiveAction.SCALE_UP, self._handle_scale_up)
        dispatcher.register_handler(ProactiveAction.SCALE_DOWN, self._handle_scale_down)

        # MIGRATE_STORAGE → SmartStorageOrchestrator
        dispatcher.register_handler(ProactiveAction.MIGRATE_STORAGE, self._handle_migration)

        # REBALANCE → FluidicRouter
        dispatcher.register_handler(ProactiveAction.REBALANCE, self._handle_rebalance)

        # HARDEN → DefenseEngine
        dispatcher.register_handler(ProactiveAction.HARDEN, self._handle_harden)

        # ALERT → EventBus publish
        dispatcher.register_handler(ProactiveAction.ALERT, self._handle_alert)

        # RECONFIGURE → AutoConfigManager
        dispatcher.register_handler(ProactiveAction.RECONFIGURE, self._handle_reconfigure)

        # QUARANTINE → ResilienceManager
        dispatcher.register_handler(ProactiveAction.QUARANTINE, self._handle_quarantine)

        logger.info("ProactiveSystemBootstrap: Action handlers registered (8 types)")

    # ------------------------------------------------------------------
    # Pulse Daemon Registration
    # ------------------------------------------------------------------

    def _register_pulse_daemons(self) -> None:
        """Register all daemons with the AdaptivePulseController.

        Daemons and their baseline intervals:
        - sentinel:         30s (security verification)
        - discovery:        60s (service discovery)
        - orchestration:    15s (proactive orchestration)
        - capacity_check:   60s (storage capacity monitoring)
        - threat_scan:     120s (security threat scanning)
        - rebalance:        30s (routing weight rebalancing)
        - foresight:        45s (trajectory prediction)
        - health_collect:   10s (health metric collection)
        """
        if self._pulse is None:
            return

        daemon_intervals = {
            "sentinel": 30.0,
            "discovery": 60.0,
            "orchestration": 15.0,
            "capacity_check": 60.0,
            "threat_scan": 120.0,
            "rebalance": 30.0,
            "foresight": 45.0,
            "health_collect": 10.0,
        }

        for name, baseline in daemon_intervals.items():
            try:
                self._pulse.register(name, baseline)
            except Exception:
                pass  # May already be registered

        logger.info(
            "ProactiveSystemBootstrap: Registered %d pulse-controlled daemons",
            len(daemon_intervals),
        )

    # ------------------------------------------------------------------
    # Event Handlers (EventBus → Orchestrator)
    # ------------------------------------------------------------------

    async def _handle_storage_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
    ) -> None:
        """Route storage events to the orchestrator."""
        if "capacity_critical" in event_type or "migration_needed" in event_type:
            # Record metric for health prediction
            self._orchestrator._health_analyzer.record(
                "storage",
                0.3,
                tags={"event": event_type},
            )
        elif "migration_complete" in event_type:
            self._orchestrator._health_analyzer.record(
                "storage",
                0.8,
                tags={"event": event_type},
            )
        elif event_type == "storage.tier_health":
            health_score = data.get("health_score", 0.5)
            self._orchestrator._health_analyzer.record("storage", health_score)

    async def _handle_security_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
    ) -> None:
        """Route security events to the orchestrator."""
        threat_level = data.get("threat_level", "low")
        threat_score = {"critical": 0.1, "high": 0.3, "medium": 0.6, "low": 0.9}.get(
            threat_level,
            0.5,
        )
        self._orchestrator._health_analyzer.record("security", threat_score)

        # Elevate pulse mode if threat is high
        if threat_level in ("critical", "high") and self._pulse:
            self._pulse.update(threat_score)

    async def _handle_service_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
    ) -> None:
        """Route service discovery/health events to the orchestrator."""
        if "lost" in event_type or "unhealthy" in event_type:
            self._orchestrator._health_analyzer.record("service", 0.3)
        elif "discovered" in event_type or "healthy" in event_type:
            self._orchestrator._health_analyzer.record("service", 0.9)
        else:
            health = data.get("health_score", 0.7)
            self._orchestrator._health_analyzer.record("service", health)

    async def _handle_circuit_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
    ) -> None:
        """Route circuit breaker events to the orchestrator."""
        state = data.get("state", "closed")
        state_score = {"closed": 0.9, "half_open": 0.5, "open": 0.1}.get(state, 0.5)
        self._orchestrator._health_analyzer.record("resilience", state_score)

    async def _handle_health_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
    ) -> None:
        """Route general health events to the orchestrator."""
        subsystem = data.get("subsystem", "unknown")
        score = data.get("health_score", 0.5)
        self._orchestrator._health_analyzer.record(subsystem, score)

    # ------------------------------------------------------------------
    # Action Handlers (Orchestrator → Subsystems)
    # ------------------------------------------------------------------

    async def _handle_heal(self, plan: Any) -> Any:
        """Handle HEAL actions by routing to the appropriate subsystem."""
        bridge = self._bridges.get(BridgeType.SENTINEL)
        if bridge:
            bridge.record_action()

        # Delegate to orchestrator's built-in healing
        if hasattr(self._orchestrator, "_handle_heal_action"):
            return await self._orchestrator._handle_heal_action(plan)
        return plan

    async def _handle_scale_up(self, plan: Any) -> Any:
        """Handle SCALE_UP actions by routing to the PredictiveAutoscaler."""
        bridge = self._bridges.get(BridgeType.SCALER)
        if bridge:
            bridge.record_action()

        if self._scaler and hasattr(self._scaler, "evaluate"):
            decisions = self._scaler.evaluate()
            for decision in decisions:
                logger.info(
                    "ProactiveSystemBootstrap: Scale decision: %s → %d units (%s)",
                    sanitize_for_log(decision.direction.value),
                    decision.target_units,
                    sanitize_for_log(decision.reason.value),
                )
        return plan

    async def _handle_scale_down(self, plan: Any) -> Any:
        """Handle SCALE_DOWN actions by routing to the PredictiveAutoscaler."""
        bridge = self._bridges.get(BridgeType.SCALER)
        if bridge:
            bridge.record_action()

        if self._scaler and hasattr(self._scaler, "evaluate"):
            self._scaler.evaluate()
        return plan

    async def _handle_migration(self, plan: Any) -> Any:
        """Handle MIGRATE_STORAGE actions by routing to SmartStorageOrchestrator."""
        bridge = self._bridges.get(BridgeType.STORAGE)
        if bridge:
            bridge.record_action()

        storage = self._subsystems.get("storage")
        if storage and hasattr(storage, "_check_and_migrate"):
            try:
                await storage._check_and_migrate()
            except Exception as e:
                logger.error(
                    "ProactiveSystemBootstrap: Storage migration failed: %s",
                    sanitize_for_log(str(e)),
                )
        return plan

    async def _handle_rebalance(self, plan: Any) -> Any:
        """Handle REBALANCE actions by routing to FluidicRouter."""
        bridge = self._bridges.get(BridgeType.ROUTING)
        if bridge:
            bridge.record_action()

        router = self._subsystems.get("router")
        if router and hasattr(router, "stats"):
            stats = router.stats()
            logger.info(
                "ProactiveSystemBootstrap: Router rebalance — %d routes tracked",
                len(stats.get("routes", {})),
            )
        return plan

    async def _handle_harden(self, plan: Any) -> None:
        """Handle HARDEN actions by routing to DefenseEngine."""
        bridge = self._bridges.get(BridgeType.DEFENSE)
        if bridge:
            bridge.record_action()

        defense = self._subsystems.get("defense")
        if defense and hasattr(defense, "get_current_threat_level"):
            threat_level = defense.get_current_threat_level()
            logger.info(
                "ProactiveSystemBootstrap: Security harden — current threat: %s",
                sanitize_for_log(str(threat_level)),
            )

    async def _handle_alert(self, plan: Any) -> None:
        """Handle ALERT actions by publishing to EventBus."""
        event_bus = self._subsystems.get("event_bus")
        if event_bus and hasattr(event_bus, "publish"):
            from Dimensional.models import EventMessage

            await event_bus.publish(
                EventMessage(
                    event_type="proactive.alert",
                    source="ProactiveSystemBootstrap",
                    data={
                        "alert_type": getattr(plan, "action", "unknown").value  # type: ignore[union-attr]
                        if hasattr(getattr(plan, "action", None), "value")
                        else str(getattr(plan, "action", "unknown")),
                        "target": getattr(plan, "target", "unknown"),
                        "priority": getattr(plan, "priority", "unknown").value  # type: ignore[union-attr]
                        if hasattr(getattr(plan, "priority", None), "value")
                        else str(getattr(plan, "priority", "medium")),
                        "description": getattr(plan, "description", ""),
                    },
                )
            )

    async def _handle_reconfigure(self, plan: Any) -> None:
        """Handle RECONFIGURE actions by routing to AutoConfigManager."""
        bridge = self._bridges.get(BridgeType.CONFIG)
        if bridge:
            bridge.record_action()

        if self._config and hasattr(self._config, "auto_configure"):
            try:
                self._config.auto_configure()
            except Exception as e:
                logger.error(
                    "ProactiveSystemBootstrap: Reconfigure failed: %s",
                    sanitize_for_log(str(e)),
                )

    async def _handle_quarantine(self, plan: Any) -> None:
        """Handle QUARANTINE actions by routing to ResilienceManager."""
        bridge = self._bridges.get(BridgeType.RESILIENCE)
        if bridge:
            bridge.record_action()

        resilience = self._subsystems.get("resilience")
        target = getattr(plan, "target", "unknown")
        if resilience and hasattr(resilience, "get_breaker"):
            breaker = resilience.get_breaker(target)
            if breaker:
                breaker.record_failure()
                logger.warning(
                    "ProactiveSystemBootstrap: Quarantined service: %s",
                    sanitize_for_log(target),
                )

    # ------------------------------------------------------------------
    # Config Change Propagation
    # ------------------------------------------------------------------

    def _apply_orchestrator_config(self, key: str, value: Any) -> None:
        """Apply configuration changes to the ProactiveOrchestrator."""
        if not self._orchestrator:
            return

        if key == "proactive.mode":
            from Dimensional.architecture.proactive_orchestrator import OrchestratorMode

            try:
                mode = OrchestratorMode(value) if isinstance(value, str) else value
                self._orchestrator.set_mode(mode)
                logger.info("ProactiveSystemBootstrap: Orchestrator mode → %s", mode.value)
            except (ValueError, AttributeError):
                pass
        elif key == "proactive.orchestration_interval":
            if hasattr(self._orchestrator, "_orchestration_interval"):
                self._orchestrator._orchestration_interval = float(value)
        elif key == "proactive.healing_enabled":
            if hasattr(self._orchestrator, "_auto_heal_engine"):
                self._orchestrator._auto_heal_engine.enabled = bool(value)

    def _apply_pulse_config(self, key: str, value: Any) -> None:
        """Apply configuration changes to the AdaptivePulseController."""
        if not self._pulse:
            return

        if key == "pulse.acceleration_factor":
            if hasattr(self._pulse, "_acceleration_factor"):
                self._pulse._acceleration_factor = float(value)
        elif key == "pulse.emergency_factor":
            if hasattr(self._pulse, "_emergency_factor"):
                self._pulse._emergency_factor = float(value)
        elif key == "pulse.recovery_rate":
            if hasattr(self._pulse, "_recovery_rate"):
                self._pulse._recovery_rate = float(value)

    def _apply_scaler_config(self, key: str, value: Any) -> None:
        """Apply configuration changes to the PredictiveAutoscaler."""
        if not self._scaler:
            return

        if key == "scaler.scale_up_threshold":
            if hasattr(self._scaler, "_scale_up_threshold"):
                self._scaler._scale_up_threshold = float(value)
        elif key == "scaler.scale_down_threshold":
            if hasattr(self._scaler, "_scale_down_threshold"):
                self._scaler._scale_down_threshold = float(value)
        elif key == "scaler.cooldown_seconds":
            if hasattr(self._scaler, "_cooldown_seconds"):
                self._scaler._cooldown_seconds = float(value)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive wiring status for all bridges."""
        return {
            "wired": self._wired,
            "started": self._started,
            "bridges": self.bridge_status,
            "subsystems_connected": sum(
                1
                for b in self._bridges.values()
                if b.status in (WiringStatus.CONNECTED, WiringStatus.ACTIVE)
            ),
            "subsystems_total": len(self._bridges),
            "total_events_processed": sum(b.events_processed for b in self._bridges.values()),
            "total_actions_dispatched": sum(b.actions_dispatched for b in self._bridges.values()),
            "total_errors": sum(b.errors for b in self._bridges.values()),
        }

    def get_dashboard(self) -> Dict[str, Any]:
        """Get a dashboard-ready summary of the proactive system state."""
        status = self.get_status()

        # Get orchestrator dashboard if available
        orchestrator_dashboard = {}
        if self._orchestrator and hasattr(self._orchestrator, "get_dashboard"):
            try:
                orchestrator_dashboard = self._orchestrator.get_dashboard()
            except Exception:
                pass

        # Get health profile if available
        health_profile = {}  # type: ignore[var-annotated]
        if self._orchestrator and hasattr(self._orchestrator, "get_health_profile"):
            try:
                hp = self._orchestrator.get_health_profile()
                health_profile = hp.to_dict() if hasattr(hp, "to_dict") else {}
            except Exception:
                pass

        # Get zero-cost status if available
        zero_cost_status = {}  # type: ignore[var-annotated]
        if self._orchestrator and hasattr(self._orchestrator, "get_zero_cost_status"):
            try:
                zc = self._orchestrator.get_zero_cost_status()
                zero_cost_status = zc.to_dict() if hasattr(zc, "to_dict") else {}
            except Exception:
                pass

        # Get pulse state if available
        pulse_state = {}
        if self._pulse and hasattr(self._pulse, "get_all_intervals"):
            try:
                pulse_state = self._pulse.get_all_intervals()
            except Exception:
                pass

        # Get scaler state if available
        scaler_state = {}
        if self._scaler and hasattr(self._scaler, "get_all_decisions"):
            try:
                scaler_state = self._scaler.get_all_decisions()
            except Exception:
                pass

        return {
            "system_status": status,
            "orchestrator": orchestrator_dashboard,
            "health_profile": health_profile,
            "zero_cost_compliance": zero_cost_status,
            "pulse_state": pulse_state,
            "scaler_state": scaler_state,
            "config_profile": (
                self._config.get_active_profile()
                if self._config and hasattr(self._config, "get_active_profile")
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

proactive_bootstrap = ProactiveSystemBootstrap()
