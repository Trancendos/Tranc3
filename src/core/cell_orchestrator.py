"""
Cell Orchestrator — Workers as Biological Cells
================================================
Models platform workers as cells in a living cluster.

Cell lifecycle states:
  seed      → spawning (process starting)
  embryo    → maturing (warmup period)
  mature    → healthy and serving traffic
  replicate → spawning a copy of itself
  apoptosis → graceful shutdown

Uses subprocess + threading (asyncio-compatible via run_in_executor).
Zero external dependencies.
"""

from __future__ import annotations

import enum
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("tranc3.core.cell_orchestrator")


# ── Cell lifecycle ────────────────────────────────────────────────────────


class CellState(str, enum.Enum):
    SEED = "seed"
    EMBRYO = "embryo"
    MATURE = "mature"
    REPLICATE = "replicate"
    APOPTOSIS = "apoptosis"
    DEAD = "dead"


@dataclass
class CellSpec:
    """Blueprint for spawning a worker cell."""

    cell_type: str  # e.g. "inference-worker", "mcp-worker"
    command: List[str]  # e.g. ["python", "-m", "workers.inference"]
    port: Optional[int] = None
    env_overrides: Dict[str, str] = field(default_factory=dict)
    warmup_s: float = 5.0  # seconds to wait before marking mature
    max_age_s: float = 0.0  # 0 = immortal; >0 = auto-apoptosis after N seconds
    health_check_url: str = ""  # optional URL to poll


@dataclass
class Cell:
    """A running worker instance."""

    cell_id: str
    spec: CellSpec
    state: CellState = CellState.SEED
    pid: Optional[int] = None
    process: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
    spawned_at: float = field(default_factory=time.monotonic)
    matured_at: Optional[float] = None
    exit_code: Optional[int] = None
    error_count: int = 0
    health_score: float = 100.0

    def age_s(self) -> float:
        return time.monotonic() - self.spawned_at


# ── CellOrchestrator ──────────────────────────────────────────────────────


