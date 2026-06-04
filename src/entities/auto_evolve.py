"""
AutoEvolve — Zero-Cost Genetic Self-Optimisation Scheduler
==========================================================
Periodically invokes NSGA-II evolution on all registered T3 Lead AIs
and T1 Orchestrators to continuously adapt routing parameters.

Zero-cost: pure asyncio, no external services, SQLite result cache.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from src.database.encrypted_sqlite import connect as sqlite3_connect

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/evolution_cache.db")
_EVOLVE_INTERVAL_S = 3600.0  # once per hour by default
_EVOLVE_GENERATIONS = 30
_EVOLVE_POP_SIZE = 20


class AutoEvolve:
    """
    Continuously evolve registered entities' parameters in the background.

    Usage::

        ae = AutoEvolve(interval_seconds=3600)
        ae.register(nexus_prime_lead_ai)
        asyncio.create_task(ae.run())
    """

    def __init__(
        self,
        interval_seconds: float = _EVOLVE_INTERVAL_S,
        generations: int = _EVOLVE_GENERATIONS,
        pop_size: int = _EVOLVE_POP_SIZE,
        db_path: Path = _DB_PATH,
    ) -> None:
        self._interval = interval_seconds
        self._generations = generations
        self._pop_size = pop_size
        self._entities: dict[str, Any] = {}
        self._last_evolved: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3_connect(self._db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS evolution_results (
                    entity_id TEXT,
                    evolved_at REAL,
                    best_config TEXT,
                    PRIMARY KEY (entity_id, evolved_at)
                )""",
            )
            conn.commit()

    def register(self, entity: Any) -> None:
        try:
            eid = entity.dna.aid
            self._entities[eid] = entity
            self._last_evolved[eid] = 0.0
            logger.debug("AutoEvolve: registered %s", eid)
        except AttributeError as exc:
            logger.warning("AutoEvolve.register: entity missing .dna.aid — %s", exc)

    def deregister(self, aid: str) -> None:
        self._entities.pop(aid, None)
        self._last_evolved.pop(aid, None)

    async def _evolve_entity(self, eid: str, entity: Any) -> None:
        if not hasattr(entity, "evolve"):
            return
        try:
            best = await entity.evolve(generations=self._generations, pop_size=self._pop_size)
            self._last_evolved[eid] = time.monotonic()
            if best:
                import json

                with sqlite3_connect(self._db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO evolution_results VALUES (?,?,?)",
                        (eid, time.time(), json.dumps(best)),
                    )
                    conn.commit()
                logger.info("AutoEvolve: %s evolved — best=%s", eid, best)
        except Exception as exc:
            logger.warning("AutoEvolve: evolution failed for %s: %s", eid, exc)

    async def run(self) -> None:
        self._running = True
        logger.info(
            "AutoEvolve started (%d entities, interval=%.0fs)", len(self._entities), self._interval,
        )
        while self._running:
            now = time.monotonic()
            tasks = []
            for eid, entity in list(self._entities.items()):
                elapsed = now - self._last_evolved.get(eid, 0.0)
                if elapsed >= self._interval:
                    tasks.append(self._evolve_entity(eid, entity))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await asyncio.sleep(min(self._interval, 300.0))
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        if self._running:
            return
        self._task = asyncio.create_task(self.run(), name="auto_evolve")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "registered": len(self._entities),
            "interval_seconds": self._interval,
            "last_evolved": {eid: round(now - t, 1) for eid, t in self._last_evolved.items()},
        }
