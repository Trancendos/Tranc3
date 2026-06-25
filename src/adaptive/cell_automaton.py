"""
src/adaptive/cell_automaton.py
==============================
Cellular automaton for self-healing service topology.

Rules (Conway-like adapted for service health):
- HEALTHY  : remains healthy if majority of neighbours are healthy
- STRESSED : health_score < 0.7; propagates stress to neighbours
- FAILING  : health_score < 0.4; triggers regeneration signal
- DEAD     : health_score == 0; cell auto-restarts after grace period
- REGENERATING: recovering from DEAD; transitions to HEALTHY if health_score > 0.6

Used by health-aggregator to auto-restart failing services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CellState(str, Enum):
    HEALTHY = "healthy"
    STRESSED = "stressed"
    FAILING = "failing"
    DEAD = "dead"
    REGENERATING = "regenerating"


@dataclass
class ServiceCell:
    service_name: str
    state: CellState = CellState.HEALTHY
    neighbors: list[str] = field(default_factory=list)
    health_score: float = 1.0  # 0.0 - 1.0
    generation: int = 0
    last_state_change: float = field(default_factory=time.time)
    error_count: int = 0

    def _update_state(self) -> None:
        """Derive state from health_score."""
        if self.health_score >= 0.8:
            self.state = CellState.HEALTHY
        elif self.health_score >= 0.6:
            self.state = CellState.STRESSED
        elif self.health_score > 0.0:
            self.state = CellState.FAILING
        else:
            if self.state == CellState.DEAD:
                pass  # stay dead until healed externally
            else:
                self.state = CellState.DEAD
                self.last_state_change = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "state": self.state.value,
            "health_score": self.health_score,
            "generation": self.generation,
            "error_count": self.error_count,
            "neighbors": self.neighbors,
        }


class CellAutomaton:
    """Self-healing service topology based on cellular automaton rules."""

    STRESS_PROPAGATION_THRESHOLD = 0.5
    DEAD_GRACE_SECONDS = 30.0
    REGENERATION_SCORE = 0.3

    def __init__(self) -> None:
        self._cells: dict[str, ServiceCell] = {}
        self._generation: int = 0

    def add_cell(self, service_name: str, neighbors: list[str] | None = None) -> ServiceCell:
        cell = ServiceCell(service_name=service_name, neighbors=neighbors or [])
        self._cells[service_name] = cell
        return cell

    def update_health(self, service_name: str, health_score: float, error_count: int = 0) -> None:
        """Update health score for a service cell."""
        if service_name not in self._cells:
            self.add_cell(service_name)
        cell = self._cells[service_name]
        old_state = cell.state
        cell.health_score = max(0.0, min(1.0, health_score))
        cell.error_count = error_count
        cell._update_state()
        if cell.state != old_state:
            cell.last_state_change = time.time()

    def tick(self) -> dict[str, CellState]:
        """Advance one generation. Returns new state map."""
        self._generation += 1
        new_states: dict[str, CellState] = {}

        for name, cell in self._cells.items():
            cell.generation = self._generation

            # Dead cell — check grace period for auto-regeneration
            if cell.state == CellState.DEAD:
                elapsed = time.time() - cell.last_state_change
                if elapsed >= self.DEAD_GRACE_SECONDS:
                    cell.state = CellState.REGENERATING
                    cell.health_score = self.REGENERATION_SCORE
                    cell.last_state_change = time.time()
                new_states[name] = cell.state
                continue

            # Regenerating — promote to healthy if score rising
            if cell.state == CellState.REGENERATING:
                cell.health_score = min(1.0, cell.health_score + 0.1)
                cell._update_state()
                new_states[name] = cell.state
                continue

            # Propagate stress from neighbours
            neighbour_states = [self._cells[n].state for n in cell.neighbors if n in self._cells]
            stressed_neighbours = sum(
                1
                for s in neighbour_states
                if s in (CellState.STRESSED, CellState.FAILING, CellState.DEAD)
            )
            if (
                neighbour_states
                and stressed_neighbours / len(neighbour_states) >= self.STRESS_PROPAGATION_THRESHOLD
            ):
                cell.health_score = max(0.0, cell.health_score - 0.05)
                cell._update_state()

            new_states[name] = cell.state

        return new_states

    def heal(self, service_name: str, health_score: float = 1.0) -> None:
        """Trigger regeneration for a dead or failing cell."""
        if service_name not in self._cells:
            return
        cell = self._cells[service_name]
        cell.health_score = health_score
        cell.state = CellState.REGENERATING if health_score < 0.8 else CellState.HEALTHY
        cell.last_state_change = time.time()

    def propagate_stress(self, source: str, amount: float = 0.1) -> list[str]:
        """Manually propagate stress from a source to its neighbours."""
        affected: list[str] = []
        if source not in self._cells:
            return affected
        for n in self._cells[source].neighbors:
            if n in self._cells:
                self._cells[n].health_score = max(0.0, self._cells[n].health_score - amount)
                self._cells[n]._update_state()
                affected.append(n)
        return affected

    def get_topology(self) -> dict[str, Any]:
        """Return current grid state as JSON-serialisable dict."""
        return {
            "generation": self._generation,
            "cells": {name: cell.to_dict() for name, cell in self._cells.items()},
            "summary": {
                "healthy": sum(1 for c in self._cells.values() if c.state == CellState.HEALTHY),
                "stressed": sum(1 for c in self._cells.values() if c.state == CellState.STRESSED),
                "failing": sum(1 for c in self._cells.values() if c.state == CellState.FAILING),
                "dead": sum(1 for c in self._cells.values() if c.state == CellState.DEAD),
                "regenerating": sum(
                    1 for c in self._cells.values() if c.state == CellState.REGENERATING
                ),
            },
        }

    def failing_services(self) -> list[str]:
        return [n for n, c in self._cells.items() if c.state in (CellState.FAILING, CellState.DEAD)]
