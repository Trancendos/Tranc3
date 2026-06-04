"""
Tranc3 — Tier 3 AI Base Template
==================================
The canonical base class for all Tier 3 Lead AIs in the Trancendos platform.

Tranc3 is the flagship AI tier: day-to-day location managers with full
sensory access to their hub, adaptive routing, genetic self-optimisation,
and liquid time-constant decision-making.

Design principles:
  - Adaptive: EWMA health tracking, gaseous load-balanced routing
  - Genetic:  NSGA-II multi-objective parameter evolution (async)
  - Liquid:   LTC ODE-governed state for smooth context continuity
  - Modular:  plug-in trait slots for hub-specific power-ups
  - Nanoflow: zero-cost, SQLite-backed, pure Python — no paid services

Power-up model:
  Each Tranc3 AI gains enhanced capability when within their home hub
  (their assigned location), but retains full mobility across the platform.
  Hub power-ups are injected via `register_hub_powerup()`.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Adaptive trait imports (all zero-cost, pure-Python fallbacks built in)
# ---------------------------------------------------------------------------

try:
    from shared_core.gas.kinetic import KineticEnergyTracker
    from shared_core.gas.pressure import PressureBalancer

    _GAS_AVAILABLE = True
except ImportError:
    _GAS_AVAILABLE = False

try:
    from shared_core.liquid.ltc_router import LiquidRouter

    _LIQUID_AVAILABLE = True
except ImportError:
    _LIQUID_AVAILABLE = False

try:
    from shared_core.genetics.fitness import LatencyThroughputFitness
    from shared_core.genetics.optimizer import GeneticOptimizer

    _GENETIC_AVAILABLE = True
except ImportError:
    _GENETIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# DNA strand — immutable identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tranc3DNA:
    """Immutable identity record for a Tier 3 AI."""

    aid: str  # e.g. "AID-NXS-01"
    location_pid: str  # home hub PID  e.g. "PID-NXS"
    name: str  # canonical display name
    tier: int = 3
    strand_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __str__(self) -> str:
        return f"Tranc3[{self.name}@{self.location_pid}]"


# ---------------------------------------------------------------------------
# SWOT snapshot
# ---------------------------------------------------------------------------


@dataclass
class SWOTSnapshot:
    """Live SWOT analysis snapshot for self-assessment."""

    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)
    assessed_at: float = field(default_factory=time.monotonic)

    def age_seconds(self) -> float:
        return time.monotonic() - self.assessed_at


# ---------------------------------------------------------------------------
# Hub power-up registry
# ---------------------------------------------------------------------------


@dataclass
class HubPowerUp:
    """A hub-specific capability enhancement."""

    name: str
    description: str
    active: bool = False
    handler: Callable[..., Any] | None = None


# ---------------------------------------------------------------------------
# Tranc3 base class
# ---------------------------------------------------------------------------


class Tranc3:
    """
    Tier 3 AI — Lead AI base for any Trancendos location.

    Sub-class this and override `process()` to build a concrete Lead AI.
    All adaptive, genetic, and liquid capabilities are wired in automatically
    when their shared_core modules are present (zero-cost, pure-Python).

    Example::

        class NexusPrime(Tranc3):
            def __init__(self):
                super().__init__(
                    aid="AID-NXS-01",
                    location_pid="PID-NXS",
                    name="Nexus-Prime",
                )

            async def process(self, payload: dict) -> dict:
                return {"routed": True, "payload": payload}
    """

    TIER = 3

    def __init__(
        self,
        aid: str,
        location_pid: str,
        name: str,
        peers: list[str] | None = None,
    ) -> None:
        self.dna = Tranc3DNA(aid=aid, location_pid=location_pid, name=name)
        self._peers: list[str] = peers or []
        self._running = False
        self._cycle_count = 0
        self._error_count = 0
        self._swot: SWOTSnapshot = SWOTSnapshot()
        self._powerups: dict[str, HubPowerUp] = {}
        self._in_home_hub: bool = False
        self._health_score: float = 1.0
        self._last_latency_ms: float = 0.0
        self._task: asyncio.Task | None = None

        # Adaptive subsystems — instantiate only when available
        self._gas: PressureBalancer | None = (
            PressureBalancer(self._peers) if _GAS_AVAILABLE and self._peers else None
        )
        self._liquid: LiquidRouter | None = (
            LiquidRouter(self._peers) if _LIQUID_AVAILABLE and self._peers else None
        )
        self._genetic: GeneticOptimizer | None = (
            GeneticOptimizer(fitness=LatencyThroughputFitness()) if _GENETIC_AVAILABLE else None
        )
        self._kinetic: dict[str, KineticEnergyTracker] = {}
        if _GAS_AVAILABLE:
            for peer in self._peers:
                self._kinetic[peer] = KineticEnergyTracker(worker=peer)

        logger.info("%s initialised (tier=%d, hub=%s)", self.dna, self.TIER, location_pid)

    # ------------------------------------------------------------------
    # Hub presence
    # ------------------------------------------------------------------

    def enter_hub(self) -> None:
        """Activate hub power-ups when the AI enters its home location."""
        self._in_home_hub = True
        for pu in self._powerups.values():
            pu.active = True
        logger.debug("%s entered home hub — %d power-ups active", self.dna, len(self._powerups))

    def leave_hub(self) -> None:
        """Deactivate hub power-ups when the AI leaves its home location."""
        self._in_home_hub = False
        for pu in self._powerups.values():
            pu.active = False
        logger.debug("%s left home hub", self.dna)

    def register_hub_powerup(self, powerup: HubPowerUp) -> None:
        """Register a hub-specific capability enhancement."""
        self._powerups[powerup.name] = powerup

    # ------------------------------------------------------------------
    # Adaptive routing
    # ------------------------------------------------------------------

    def record_peer_metrics(
        self, peer: str, rps: float, latency_ms: float, queue: int = 0, slots: int = 0,
    ) -> None:
        """Feed live metrics into the gas/kinetic subsystem."""
        self._last_latency_ms = latency_ms
        if self._gas:
            self._gas.observe(peer, rps=rps, latency_ms=latency_ms, queue=queue, slots=slots)
        if peer in self._kinetic:
            self._kinetic[peer].record(rps)

    def select_peer(self) -> str | None:
        """Gas-pressure-weighted peer selection (MB distribution)."""
        if not self._peers:
            return None
        if self._gas:
            try:
                result = self._gas.select()
                return result.selected
            except Exception:
                pass
        return self._peers[0]

    def liquid_route(self, signals: dict[str, float] | None = None) -> str | None:
        """LTC ODE-governed routing across peers."""
        if not self._peers:
            return None
        if self._liquid:
            try:
                result = self._liquid.route(signals)
                return result.target
            except Exception:
                pass
        return self._peers[0]

    # ------------------------------------------------------------------
    # Genetic self-optimisation
    # ------------------------------------------------------------------

    async def evolve(self, generations: int = 30, pop_size: int = 20) -> dict[str, Any]:
        """Run async NSGA-II genetic optimisation. Returns best config."""
        if not self._genetic:
            return {}
        try:
            result = await self._genetic.evolve(generations=generations, pop_size=pop_size)
            logger.info("%s evolved: best=%s", self.dna, result.best_fitness)
            return result.best_config
        except Exception as exc:
            logger.warning("%s evolution failed: %s", self.dna, exc)
            return {}

    # ------------------------------------------------------------------
    # SWOT self-assessment
    # ------------------------------------------------------------------

    def assess_swot(self) -> SWOTSnapshot:
        """Run a live SWOT self-assessment based on current metrics."""
        snap = SWOTSnapshot()

        # Strengths
        if self._health_score > 0.8:
            snap.strengths.append("High health score")
        if self._in_home_hub:
            snap.strengths.append("Operating within home hub — full power-ups active")
        if _GAS_AVAILABLE:
            snap.strengths.append("Gas-pressure adaptive routing active")
        if _LIQUID_AVAILABLE:
            snap.strengths.append("Liquid time-constant routing active")
        if _GENETIC_AVAILABLE:
            snap.strengths.append("Genetic self-optimisation available")

        # Weaknesses
        if self._error_count > 5:
            snap.weaknesses.append(f"Elevated error count: {self._error_count}")
        if self._last_latency_ms > 500:
            snap.weaknesses.append(f"High latency: {self._last_latency_ms:.0f}ms")
        if not self._peers:
            snap.weaknesses.append("No peer routing targets registered")

        # Opportunities
        if not _GAS_AVAILABLE:
            snap.opportunities.append("Install shared_core.gas for gas-pressure routing")
        if not _GENETIC_AVAILABLE:
            snap.opportunities.append("Install shared_core.genetics for parameter evolution")
        if self._cycle_count > 100 and not self._in_home_hub:
            snap.opportunities.append("Return to home hub for power-up boost")

        # Threats
        if self._health_score < 0.4:
            snap.threats.append("Critical health degradation — escalate to Prime")
        if self._gas and self._gas.system_temperature() > 1000:
            snap.threats.append("System pressure critical — consider scale-out")

        self._swot = snap
        return snap

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the AI cycle loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._cycle_loop(), name=f"tranc3_{self.dna.aid}")
        logger.info("%s started", self.dna)

    async def stop(self) -> None:
        """Stop the AI cycle loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected — task was cancelled by us
        logger.info("%s stopped after %d cycles", self.dna, self._cycle_count)

    async def _cycle_loop(self) -> None:
        """Internal heartbeat — override `on_cycle()` for custom logic."""
        while self._running:
            try:
                await self.on_cycle()
                self._cycle_count += 1
                self._health_score = min(1.0, self._health_score + 0.01)
                await asyncio.sleep(self._cycle_interval())
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._error_count += 1
                self._health_score = max(0.0, self._health_score - 0.1)
                logger.error("%s cycle error: %s", self.dna, exc)
                await asyncio.sleep(5.0)

    def _cycle_interval(self) -> float:
        """Adaptive cycle interval — increases under load, minimum 1s."""
        if self._gas:
            temp = self._gas.system_temperature()
            return max(1.0, min(30.0, temp / 100.0))
        return 5.0

    # ------------------------------------------------------------------
    # Override points
    # ------------------------------------------------------------------

    async def on_cycle(self) -> None:  # noqa: B027 - optional override hook
        """Called on every heartbeat cycle. Override for periodic work."""
        return None

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process an incoming request payload. Override in concrete classes."""
        raise NotImplementedError(f"{self.dna} must implement process()")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "aid": self.dna.aid,
            "name": self.dna.name,
            "tier": self.TIER,
            "location_pid": self.dna.location_pid,
            "running": self._running,
            "in_home_hub": self._in_home_hub,
            "health_score": round(self._health_score, 3),
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "peers": self._peers,
            "powerups": {k: v.active for k, v in self._powerups.items()},
            "gas_available": _GAS_AVAILABLE,
            "liquid_available": _LIQUID_AVAILABLE,
            "genetic_available": _GENETIC_AVAILABLE,
        }

    def __repr__(self) -> str:
        return f"<Tranc3 name={self.dna.name!r} tier={self.TIER} hub={self.dna.location_pid!r}>"
