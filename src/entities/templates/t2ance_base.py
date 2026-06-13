"""
T2ance — Tier 2 Prime Base Template
======================================
Base class for all Tier 2 Prime AIs in the Trancendos platform.

Primes govern a Pillar domain and manage a set of Tier 3 Lead AIs. They
hold executive authority within their pillar, approve HIL-A actions that
exceed Tier 3 thresholds, and maintain ecosystem-wide health visibility.

Design principles:
  - Governance: manages a group of Tranc3 Lead AIs, coordinates cycles
  - HIL-A: human-in-the-loop approval gating for high-impact decisions
  - Forensic: deep diagnostic scanning of managed AIs
  - Genetic:  Pillar-level NSGA-II multi-objective optimisation
  - Liquid:   adaptive weighting of Lead AI workload
  - SWOT:     pillar-level strategic self-assessment
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .tranc3_base import SWOTSnapshot, Tranc3

logger = logging.getLogger(__name__)

try:
    from shared_core.genetics.fitness import LatencyThroughputFitness
    from shared_core.genetics.optimizer import GeneticOptimizer

    _GENETIC_AVAILABLE = True
except ImportError:
    _GENETIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# DNA
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class T2anceDNA:
    """Immutable identity record for a Tier 2 Prime."""

    aid: str
    pillar: str
    name: str
    tier: int = 2
    strand_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __str__(self) -> str:
        return f"T2ance[{self.name}@{self.pillar}]"


# ---------------------------------------------------------------------------
# HIL-A Approval gate
# ---------------------------------------------------------------------------


@dataclass
class HILARequest:
    """A pending Human-in-the-Loop Approval request."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    action_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    requester_aid: str = ""
    raised_at: float = field(default_factory=time.monotonic)
    approved: bool | None = None
    decided_at: float | None = None
    decided_by: str | None = None
    reason: str | None = None

    def age_seconds(self) -> float:
        return time.monotonic() - self.raised_at

    def decide(self, approved: bool, decided_by: str, reason: str | None = None) -> None:
        self.approved = approved
        self.decided_at = time.monotonic()
        self.decided_by = decided_by
        self.reason = reason


# ---------------------------------------------------------------------------
# T2ance base class
# ---------------------------------------------------------------------------


