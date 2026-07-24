"""Cell orchestrator admin surface — dynamic worker-cell lifecycle control.

Wraps src.core.cell_orchestrator.CellOrchestrator (subprocess-based worker
lifecycle manager) as a lazily-constructed singleton, so Admin OS operators
can spawn, inspect, and retire worker cells without a code change.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.cell_orchestrator import Cell, CellOrchestrator, CellSpec, CellState

_orchestrator: Optional[CellOrchestrator] = None


def get_orchestrator() -> CellOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CellOrchestrator()
    return _orchestrator


def _cell_to_dict(cell: Cell) -> Dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "cell_type": cell.spec.cell_type,
        "state": cell.state.value,
        "pid": cell.pid,
        "age_s": round(cell.age_s(), 1),
        "error_count": cell.error_count,
        "health_score": cell.health_score,
    }


def spawn_cell(
    cell_type: str,
    command: List[str],
    port: Optional[int] = None,
    warmup_s: float = 5.0,
    max_age_s: float = 0.0,
) -> Dict[str, Any]:
    orch = get_orchestrator()
    spec = CellSpec(
        cell_type=cell_type,
        command=command,
        port=port,
        warmup_s=warmup_s,
        max_age_s=max_age_s,
    )
    cell_id = orch.spawn(spec)
    cell = orch.get_cell(cell_id)
    return _cell_to_dict(cell) if cell else {"cell_id": cell_id}


def list_cells(state: Optional[str] = None) -> Dict[str, Any]:
    orch = get_orchestrator()
    state_enum = CellState(state) if state else None
    cells = orch.list_cells(state=state_enum)
    return {
        "total": len(cells),
        "mature": orch.mature_count(),
        "alive": orch.alive_count(),
        "cells": [_cell_to_dict(c) for c in cells],
    }


def apoptosis_cell(cell_id: str) -> Dict[str, Any]:
    orch = get_orchestrator()
    if orch.get_cell(cell_id) is None:
        raise KeyError(f"Unknown cell: {cell_id}")
    orch.apoptosis(cell_id)
    cell = orch.get_cell(cell_id)
    return _cell_to_dict(cell) if cell else {"cell_id": cell_id, "state": "dead"}


def replicate_cell(cell_id: str) -> Dict[str, Any]:
    orch = get_orchestrator()
    new_id = orch.replicate(cell_id)
    cell = orch.get_cell(new_id)
    return _cell_to_dict(cell) if cell else {"cell_id": new_id}
