"""
Sovereign Controller — Trance-One Tier 1
==========================================
Top-level platform authority. Manages the 5-tier AI hierarchy, enforces
zero-cost compliance platform-wide, and arbitrates emergency failovers.

No paid external service calls ever originate from or pass through here.
All decisions are logged to The Observatory for full audit traceability.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from trance_one.platform_manifest import (
    PlatformManifest,
    get_manifest,
)
from trance_one.tier_bridge import (
    TierBridge,
    TierCommand,
    TierCommandType,
    TierEvent,
    get_tier_bridge,
)

logger = logging.getLogger("trance_one.sovereign")

# Tier constants — immutable identifiers
TIER_SOVEREIGN = 1
TIER_PRIME = 2
TIER_BASE_AI = 3
TIER_AGENT = 4
TIER_WORKER = 5


@dataclass
class PlatformState:
    initialised_at: float = field(default_factory=time.time)
    active_entities: Dict[str, bool] = field(default_factory=dict)
    zero_cost_violations: List[str] = field(default_factory=list)
    emergency_failovers: int = 0
    tier_health: Dict[int, str] = field(default_factory=lambda: {
        TIER_SOVEREIGN: "healthy",
        TIER_PRIME: "unknown",
        TIER_BASE_AI: "unknown",
        TIER_AGENT: "unknown",
        TIER_WORKER: "unknown",
    })


class SovereignController:
    """
    Trance-One Sovereign Controller.

    Single instance per platform deployment.
    Manages platform state, tier lifecycle, and emergency authority.
    """

    TIER = TIER_SOVEREIGN

    def __init__(self) -> None:
        self._manifest: PlatformManifest = get_manifest()
        self._bridge: TierBridge = get_tier_bridge()
        self._state = PlatformState()
        self._scan_task: Optional[asyncio.Task] = None
        self._register_default_handlers()
        logger.info("Trance-One Sovereign Controller initialised.")

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Start the sovereign controller background loop."""
        logger.info("Trance-One: starting sovereign loop")
        self._scan_task = asyncio.create_task(self._sovereign_loop())

    async def stop(self) -> None:
        if self._scan_task:
            self._scan_task.cancel()
            logger.info("Trance-One: sovereign loop stopped")

    async def _sovereign_loop(self) -> None:
        """Background health and compliance loop (runs every 60 s)."""
        while True:
            try:
                await self._enforce_zero_cost_policy()
                await self._probe_tier_health()
            except Exception as exc:
                logger.error("Sovereign loop error: %s", exc)
            await asyncio.sleep(60.0)

    # -----------------------------------------------------------------------
    # Zero-cost enforcement
    # -----------------------------------------------------------------------

    async def _enforce_zero_cost_policy(self) -> None:
        """
        Issue zero-cost enforcement commands to all tiers.
        Any pending violations trigger a SUSPEND_PAID_CALLS broadcast.
        """
        try:
            from src.platform.zero_cost_service_map import audit_zero_cost
            audit = audit_zero_cost()
            if not audit["compliant"]:
                self._state.zero_cost_violations = [
                    f"{v['entity']}:{v['foundation']}"
                    for v in audit.get("violations", [])
                ]
                self._bridge.issue_command(TierCommand(
                    command_type=TierCommandType.SUSPEND_PAID_CALLS,
                    source_tier=TIER_SOVEREIGN,
                    target_tier=TIER_BASE_AI,
                    payload={"violations": self._state.zero_cost_violations},
                    priority=1,
                ))
                logger.critical(
                    "ZERO-COST VIOLATION: %s", self._state.zero_cost_violations
                )
            else:
                self._state.zero_cost_violations = []
        except ImportError:
            pass  # platform module not yet loaded

    async def _probe_tier_health(self) -> None:
        """Surface tier health state events upward from T2/T3."""
        self._bridge.surface_event(TierEvent(
            source_tier=TIER_SOVEREIGN,
            source_entity=None,
            event_type="SOVEREIGN_HEARTBEAT",
            payload={"platform_state": self.status()},
        ))

    # -----------------------------------------------------------------------
    # Emergency authority
    # -----------------------------------------------------------------------

    def emergency_rotate(self, entity_id: str) -> None:
        """Force an emergency rotation — highest-priority command."""
        self._state.emergency_failovers += 1
        self._bridge.issue_command(TierCommand(
            command_type=TierCommandType.ROTATE_ENTITY,
            source_tier=TIER_SOVEREIGN,
            target_tier=TIER_BASE_AI,
            target_entity=entity_id,
            payload={"reason": "sovereign_emergency_rotate"},
            priority=1,
        ))
        logger.warning("Sovereign emergency rotate: entity=%s", entity_id)

    def activate_entity(self, entity_id: str) -> None:
        self._state.active_entities[entity_id] = True
        self._bridge.issue_command(TierCommand(
            command_type=TierCommandType.ACTIVATE_ENTITY,
            source_tier=TIER_SOVEREIGN,
            target_tier=TIER_BASE_AI,
            target_entity=entity_id,
        ))

    def deactivate_entity(self, entity_id: str) -> None:
        self._state.active_entities[entity_id] = False
        self._bridge.issue_command(TierCommand(
            command_type=TierCommandType.DEACTIVATE_ENTITY,
            source_tier=TIER_SOVEREIGN,
            target_tier=TIER_BASE_AI,
            target_entity=entity_id,
        ))

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------

    def status(self) -> dict:
        manifest_summary = self._manifest.summary()
        return {
            "tier": TIER_SOVEREIGN,
            "label": "Trance-One",
            "initialised_at": self._state.initialised_at,
            "zero_cost_compliant": len(self._state.zero_cost_violations) == 0,
            "zero_cost_violations": self._state.zero_cost_violations,
            "emergency_failovers": self._state.emergency_failovers,
            "tier_health": self._state.tier_health,
            "platform": manifest_summary,
            "recent_commands": self._bridge.recent_commands(10),
        }

    # -----------------------------------------------------------------------
    # Handler registration
    # -----------------------------------------------------------------------

    def _register_default_handlers(self) -> None:
        """Register default upward event handlers from lower tiers."""
        self._bridge.register_event_listener(self._on_tier_event)

    def _on_tier_event(self, event: TierEvent) -> None:
        if event.event_type == "ZERO_COST_VIOLATION":
            entity = event.payload.get("entity_id", "unknown")
            if entity not in self._state.zero_cost_violations:
                self._state.zero_cost_violations.append(entity)
                logger.critical(
                    "Sovereign received zero-cost violation from T%d entity=%s",
                    event.source_tier,
                    entity,
                )
        elif event.event_type.startswith("TIER_HEALTH_"):
            tier_num = event.payload.get("tier")
            health = event.payload.get("health", "unknown")
            if tier_num:
                self._state.tier_health[tier_num] = health


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_sovereign: Optional[SovereignController] = None


def get_sovereign() -> SovereignController:
    global _sovereign
    if _sovereign is None:
        _sovereign = SovereignController()
    return _sovereign