class T2ance:
    """
    Tier 2 Prime AI — governs a Pillar domain.

    Sub-class and override `govern()` for pillar-specific logic.

    Example::

        class ArchitecturalPrime(T2ance):
            def __init__(self):
                super().__init__(
                    aid="AID-NXS-00",
                    pillar="Architectural",
                    name="Nexus-Prime-Arch",
                )

            async def govern(self) -> None:
                # Pillar-specific governance cycle
                pass
    """

    TIER = 2

    def __init__(
        self,
        aid: str,
        pillar: str,
        name: str,
    ) -> None:
        self.dna = T2anceDNA(aid=aid, pillar=pillar, name=name)
        self._managed: dict[str, Tranc3] = {}
        self._hila_queue: list[HILARequest] = []
        self._running = False
        self._cycle_count = 0
        self._error_count = 0
        self._swot: SWOTSnapshot = SWOTSnapshot()
        self._health_score: float = 1.0
        self._task: asyncio.Task | None = None

        self._genetic: GeneticOptimizer | None = (
            GeneticOptimizer(fitness=LatencyThroughputFitness()) if _GENETIC_AVAILABLE else None
        )

        logger.info("%s initialised (tier=%d, pillar=%s)", self.dna, self.TIER, pillar)

    # ------------------------------------------------------------------
    # Managed AI registry
    # ------------------------------------------------------------------

    def register(self, ai: Tranc3) -> None:
        """Register a Tier 3 Lead AI under this Prime's governance."""
        self._managed[ai.dna.aid] = ai
        logger.debug("%s registered %s", self.dna, ai.dna)

    def deregister(self, aid: str) -> None:
        """Remove a Tier 3 AI from governance."""
        self._managed.pop(aid, None)

    # ------------------------------------------------------------------
    # HIL-A approval
    # ------------------------------------------------------------------

    def raise_hila(
        self, action_type: str, payload: dict[str, Any], requester_aid: str
    ) -> HILARequest:
        """Raise a HIL-A approval request. Returns the pending request."""
        req = HILARequest(action_type=action_type, payload=payload, requester_aid=requester_aid)
        self._hila_queue.append(req)
        logger.info("%s HIL-A raised: %s (id=%s)", self.dna, action_type, req.request_id)
        return req

    def decide_hila(
        self, request_id: str, approved: bool, decided_by: str, reason: str | None = None
    ) -> bool:
        """Approve or reject a pending HIL-A request."""
        for req in self._hila_queue:
            if req.request_id == request_id and req.approved is None:
                req.decide(approved, decided_by, reason)
                logger.info(
                    "%s HIL-A %s: %s", self.dna, request_id, "APPROVED" if approved else "REJECTED"
                )
                return True
        return False

    def pending_hila(self) -> list[HILARequest]:
        """Return all pending (undecided) HIL-A requests."""
        return [r for r in self._hila_queue if r.approved is None]

    # ------------------------------------------------------------------
    # Forensic assessment
    # ------------------------------------------------------------------

    def forensic_scan(self) -> dict[str, Any]:
        """Deep diagnostic scan of all managed Tier 3 AIs."""
        report: dict[str, Any] = {
            "prime": str(self.dna),
            "scanned_at": time.monotonic(),
            "managed_count": len(self._managed),
            "ais": {},
            "alerts": [],
        }
        for aid, ai in self._managed.items():
            st = ai.status()
            report["ais"][aid] = st
            if st["health_score"] < 0.4:
                report["alerts"].append(f"{aid} critical health: {st['health_score']:.2f}")
            if st["error_count"] > 10:
                report["alerts"].append(f"{aid} high error count: {st['error_count']}")
        return report

    # ------------------------------------------------------------------
    # SWOT
    # ------------------------------------------------------------------

    def assess_swot(self) -> SWOTSnapshot:
        """Pillar-level SWOT assessment."""
        snap = SWOTSnapshot()

        healthy = [ai for ai in self._managed.values() if ai._health_score > 0.7]
        degraded = [ai for ai in self._managed.values() if ai._health_score < 0.4]

        if healthy:
            snap.strengths.append(f"{len(healthy)}/{len(self._managed)} managed AIs healthy")
        if not self.pending_hila():
            snap.strengths.append("No pending HIL-A approvals")
        if _GENETIC_AVAILABLE:
            snap.strengths.append("Pillar-level genetic optimisation available")

        if degraded:
            snap.weaknesses.append(f"{len(degraded)} managed AIs in critical state")
        if len(self.pending_hila()) > 5:
            snap.weaknesses.append(f"HIL-A backlog: {len(self.pending_hila())} items")

        if not self._managed:
            snap.opportunities.append("Register Tier 3 Lead AIs for governance")
        if self._error_count > 0:
            snap.opportunities.append("Investigate error patterns for systemic fixes")

        if self._health_score < 0.3:
            snap.threats.append("Prime health critical — escalate to Sovereign")

        self._swot = snap
        return snap

    # ------------------------------------------------------------------
    # Genetic optimisation
    # ------------------------------------------------------------------

    async def evolve_pillar(self, generations: int = 40, pop_size: int = 30) -> dict[str, Any]:
        """Run NSGA-II optimisation at the pillar level."""
        if not self._genetic:
            return {}
        try:
            result = await self._genetic.evolve(generations=generations, pop_size=pop_size)
            return result.best_config
        except Exception as exc:
            logger.warning("%s pillar evolution failed: %s", self.dna, exc)
            return {}

    # ------------------------------------------------------------------
    # Coordinated cycle
    # ------------------------------------------------------------------

    async def coordinate(self) -> None:
        """Trigger one governance cycle across managed Tier 3 AIs not yet started."""
        # Skip AIs whose own _cycle_loop is already running to avoid re-entrancy
        tasks = [ai.on_cycle() for ai in self._managed.values() if not ai._running]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    self._error_count += 1
                    self._health_score = max(0.0, self._health_score - 0.05)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the Prime governance loop and all managed AIs."""
        if self._running:
            return
        self._running = True
        for ai in self._managed.values():
            await ai.start()
        self._task = asyncio.create_task(self._govern_loop(), name=f"t2ance_{self.dna.aid}")
        logger.info("%s started — governing %d AIs", self.dna, len(self._managed))

    async def stop(self) -> None:
        """Stop the Prime and all managed AIs."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected — task was cancelled by us
        await asyncio.gather(
            *[ai.stop() for ai in self._managed.values()],
            return_exceptions=True,
        )
        logger.info("%s stopped after %d cycles", self.dna, self._cycle_count)

    async def _govern_loop(self) -> None:
        while self._running:
            try:
                await self.govern()
                await self.coordinate()
                self._cycle_count += 1
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._error_count += 1
                self._health_score = max(0.0, self._health_score - 0.1)
                logger.error("%s govern error: %s", self.dna, exc)
                await asyncio.sleep(15.0)

    async def govern(self) -> None:
        """Pillar governance cycle. Override for domain-specific logic."""

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "aid": self.dna.aid,
            "name": self.dna.name,
            "tier": self.TIER,
            "pillar": self.dna.pillar,
            "running": self._running,
            "health_score": round(self._health_score, 3),
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "managed_ais": list(self._managed.keys()),
            "pending_hila": len(self.pending_hila()),
        }

    def __repr__(self) -> str:
        return f"<T2ance name={self.dna.name!r} tier={self.TIER} pillar={self.dna.pillar!r}>"
