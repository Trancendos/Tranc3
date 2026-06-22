"""Cellular Automaton for service health propagation modelling.

Each Trancendos service is a cell with health state [0.0, 1.0].
Transition rules model how failures propagate through dependencies.

Rule set (biologically inspired — similar to Conway's Life):
  - Healthy cell with ≥2 failing neighbours → degrades (neighbour pressure)
  - Degraded cell with 0 failing neighbours → recovers slowly
  - Dead cell (0.0) with all healthy neighbours → begins recovery
  - Healthy cell in isolation → stays healthy

This gives emergent behaviour: isolated failures recover; cascades propagate.
Used by The Observatory health-aggregator to predict failure cascades.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ServiceCell:
    name: str
    health: float = 1.0  # 1.0 = fully healthy, 0.0 = dead
    neighbours: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)

    @property
    def state(self) -> str:
        if self.health >= 0.8:
            return "healthy"
        if self.health >= 0.4:
            return "degraded"
        return "dead"


class ServiceHealthCA:
    """Cellular automaton over the Trancendos service graph.

    Services and their dependency edges are the grid topology.
    Call `tick()` each monitoring cycle to propagate health states.
    """

    # Default dependency graph — matches CLAUDE.md port assignments
    DEFAULT_TOPOLOGY: Dict[str, List[str]] = {
        "tranc3-backend": ["infinity-auth", "infinity-ws", "the-grid"],
        "infinity-auth": ["tranc3-backend", "users-service"],
        "infinity-ws": ["tranc3-backend", "queue-service"],
        "the-grid": ["tranc3-backend", "workflow-engine-service"],
        "users-service": ["infinity-auth", "audit-service"],
        "queue-service": ["infinity-ws", "notifications"],
        "payments-service": ["tranc3-backend", "audit-service"],
        "audit-service": [],
        "notifications": ["audit-service"],
        "monitoring": ["tranc3-backend"],
        "vault-service": ["tranc3-backend"],
        "workflow-engine-service": ["the-grid"],
    }

    def __init__(self, topology: Optional[Dict[str, List[str]]] = None) -> None:
        topo = topology or self.DEFAULT_TOPOLOGY
        self.cells: Dict[str, ServiceCell] = {
            name: ServiceCell(name=name, neighbours=list(neighbours))
            for name, neighbours in topo.items()
        }

    def update_health(self, service: str, health: float) -> None:
        if service in self.cells:
            self.cells[service].health = max(0.0, min(1.0, health))
            self.cells[service].last_updated = time.time()

    def tick(self, decay_rate: float = 0.05, recovery_rate: float = 0.02) -> Dict[str, str]:
        """Run one CA generation. Returns new state map."""
        new_healths: Dict[str, float] = {}

        for name, cell in self.cells.items():
            neighbours = [self.cells[n] for n in cell.neighbours if n in self.cells]
            if not neighbours:
                new_healths[name] = cell.health
                continue

            failing = sum(1 for n in neighbours if n.health < 0.5)
            total = len(neighbours)
            avg_neighbour_health = sum(n.health for n in neighbours) / total

            if cell.health >= 0.8:
                # Healthy: pressure from failing neighbours
                pressure = failing / max(total, 1)
                new_h = cell.health - (pressure * decay_rate * 3)
            elif cell.health >= 0.4:
                # Degraded: recover if neighbours healthy, degrade further if not
                if avg_neighbour_health > 0.7:
                    new_h = cell.health + recovery_rate
                else:
                    new_h = cell.health - (decay_rate * failing / max(total, 1))
            else:
                # Dead: slow recovery if neighbours healthy
                if avg_neighbour_health > 0.8:
                    new_h = cell.health + recovery_rate * 0.5
                else:
                    new_h = cell.health

            new_healths[name] = max(0.0, min(1.0, new_h))

        for name, h in new_healths.items():
            self.cells[name].health = h

        return {name: cell.state for name, cell in self.cells.items()}

    def at_risk(self, threshold: float = 0.5) -> List[str]:
        """Services predicted to fail within next 2 ticks."""
        at_risk = []
        for name, cell in self.cells.items():
            if cell.health < threshold:
                continue
            # Count failing neighbours
            failing = sum(
                1 for n in cell.neighbours if n in self.cells and self.cells[n].health < 0.5
            )
            if failing >= 2:
                at_risk.append(name)
        return at_risk

    def snapshot(self) -> Dict[str, Dict]:
        return {
            name: {"health": round(cell.health, 3), "state": cell.state}
            for name, cell in self.cells.items()
        }
