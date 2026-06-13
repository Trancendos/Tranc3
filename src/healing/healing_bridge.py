"""
Healing Bridge — wires LogicCoreHealthMonitor alerts to SelfRepairEngine.

Subscribes to health monitor alert callbacks and translates degraded/emergency
status events into SelfRepairEngine context dictionaries, then calls
evaluate_and_repair() so registered strategies fire automatically.

Usage (in api.py lifespan):
    from src.healing.healing_bridge import HealingBridge
    bridge = HealingBridge(health_monitor, repair_engine)
    bridge.attach()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger("tranc3.healing.bridge")


class HealingBridge:
    def __init__(self, health_monitor: Any, repair_engine: Any) -> None:
        self._monitor = health_monitor
        self._engine = repair_engine
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach(self) -> None:
        """Subscribe to health monitor alerts and wire to repair engine."""
        try:
            self._monitor.subscribe_alerts(self._on_alert)
            logger.info("HealingBridge attached — health monitor → repair engine wired")
        except Exception as exc:
            logger.warning("HealingBridge.attach failed: %s", exc)

    def _on_alert(self, alert: Any) -> None:
        """Callback from health monitor — dispatch to repair engine."""
        try:
            status = str(getattr(alert, "status", "") or getattr(alert, "health_status", ""))
            service_id = str(getattr(alert, "service_id", "unknown"))

            context: Dict[str, Any] = {
                "service_id": service_id,
                "health_status": status.lower(),
                "error_rate": float(getattr(alert, "error_rate", 0.0)),
                "response_time_ms": float(getattr(alert, "response_time_ms", 0.0)),
                "alert": alert,
            }

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._engine.evaluate_and_repair(context))
                else:
                    loop.run_until_complete(self._engine.evaluate_and_repair(context))
            except RuntimeError:
                asyncio.run(self._engine.evaluate_and_repair(context))

        except Exception as exc:
            logger.error("HealingBridge._on_alert error: %s", exc)
