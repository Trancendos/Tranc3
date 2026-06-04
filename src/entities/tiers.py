"""
Trancendos Ecosystem — Tier 1 (Sovereign) & Tier 2 (Prime) Classes

Custom hierarchy:
  Tier 1 — Sovereign  = System-wide authority, ultimate orchestrator
  Tier 2 — Prime      = Executive AI authority, cross-domain coordinator
  Tier 3 — AI         = Lead AI / domain orchestrator (existing AI class)
  Tier 4 — Agent      = Autonomous microservice (existing Agent class)
  Tier 5 — Bot        = Stateless nanoservice / function (existing Bot class)

These classes provide:
  - Lifecycle hooks via LifecycleEmitter
  - HIL-A approval/rejection at their tier level
  - Health check aggregation down the hierarchy
  - Coordinated cycle execution across subordinates
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .lifecycle import LifecycleEmitter, LifecycleEvent


@dataclass
class HILAApproval:
    """HIL-A approval decision from a tier authority."""

    action_id: str
    approved_by: str
    tier: int
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    final: bool = False  # True for Sovereign rejections (cannot be overridden)


@dataclass
class HealthReport:
    """Standardised health check report for any tier."""

    name: str
    tier: int
    running: bool
    emergency_stopped: bool = False
    managed_entities: int = 0
    total_agents: int = 0
    total_bots: int = 0
    sub_healths: List[Dict[str, Any]] = field(default_factory=list)


class Prime:
    """
    Tier 2 — Executive AI Authority

    A Prime coordinates multiple Tier 3 AIs across its domain (pillar).
    It can approve/reject HIL-A actions at Tier 2 level (for Tier 3+ actions).

    In the 43-platform entity model, Primes correspond to the named
    Prime individuals (e.g., "Cornelius MacIntyre", "Dorris Fontaine")
    who oversee multiple locations within a pillar.
    """

    def __init__(
        self,
        prime_id: str = "",
        name: str = "",
        pillar: str = "",
    ) -> None:
        self.id = prime_id
        self.name = name
        self.pillar = pillar
        self.tier = 2
        self.created_at = datetime.utcnow()
        self._running = False

        # Managed Tier 3 AIs — key is AID
        self._ais: Dict[str, Any] = {}  # Avoid circular import — accepts AI-like objects

        # HIL-A: Tier 2 can approve Tier 3, 4, 5 actions
        self.can_approve_tiers = [3, 4, 5]

        # Lifecycle hooks
        self.lifecycle = LifecycleEmitter(name or prime_id)
        self.lifecycle.emit_lifecycle_sync(
            LifecycleEvent.INIT, {"id": self.id, "tier": 2, "pillar": pillar},
        )

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start this Prime and all managed AIs."""
        if self._running:
            return
        self._running = True
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.START,
            {
                "managedAIs": len(self._ais),
            },
        )
        # Start all managed AIs (if they have a start method)
        for ai in self._ais.values():
            if hasattr(ai, "start") and asyncio.iscoroutinefunction(ai.start):
                try:
                    await ai.start()
                except Exception as e:
                    await self.lifecycle.emit_lifecycle(
                        LifecycleEvent.ERROR,
                        {
                            "aiId": getattr(ai, "id", "unknown"),
                            "phase": "start",
                            "error": str(e),
                        },
                    )

    async def stop(self) -> None:
        """Stop this Prime and all managed AIs."""
        if not self._running:
            return
        self._running = False
        for ai in self._ais.values():
            if hasattr(ai, "stop") and asyncio.iscoroutinefunction(ai.stop):
                try:
                    await ai.stop()
                except Exception as e:
                    await self.lifecycle.emit_lifecycle(
                        LifecycleEvent.ERROR,
                        {
                            "aiId": getattr(ai, "id", "unknown"),
                            "phase": "stop",
                            "error": str(e),
                        },
                    )
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.STOP,
            {
                "managedAIs": len(self._ais),
            },
        )

    def register_ai(self, ai: Any) -> None:
        """Register a Tier 3 AI under this Prime's domain."""
        ai_id = getattr(ai, "id", str(id(ai)))
        self._ais[ai_id] = ai

    def get_ai(self, ai_id: str) -> Optional[Any]:
        """Get a managed AI by AID."""
        return self._ais.get(ai_id)

    def list_ai_ids(self) -> List[str]:
        """List all managed AI IDs."""
        return list(self._ais.keys())

    def list_all_agent_ids(self) -> List[str]:
        """List all agent IDs across all managed AIs."""
        agents: List[str] = []
        for ai in self._ais.values():
            if hasattr(ai, "listAgentIds"):
                agents.extend(ai.listAgentIds())
            elif hasattr(ai, "list_agent_ids"):
                agents.extend(ai.list_agent_ids())
        return agents

    async def run_coordinated_cycle(self, observation: Any) -> Dict[str, Any]:
        """Run a coordinated cycle across all managed AIs."""
        results: Dict[str, Any] = {}
        for ai_id, ai in self._ais.items():
            try:
                if hasattr(ai, "runAllAgentCycles"):
                    results[ai_id] = await ai.runAllAgentCycles(observation)
                elif hasattr(ai, "run_all_agent_cycles"):
                    results[ai_id] = await ai.run_all_agent_cycles(observation)
            except Exception as e:
                await self.lifecycle.emit_lifecycle(
                    LifecycleEvent.ERROR,
                    {
                        "aiId": ai_id,
                        "phase": "runCoordinatedCycle",
                        "error": str(e),
                    },
                )
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.CYCLE,
            {
                "aisProcessed": len(results),
            },
        )
        return results

    def approve_action(self, action_id: str, reason: str = "Approved by Prime") -> HILAApproval:
        """HIL-A: Approve an action on behalf of this Prime (Tier 2 authority)."""
        return HILAApproval(
            action_id=action_id,
            approved_by=self.id,
            tier=self.tier,
            reason=reason,
        )

    def reject_action(self, action_id: str, reason: str) -> HILAApproval:
        """HIL-A: Reject an action on behalf of this Prime."""
        return HILAApproval(
            action_id=action_id,
            approved_by=self.id,
            tier=self.tier,
            reason=reason,
        )

    def health_check(self) -> HealthReport:
        """Get health summary of all managed AIs."""
        sub_healths: List[Dict[str, Any]] = []
        total_agents = 0
        total_bots = 0

        for ai in self._ais.values():
            ai_running = getattr(ai, "running", False)
            ai_agents = 0
            ai_bots = 0
            if hasattr(ai, "listAgentIds"):
                ai_agents = len(ai.listAgentIds())
            if hasattr(ai, "listBotNames"):
                ai_bots = len(ai.listBotNames())
            total_agents += ai_agents
            total_bots += ai_bots
            sub_healths.append(
                {
                    "id": getattr(ai, "id", "unknown"),
                    "running": ai_running,
                    "agents": ai_agents,
                    "bots": ai_bots,
                },
            )

        return HealthReport(
            name=self.name,
            tier=self.tier,
            running=self._running,
            managed_entities=len(self._ais),
            total_agents=total_agents,
            total_bots=total_bots,
            sub_healths=sub_healths,
        )