class CellOrchestrator:
    """
    Manages a fleet of worker cells with lifecycle management.

    Features:
    - Spawn / replicate cells via subprocess
    - Automatic apoptosis when max_age_s exceeded
    - Health monitoring via configurable callbacks
    - Thread-safe cell registry

    Usage::

        orch = CellOrchestrator(max_cells=8)
        spec = CellSpec(
            cell_type="inference",
            command=["python", "-m", "workers.inference_worker"],
            port=8200,
            warmup_s=3.0,
        )
        cell_id = orch.spawn(spec)
        ...
        orch.apoptosis(cell_id)
        orch.shutdown()
    """

    def __init__(
        self,
        max_cells: int = 16,
        monitor_interval_s: float = 10.0,
        on_state_change: Optional[Callable[[Cell, CellState, CellState], None]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._cells: Dict[str, Cell] = {}
        self._max_cells = max_cells
        self._monitor_interval_s = monitor_interval_s
        self._on_state_change = on_state_change

        self._stop_event = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="cell-orchestrator-monitor", daemon=True
        )
        self._monitor_thread.start()

    # ── Spawn ─────────────────────────────────────────────────────────────

    def spawn(self, spec: CellSpec, replicate_from: Optional[str] = None) -> str:
        """
        Spawn a new cell from *spec*.  Returns the cell_id.
        *replicate_from* marks this as a replication (for logging).
        """
        with self._lock:
            alive = self._alive_count()
            if alive >= self._max_cells:
                raise RuntimeError(
                    f"Cell limit reached ({self._max_cells}). "
                    "Trigger apoptosis before spawning more."
                )

        cell_id = f"{spec.cell_type}-{uuid.uuid4().hex[:8]}"
        cell = Cell(cell_id=cell_id, spec=spec)

        env = dict(os.environ)
        env.update(spec.env_overrides)
        if spec.port:
            env["PORT"] = str(spec.port)
        env["CELL_ID"] = cell_id

        try:
            proc = subprocess.Popen(
                spec.command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # own process group for clean termination
            )
            cell.process = proc
            cell.pid = proc.pid
            cell.state = CellState.EMBRYO
            logger.info(
                "cell_spawned: id=%s type=%s pid=%d replicate_from=%s",
                cell_id,
                spec.cell_type,
                proc.pid,
                replicate_from,
            )
        except Exception as exc:
            cell.state = CellState.DEAD
            cell.exit_code = -1
            logger.error("cell_spawn_failed: id=%s error=%s", cell_id, exc)
            raise

        with self._lock:
            self._cells[cell_id] = cell

        # Schedule maturation after warmup_s
        threading.Thread(
            target=self._mature_after_warmup,
            args=(cell_id, spec.warmup_s),
            daemon=True,
        ).start()

        return cell_id

    def replicate(self, cell_id: str) -> str:
        """Spawn a copy of an existing cell."""
        with self._lock:
            if cell_id not in self._cells:
                raise KeyError(f"Unknown cell: {cell_id}")
            source = self._cells[cell_id]
            if source.state != CellState.MATURE:
                raise RuntimeError(f"Cell {cell_id} must be MATURE to replicate.")
            self._transition(source, CellState.REPLICATE)

        new_id = self.spawn(source.spec, replicate_from=cell_id)
        # Return source to mature after replication signal
        with self._lock:
            if source.cell_id in self._cells:
                self._transition(source, CellState.MATURE)
        return new_id

    # ── Apoptosis ─────────────────────────────────────────────────────────

    def apoptosis(self, cell_id: str, timeout_s: float = 10.0) -> None:
        """Gracefully shut down a cell (programmed cell death)."""
        with self._lock:
            if cell_id not in self._cells:
                return
            cell = self._cells[cell_id]
            self._transition(cell, CellState.APOPTOSIS)

        if cell.process and cell.process.poll() is None:
            try:
                cell.process.terminate()
                cell.process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                cell.process.kill()
                cell.process.wait()
            except Exception as exc:
                logger.warning("apoptosis_error: id=%s error=%s", cell_id, exc)

        with self._lock:
            if cell_id in self._cells:
                self._transition(cell, CellState.DEAD)
                cell.exit_code = cell.process.returncode if cell.process else -1
        logger.info("cell_dead: id=%s", cell_id)

    def apoptosis_oldest(self) -> Optional[str]:
        """Trigger apoptosis on the oldest mature cell. Returns its id."""
        with self._lock:
            mature = [c for c in self._cells.values() if c.state == CellState.MATURE]
            if not mature:
                return None
            oldest = max(mature, key=lambda c: c.age_s())

        self.apoptosis(oldest.cell_id)
        return oldest.cell_id

    # ── Query ─────────────────────────────────────────────────────────────

    def list_cells(self, state: Optional[CellState] = None) -> List[Cell]:
        with self._lock:
            cells = list(self._cells.values())
        if state:
            cells = [c for c in cells if c.state == state]
        return cells

    def get_cell(self, cell_id: str) -> Optional[Cell]:
        with self._lock:
            return self._cells.get(cell_id)

    def mature_count(self) -> int:
        with self._lock:
            return sum(1 for c in self._cells.values() if c.state == CellState.MATURE)

    def alive_count(self) -> int:
        with self._lock:
            return self._alive_count()

    def shutdown(self, timeout_s: float = 15.0) -> None:
        """Gracefully shut down all cells and stop the monitor thread."""
        self._stop_event.set()
        with self._lock:
            ids = list(self._cells.keys())
        for cid in ids:
            try:
                self.apoptosis(cid, timeout_s=timeout_s)
            except Exception:
                pass
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
        logger.info("cell_orchestrator_shutdown: all cells stopped")

    # ── Internal ──────────────────────────────────────────────────────────

    def _alive_count(self) -> int:
        return sum(
            1 for c in self._cells.values() if c.state not in (CellState.DEAD, CellState.APOPTOSIS)
        )

    def _transition(self, cell: Cell, new_state: CellState) -> None:
        old_state = cell.state
        cell.state = new_state
        if new_state == CellState.MATURE:
            cell.matured_at = time.monotonic()
        if self._on_state_change and old_state != new_state:
            try:
                self._on_state_change(cell, old_state, new_state)
            except Exception as exc:
                logger.warning("state_change_callback_error: %s", exc)

    def _mature_after_warmup(self, cell_id: str, warmup_s: float) -> None:
        time.sleep(warmup_s)
        with self._lock:
            cell = self._cells.get(cell_id)
            if cell and cell.state == CellState.EMBRYO:
                if cell.process and cell.process.poll() is None:
                    self._transition(cell, CellState.MATURE)
                    logger.info("cell_matured: id=%s", cell_id)
                else:
                    self._transition(cell, CellState.DEAD)
                    logger.warning("cell_died_during_warmup: id=%s", cell_id)

    def _monitor_loop(self) -> None:
        """Background thread: detect dead processes and enforce max_age_s."""
        while not self._stop_event.is_set():
            try:
                self._check_cells()
            except Exception as exc:
                logger.error("cell_monitor_error: %s", exc)
            self._stop_event.wait(timeout=self._monitor_interval_s)

    def _check_cells(self) -> None:
        time.monotonic()
        with self._lock:
            cells = list(self._cells.values())

        for cell in cells:
            if cell.state in (CellState.DEAD, CellState.APOPTOSIS):
                continue
            # Check if process died unexpectedly
            if cell.process and cell.process.poll() is not None:
                with self._lock:
                    if cell.state not in (CellState.DEAD, CellState.APOPTOSIS):
                        logger.warning(
                            "cell_unexpectedly_dead: id=%s exit_code=%d",
                            cell.cell_id,
                            cell.process.returncode,
                        )
                        self._transition(cell, CellState.DEAD)
                        cell.exit_code = cell.process.returncode
                continue
            # Enforce max_age_s
            if cell.spec.max_age_s > 0 and cell.age_s() >= cell.spec.max_age_s:
                logger.info("cell_max_age_reached: id=%s age=%.1fs", cell.cell_id, cell.age_s())
                threading.Thread(target=self.apoptosis, args=(cell.cell_id,), daemon=True).start()
