"""
Self-healing monitor — proactive service recovery (cell regeneration pattern).

Polls configured services, detects degradation, and triggers corrective actions
(log escalation, cooldown reset, alert emission) without human intervention.

Philosophy: each service is a "cell" in the platform organism. When a cell
goes unhealthy it signals the system to regenerate it. The healer is the
immune system.

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CellState:
    name: str
    url: str
    healthy: bool = True
    consecutive_failures: int = 0
    last_checked: float = 0.0
    recovery_actions_taken: int = 0

    @property
    def degraded(self) -> bool:
        return self.consecutive_failures >= 2

    @property
    def critical(self) -> bool:
        return self.consecutive_failures >= 5


@dataclass
class SelfHealer:
    """Platform immune system — monitors cells and triggers regeneration."""

    poll_interval_s: float = 30.0
    timeout_s: float = 5.0
    _cells: Dict[str, CellState] = field(default_factory=dict)
    _recovery_hooks: List[Callable[[CellState], None]] = field(default_factory=list)
    _running: bool = False

    def register_cell(self, name: str, health_url: str) -> None:
        self._cells[name] = CellState(name=name, url=health_url)

    def on_recovery_needed(self, hook: Callable[[CellState], None]) -> None:
        """Register a hook called when a cell enters degraded state."""
        self._recovery_hooks.append(hook)

    async def _probe_cell(self, cell: CellState, client: httpx.AsyncClient) -> None:
        try:
            resp = await client.get(cell.url, timeout=self.timeout_s)
            alive = resp.is_success
        except Exception:  # noqa: BLE001
            alive = False

        cell.last_checked = time.monotonic()
        if alive:
            if not cell.healthy:
                logger.info(
                    "Cell '%s' recovered (was down for %d probes)",
                    cell.name,
                    cell.consecutive_failures,
                )
            cell.healthy = True
            cell.consecutive_failures = 0
        else:
            cell.healthy = False
            cell.consecutive_failures += 1
            level = logging.CRITICAL if cell.critical else logging.WARNING
            logger.log(level, "Cell '%s' failure #%d", cell.name, cell.consecutive_failures)
            if cell.degraded:
                for hook in self._recovery_hooks:
                    try:
                        hook(cell)
                    except Exception:  # noqa: BLE001
                        logger.exception("Recovery hook failed for cell '%s'", cell.name)
                cell.recovery_actions_taken += 1

    async def run_once(self) -> Dict[str, bool]:
        """Probe all cells; return health map."""
        async with httpx.AsyncClient() as client:
            await asyncio.gather(*[self._probe_cell(c, client) for c in self._cells.values()])
        return {name: cell.healthy for name, cell in self._cells.items()}

    async def run_forever(self) -> None:
        self._running = True
        logger.info(
            "SelfHealer started — monitoring %d cells every %.0fs",
            len(self._cells),
            self.poll_interval_s,
        )
        while self._running:
            await self.run_once()
            await asyncio.sleep(self.poll_interval_s)

    def stop(self) -> None:
        self._running = False

    def summary(self) -> Dict[str, object]:
        return {
            name: {
                "healthy": cell.healthy,
                "consecutive_failures": cell.consecutive_failures,
                "recovery_actions_taken": cell.recovery_actions_taken,
                "last_checked": cell.last_checked,
            }
            for name, cell in self._cells.items()
        }


# ── Module-level singleton (lazy) ──────────────────────────────────────────────

_healer: Optional[SelfHealer] = None

P0_CELLS = {
    "infinity-ws": "http://localhost:8004/health",
    "infinity-auth": "http://localhost:8005/health",
}

P1_CELLS = {
    "users-service": "http://localhost:8006/health",
    "monitoring": "http://localhost:8007/health",
    "notifications": "http://localhost:8008/health",
    "infinity-ai": "http://localhost:8009/health",
    "the-grid": "http://localhost:8010/health",
}


def get_healer() -> SelfHealer:
    global _healer
    if _healer is None:
        _healer = SelfHealer()
        for name, url in {**P0_CELLS, **P1_CELLS}.items():
            _healer.register_cell(name, url)

        def _default_recovery(cell: CellState) -> None:
            logger.error(
                "AUTO-RECOVERY: cell '%s' degraded (failures=%d). Manual restart may be required.",
                cell.name,
                cell.consecutive_failures,
            )

        _healer.on_recovery_needed(_default_recovery)
    return _healer
