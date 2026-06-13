"""Health Monitor → Self-Repair Bridge.

Subscribes to health-status-change events from LogicCoreHealthMonitor and
automatically triggers SelfRepairEngine when a service degrades.

Wire up by calling `wire_health_to_repair()` once at startup (e.g. inside
the FastAPI lifespan context manager).  The function is idempotent — calling
it twice is safe.

Severity mapping:
    DEGRADED  → evaluate_and_repair()   (normal repair cycle)
    CRITICAL  → evaluate_and_repair()   (normal repair cycle)
    EMERGENCY → emergency_repair()       (bypass all cooldowns)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("tranc3.healing.bridge")

_wired = False


async def _on_health_event(event: dict) -> None:
    """Callback invoked by LogicCoreHealthMonitor on every status change."""
    new_status = event.get("new_status", "")
    service_id = event.get("service_id", "unknown")

    if new_status not in ("DEGRADED", "CRITICAL", "EMERGENCY"):
        return

    logger.info(
        "health_repair_bridge: %s transitioned to %s — triggering repair",
        service_id,
        new_status,
    )

    try:
        from src.healing.self_repair import SelfRepairEngine

        engine = SelfRepairEngine()
        context = {
            "service_id": service_id,
            "status": new_status,
            "composite_score": event.get("composite_score", 0.0),
            "timestamp": event.get("timestamp"),
        }

        if new_status == "EMERGENCY":
            results = await engine.emergency_repair(context)
        else:
            results = await engine.evaluate_and_repair(context)

        if results:
            logger.info(
                "health_repair_bridge: %d repair action(s) applied for %s",
                len(results),
                service_id,
            )

        # Emit to Observatory
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                "healing.repair_triggered",
                service="health_repair_bridge",
                category=EventCategory.SYSTEM,
                actor=service_id,
                outcome="applied" if results else "no_action",
                metadata={
                    "trigger_status": new_status,
                    "actions_applied": len(results),
                    "actions": [r.get("strategy") for r in results if isinstance(r, dict)],
                },
            )
        except Exception:
            pass

    except Exception as exc:
        logger.error("health_repair_bridge: repair error for %s: %s", service_id, exc)


def wire_health_to_repair() -> bool:
    """
    Subscribe _on_health_event to LogicCoreHealthMonitor.

    Returns True if wired successfully, False if the monitor is unavailable.
    Idempotent — calling more than once is safe.
    """
    global _wired
    if _wired:
        return True

    try:
        from src.healing.health_monitor import LogicCoreHealthMonitor

        monitor = LogicCoreHealthMonitor()
        monitor.subscribe_alerts(_on_health_event)
        _wired = True
        logger.info(
            "health_repair_bridge: wired — self-repair will trigger on DEGRADED/CRITICAL/EMERGENCY"
        )
        return True
    except Exception as exc:
        logger.warning("health_repair_bridge: could not wire to health monitor: %s", exc)
        return False