class Sovereign:
    """
    Tier 1 — System-Wide Authority

    The Sovereign is the ultimate orchestrator of the entire Tranc3 ecosystem.
    It oversees all Primes (Tier 2) and has direct access to AIs (Tier 3)
    for emergency override.

    Key responsibilities:
      - Emergency stop: Halts all cycles across the ecosystem
      - HIL-A Tier 1 approval: The highest approval authority
      - Ecosystem-wide health aggregation
      - Coordinated cycle execution across all Primes
    """

    def __init__(
        self,
        sovereign_id: str = "SOVEREIGN-001",
        name: str = "The Sovereign",
    ) -> None:
        self.id = sovereign_id
        self.name = name
        self.tier = 1
        self.created_at = datetime.utcnow()
        self._running = False
        self._emergency_stop = False

        # Managed Tier 2 Primes
        self._primes: Dict[str, Prime] = {}

        # Direct Tier 3 AI references for emergency access
        self._ais: Dict[str, Any] = {}

        # HIL-A: Sovereign can approve any tier
        self.can_approve_tiers = [0, 1, 2, 3, 4, 5]

        # Lifecycle hooks
        self.lifecycle = LifecycleEmitter(name)
        self.lifecycle.emit_lifecycle_sync(LifecycleEvent.INIT, {"id": self.id, "tier": 1})

    @property
    def running(self) -> bool:
        return self._running

    @property
    def emergency_stopped(self) -> bool:
        return self._emergency_stop

    async def start(self) -> None:
        """Start the Sovereign and all managed Primes."""
        if self._running:
            return
        self._running = True
        self._emergency_stop = False
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.START,
            {
                "managedPrimes": len(self._primes),
            },
        )
        for prime in self._primes.values():
            try:
                await prime.start()
            except Exception as e:
                await self.lifecycle.emit_lifecycle(
                    LifecycleEvent.ERROR,
                    {
                        "primeId": prime.id,
                        "phase": "start",
                        "error": str(e),
                    },
                )

    async def stop(self) -> None:
        """Stop the Sovereign and all managed Primes."""
        if not self._running:
            return
        self._running = False
        for prime in self._primes.values():
            try:
                await prime.stop()
            except Exception as e:
                await self.lifecycle.emit_lifecycle(
                    LifecycleEvent.ERROR,
                    {
                        "primeId": prime.id,
                        "phase": "stop",
                        "error": str(e),
                    },
                )
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.STOP,
            {
                "managedPrimes": len(self._primes),
            },
        )

    def register_prime(self, prime: Prime) -> None:
        """Register a Tier 2 Prime under this Sovereign."""
        self._primes[prime.id] = prime

    def register_ai(self, ai: Any) -> None:
        """Register a Tier 3 AI for direct emergency access."""
        ai_id = getattr(ai, "id", str(id(ai)))
        self._ais[ai_id] = ai

    def get_prime(self, prime_id: str) -> Optional[Prime]:
        """Get a managed Prime by ID."""
        return self._primes.get(prime_id)

    def get_ai(self, ai_id: str) -> Optional[Any]:
        """Get a directly registered AI by AID."""
        return self._ais.get(ai_id)

    def list_prime_ids(self) -> List[str]:
        """List all managed Prime IDs."""
        return list(self._primes.keys())

    def list_all_ai_ids(self) -> List[str]:
        """List all AIs across all managed Primes."""
        ais: List[str] = []
        for prime in self._primes.values():
            ais.extend(prime.list_ai_ids())
        # Include directly registered AIs
        for ai_id in self._ais:
            if ai_id not in ais:
                ais.append(ai_id)
        return ais

    def approve_action(self, action_id: str, reason: str = "Sovereign decree") -> HILAApproval:
        """HIL-A: Sovereign approval — the highest authority in the system."""
        return HILAApproval(
            action_id=action_id,
            approved_by=self.id,
            tier=self.tier,
            reason=reason,
        )

    def reject_action(self, action_id: str, reason: str) -> HILAApproval:
        """HIL-A: Sovereign rejection — cannot be overridden."""
        return HILAApproval(
            action_id=action_id,
            approved_by=self.id,
            tier=self.tier,
            reason=reason,
            final=True,
        )

    async def emergency_stop(self, reason: str = "Manual emergency stop") -> None:
        """EMERGENCY STOP — halts all cycles across the entire ecosystem."""
        self._emergency_stop = True
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.ERROR,
            {
                "type": "emergency_stop",
                "reason": reason,
            },
        )
        # Stop all Primes
        for prime in self._primes.values():
            try:
                await prime.stop()
            except Exception:
                pass
        # Stop all directly registered AIs
        for ai in self._ais.values():
            if hasattr(ai, "stop") and asyncio.iscoroutinefunction(ai.stop):
                try:
                    await ai.stop()
                except Exception:
                    pass

    async def resume_from_emergency(self) -> None:
        """Resume from emergency stop."""
        self._emergency_stop = False
        await self.start()

    async def run_ecosystem_cycle(self, observation: Any) -> Dict[str, Any]:
        """Run a full ecosystem cycle through all Primes."""
        if self._emergency_stop:
            raise RuntimeError("Cannot run ecosystem cycle — emergency stop is active")

        results: Dict[str, Any] = {}
        for prime_id, prime in self._primes.items():
            try:
                results[prime_id] = await prime.run_coordinated_cycle(observation)
            except Exception as e:
                await self.lifecycle.emit_lifecycle(
                    LifecycleEvent.ERROR,
                    {
                        "primeId": prime_id,
                        "phase": "runEcosystemCycle",
                        "error": str(e),
                    },
                )
        await self.lifecycle.emit_lifecycle(
            LifecycleEvent.CYCLE,
            {
                "primesProcessed": len(results),
            },
        )
        return results

    def health_check(self) -> HealthReport:
        """Full ecosystem health check."""
        prime_healths: List[Dict[str, Any]] = []
        total_ais = 0
        total_agents = 0
        total_bots = 0

        for prime in self._primes.values():
            ph = prime.health_check()
            total_ais += ph.managed_entities
            total_agents += ph.total_agents
            total_bots += ph.total_bots
            prime_healths.append(
                {
                    "name": ph.name,
                    "tier": ph.tier,
                    "running": ph.running,
                    "managedAIs": ph.managed_entities,
                    "totalAgents": ph.total_agents,
                    "totalBots": ph.total_bots,
                    "subHealths": ph.sub_healths,
                },
            )

        return HealthReport(
            name=self.name,
            tier=self.tier,
            running=self._running,
            emergency_stopped=self._emergency_stop,
            managed_entities=len(self._primes),
            total_agents=total_agents,
            total_bots=total_bots,
            sub_healths=prime_healths,
        )
