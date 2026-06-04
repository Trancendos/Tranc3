"""
TrancOne — Tier 1 Orchestrator Base Template
=============================================
Base class for the three Tier 1 Orchestrators in the Trancendos platform.

Tier 1 Orchestrators are the highest autonomous AI authority — they govern
all Tier 2 Primes across all Pillars. There are exactly three instances:

  1. Cornelius McIntyre   — Primary AI Orchestrator (always on)
  2. The Queen            — Data/Swarm Orchestrator (always on)
  3. tAImra               — User Personal Assistant (opt-in, off by default)

As Sovereign-level entities, Orchestrators hold the highest HIL-A authority,
can perform emergency stops across the entire ecosystem, and are responsible
for cross-pillar coordination, platform-wide SWOT, and forensic deep-dives.

Design principles:
  - Sovereign governance: manages all T2ance Primes across all Pillars
  - Emergency stop: hard-halt any Prime and cascade to its managed AIs
  - HIL-A highest authority: final approver for all escalated decisions
  - Ecosystem SWOT: platform-wide strategic assessment
  - Gas + Liquid + Genetic: all adaptive subsystems at full orchestrator scale
  - tAImra gate: third orchestrator activates only when user explicitly enables
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .t2ance_base import HILARequest, T2ance
from .tranc3_base import SWOTSnapshot

logger = logging.getLogger(__name__)

try:
    from shared_core.genetics.fitness import LatencyThroughputFitness
    from shared_core.genetics.optimizer import GeneticOptimizer

    _GENETIC_AVAILABLE = True
except ImportError:
    _GENETIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Orchestrator identity
# ---------------------------------------------------------------------------

ORCHESTRATOR_SLOTS = {
    1: "Cornelius McIntyre",  # Primary AI orchestrator
    2: "The Queen",  # Data/Swarm orchestrator
    3: "tAImra",  # User assistant (off by default)
}


@dataclass(frozen=True)
class TrancOneDNA:
    """Immutable identity for a Tier 1 Orchestrator."""

    aid: str
    name: str
    slot: int  # 1, 2, or 3
    tier: int = 1
    strand_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    opt_in_required: bool = False  # True for tAImra (slot 3)

    def __str__(self) -> str:
        return f"TrancOne[{self.name}:slot{self.slot}]"


# ---------------------------------------------------------------------------
# Emergency stop record
# ---------------------------------------------------------------------------


@dataclass
class EmergencyStopRecord:
    """Record of an emergency stop action."""

    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    target_aid: str = ""
    reason: str = ""
    initiated_by: str = ""
    initiated_at: float = field(default_factory=time.monotonic)
    cascaded_to: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TrancOne base class
# ---------------------------------------------------------------------------


class TrancOne:
    """
    Tier 1 Orchestrator — Sovereign AI base for the Trancendos platform.

    Sub-class and set `slot` to 1 (Cornelius), 2 (The Queen), or 3 (tAImra).
    Slot 3 (tAImra) must be explicitly activated via `activate()`.

    Example::

        class CorneliusMcIntyre(TrancOne):
            def __init__(self):
                super().__init__(
                    aid="AID-LMN-01",
                    name="Cornelius McIntyre",
                    slot=1,
                )
    """

    TIER = 1

    def __init__(
        self,
        aid: str,
        name: str,
        slot: int,
        opt_in_required: bool = False,
    ) -> None:
        if slot not in (1, 2, 3):
            raise ValueError(f"TrancOne slot must be 1, 2, or 3 — got {slot}")
        canonical = ORCHESTRATOR_SLOTS[slot]
        if name != canonical:
            logger.warning(
                "TrancOne slot %d canonical name is %r; ignoring custom name %r — using canonical.",
                slot,
                canonical,
                name,
            )
        self.dna = TrancOneDNA(aid=aid, name=canonical, slot=slot, opt_in_required=slot == 3)
        self._primes: dict[str, T2ance] = {}
        self._running = False
        self._active = slot != 3  # tAImra (slot 3) starts inactive; requires explicit activate()
        self._cycle_count = 0
        self._error_count = 0
        self._swot: SWOTSnapshot = SWOTSnapshot()
        self._health_score: float = 1.0
        self._emergency_stops: list[EmergencyStopRecord] = []
        self._hila_final: list[HILARequest] = []
        self._task: asyncio.Task | None = None

        self._genetic: GeneticOptimizer | None = (
            GeneticOptimizer(fitness=LatencyThroughputFitness()) if _GENETIC_AVAILABLE else None
        )

        logger.info(
            "%s initialised (tier=%d, slot=%d, active=%s)",
            self.dna,
            self.TIER,
            slot,
            self._active,
        )

    # ------------------------------------------------------------------
    # tAImra activation gate
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Activate this orchestrator (required for tAImra / slot 3)."""
        self._active = True
        logger.info("%s activated", self.dna)

    def deactivate(self) -> None:
        """Deactivate this orchestrator (returns tAImra to dormant state)."""
        self._active = False
        logger.info("%s deactivated", self.dna)

    @property
    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------
    # Prime registry
    # ------------------------------------------------------------------

    def register_prime(self, prime: T2ance) -> None:
        """Register a Tier 2 Prime under orchestrator governance."""
        self._primes[prime.dna.aid] = prime
        logger.debug("%s registered prime %s", self.dna, prime.dna)

    def deregister_prime(self, aid: str) -> None:
        self._primes.pop(aid, None)

    # ------------------------------------------------------------------
    # Emergency stop
    # ------------------------------------------------------------------

    async def emergency_stop(
        self,
        target_aid: str,
        reason: str,
        initiated_by: str = "orchestrator",
    ) -> EmergencyStopRecord:
        """Hard-stop a Prime and cascade to all its managed AIs."""
        record = EmergencyStopRecord(
            target_aid=target_aid,
            reason=reason,
            initiated_by=initiated_by,
        )
        prime = self._primes.get(target_aid)
        if prime:
            # prime.stop() cascades to its managed AIs internally
            record.cascaded_to.extend(prime._managed.keys())
            try:
                await prime.stop()
            except Exception as exc:
                logger.warning(
                    "%s emergency_stop cascade failed for %s: %s",
                    self.dna,
                    target_aid,
                    exc,
                )
        self._emergency_stops.append(record)
        logger.warning("%s EMERGENCY STOP: %s — reason: %s", self.dna, target_aid, reason)
        return record

    # ------------------------------------------------------------------
    # HIL-A final authority
    # ------------------------------------------------------------------

    def receive_escalated_hila(self, request: HILARequest) -> None:
        """Accept an escalated HIL-A request that exceeded Prime authority."""
        self._hila_final.append(request)
        logger.info("%s received escalated HIL-A: %s", self.dna, request.request_id)

    def decide_final_hila(self, request_id: str, approved: bool, reason: str | None = None) -> bool:
        """Render final decision on an escalated HIL-A request."""
        for req in self._hila_final:
            if req.request_id == request_id and req.approved is None:
                req.decide(approved, str(self.dna), reason)
                logger.info(
                    "%s final HIL-A %s: %s",
                    self.dna,
                    request_id,
                    "APPROVED" if approved else "REJECTED",
                )
                return True
        return False

    def pending_final_hila(self) -> list[HILARequest]:
        return [r for r in self._hila_final if r.approved is None]

    # ------------------------------------------------------------------
    # Ecosystem SWOT
    # ------------------------------------------------------------------

    def assess_ecosystem_swot(self) -> SWOTSnapshot:
        """Platform-wide strategic SWOT assessment across all Primes."""
        snap = SWOTSnapshot()

        healthy_primes = [p for p in self._primes.values() if p._health_score > 0.7]
        degraded_primes = [p for p in self._primes.values() if p._health_score < 0.4]
        total_managed = sum(len(p._managed) for p in self._primes.values())

        if healthy_primes:
            snap.strengths.append(f"{len(healthy_primes)}/{len(self._primes)} Primes healthy")
        if total_managed > 0:
            snap.strengths.append(f"{total_managed} Tier 3 AIs under ecosystem governance")
        if self._active:
            snap.strengths.append("Orchestrator active")

        if degraded_primes:
            snap.weaknesses.append(f"{len(degraded_primes)} Primes in critical state")
        if self.pending_final_hila():
            snap.weaknesses.append(
                f"{len(self.pending_final_hila())} escalated HIL-A decisions pending",
            )
        if self._emergency_stops:
            snap.weaknesses.append(
                f"{len(self._emergency_stops)} emergency stops recorded this session",
            )

        if not self._active and self.dna.slot == 3:
            snap.opportunities.append("tAImra can be activated for personal assistant mode")
        if not _GENETIC_AVAILABLE:
            snap.opportunities.append(
                "Install shared_core.genetics for ecosystem-level GA optimisation",
            )

        if self._health_score < 0.3:
            snap.threats.append(
                "CRITICAL: Orchestrator health failing — human intervention required",
            )
        if len(degraded_primes) > len(self._primes) / 2:
            snap.threats.append("CRITICAL: Majority of Primes degraded — systemic failure risk")

        self._swot = snap
        return snap

    # ------------------------------------------------------------------
    # Forensic deep-scan
    # ------------------------------------------------------------------

    def forensic_deep_scan(self) -> dict[str, Any]:
        """Full ecosystem forensic scan: Orchestrator → Primes → Lead AIs."""
        report: dict[str, Any] = {
            "orchestrator": str(self.dna),
            "scanned_at": time.monotonic(),
            "active": self._active,
            "health_score": self._health_score,
            "emergency_stops": len(self._emergency_stops),
            "pending_final_hila": len(self.pending_final_hila()),
            "primes": {},
            "alerts": [],
        }
        for aid, prime in self._primes.items():
            prime_scan = prime.forensic_scan()
            report["primes"][aid] = prime_scan
            report["alerts"].extend(prime_scan.get("alerts", []))
        return report

    # ------------------------------------------------------------------
    # Genetic orchestration
    # ------------------------------------------------------------------

    async def evolve_ecosystem(self, generations: int = 50, pop_size: int = 40) -> dict[str, Any]:
        """Run NSGA-II optimisation at the ecosystem level."""
        if not self._genetic:
            return {}
        try:
            result = await self._genetic.evolve(generations=generations, pop_size=pop_size)
            return result.best_config
        except Exception as exc:
            logger.warning("%s ecosystem evolution failed: %s", self.dna, exc)
            return {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running or not self._active:
            return
        self._running = True
        for prime in self._primes.values():
            await prime.start()
        self._task = asyncio.create_task(
            self._orchestrate_loop(),
            name=f"trance_one_{self.dna.aid}",
        )
        logger.info("%s orchestration started — %d Primes", self.dna, len(self._primes))

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected — task was cancelled by us
        await asyncio.gather(
            *[prime.stop() for prime in self._primes.values()],
            return_exceptions=True,
        )
        logger.info("%s orchestration stopped after %d cycles", self.dna, self._cycle_count)

    async def _orchestrate_loop(self) -> None:
        while self._running and self._active:
            try:
                await self.orchestrate()
                self._cycle_count += 1
                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._error_count += 1
                self._health_score = max(0.0, self._health_score - 0.1)
                logger.error("%s orchestrate error: %s", self.dna, exc)
                await asyncio.sleep(30.0)

    async def orchestrate(self) -> None:
        """Top-level orchestration cycle. Override for sovereign-level logic."""

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "aid": self.dna.aid,
            "name": self.dna.name,
            "tier": self.TIER,
            "slot": self.dna.slot,
            "active": self._active,
            "opt_in_required": self.dna.opt_in_required,
            "running": self._running,
            "health_score": round(self._health_score, 3),
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "managed_primes": list(self._primes.keys()),
            "emergency_stops": len(self._emergency_stops),
            "pending_final_hila": len(self.pending_final_hila()),
        }

    def __repr__(self) -> str:
        return f"<TrancOne name={self.dna.name!r} tier={self.TIER} slot={self.dna.slot} active={self._active}>"
