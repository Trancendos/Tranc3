"""
Tier Bridge — Trance-One ↔ T2ance ↔ Tranc3 command relay.

Trance-One issues TierCommands down the hierarchy.
Lower tiers surface events upward via the same bridge.
All inter-tier comms are logged to The Observatory audit trail.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("trance_one.tier_bridge")


class TierCommandType(str, Enum):
    # Lifecycle
    ACTIVATE_ENTITY = "ACTIVATE_ENTITY"
    DEACTIVATE_ENTITY = "DEACTIVATE_ENTITY"
    ROTATE_ENTITY = "ROTATE_ENTITY"
    RESTART_ENTITY = "RESTART_ENTITY"
    # Policy
    ENFORCE_ZERO_COST = "ENFORCE_ZERO_COST"
    SUSPEND_PAID_CALLS = "SUSPEND_PAID_CALLS"
    # Intelligence
    PROMOTE_AGENT = "PROMOTE_AGENT"  # Tier 4 → Tier 3 temporary elevation
    RECALL_AGENT = "RECALL_AGENT"  # Pull Tier 4 agent back
    SPAWN_WORKER = "SPAWN_WORKER"  # Spin up Tier 5 worker
    TERMINATE_WORKER = "TERMINATE_WORKER"
    # Platform
    PLATFORM_HEALTH_CHECK = "PLATFORM_HEALTH_CHECK"
    BROADCAST_STATUS = "BROADCAST_STATUS"


@dataclass
class TierCommand:
    command_type: TierCommandType
    source_tier: int  # 1 = Trance-One, 2 = T2ance, etc.
    target_tier: int
    target_entity: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: f"cmd-{int(time.time() * 1000)}")
    issued_at: float = field(default_factory=time.time)
    priority: int = 5  # 1 = highest, 10 = lowest


@dataclass
class TierEvent:
    source_tier: int
    source_entity: Optional[str]
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt-{int(time.time() * 1000)}")
    occurred_at: float = field(default_factory=time.time)


HandlerFn = Callable[[TierCommand], None]
EventListenerFn = Callable[[TierEvent], None]


class TierBridge:
    """
    Inter-tier command and event relay.

    Trance-One (Tier 1) issues downward commands; lower tiers surface events
    upward. Each tier registers its own command handlers and event listeners.
    """

    def __init__(self) -> None:
        self._command_handlers: Dict[TierCommandType, List[HandlerFn]] = {}
        self._event_listeners: List[EventListenerFn] = []
        self._command_log: List[TierCommand] = []
        self._event_log: List[TierEvent] = []

    def register_command_handler(self, command_type: TierCommandType, handler: HandlerFn) -> None:
        self._command_handlers.setdefault(command_type, []).append(handler)

    def register_event_listener(self, listener: EventListenerFn) -> None:
        self._event_listeners.append(listener)

    def issue_command(self, command: TierCommand) -> None:
        """Dispatch a command from a higher tier to a lower tier."""
        self._command_log.append(command)
        logger.info(
            "[TIER BRIDGE] T%d→T%d %s entity=%s id=%s",
            command.source_tier,
            command.target_tier,
            command.command_type.value,
            command.target_entity or "*",
            command.command_id,
        )
        for handler in self._command_handlers.get(command.command_type, []):
            try:
                handler(command)
            except Exception as exc:
                logger.error("Handler error for %s: %s", command.command_type.value, exc)

    def surface_event(self, event: TierEvent) -> None:
        """Surface an event from a lower tier upward."""
        self._event_log.append(event)
        logger.debug(
            "[TIER EVENT] T%d source=%s type=%s id=%s",
            event.source_tier,
            event.source_entity or "platform",
            event.event_type,
            event.event_id,
        )
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error("Event listener error: %s", exc)

    def recent_commands(self, limit: int = 50) -> List[dict]:
        return [
            {
                "id": c.command_id,
                "type": c.command_type.value,
                "from_tier": c.source_tier,
                "to_tier": c.target_tier,
                "entity": c.target_entity,
                "issued_at": c.issued_at,
            }
            for c in self._command_log[-limit:]
        ]

    def recent_events(self, limit: int = 50) -> List[dict]:
        return [
            {
                "id": e.event_id,
                "type": e.event_type,
                "from_tier": e.source_tier,
                "entity": e.source_entity,
                "occurred_at": e.occurred_at,
            }
            for e in self._event_log[-limit:]
        ]


_bridge: Optional[TierBridge] = None


def get_tier_bridge() -> TierBridge:
    global _bridge
    if _bridge is None:
        _bridge = TierBridge()
    return _bridge
