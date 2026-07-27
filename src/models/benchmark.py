# src/models/benchmark.py
"""Regular benchmarking for the Trancendos Models Matrix.

Every named AI (or its earned specialized variant — see `matrix.py`) gets
scanned periodically against its skill domain. Each scan is recorded here;
`compute_advancement_pct()` compares a new score against the AI's own most
recent prior score to produce the "% of advancement" figure the governance
pipeline (`governance.py`) gates on.

SQLite-backed (zero-cost, self-hosted, matches `src/roles/registry.py`'s
architecture), so benchmark history survives restarts.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

DEFAULT_DB_PATH = Path("data/models_benchmark.db")


@dataclass
class BenchmarkResult:
    id: int
    model_name: str
    skill_domain: str
    score: float
    notes: str
    recorded_at: float
    recorded_by: str


class BenchmarkRegistry:
    """SQLite-backed benchmark score history, one row per scan."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Same rationale as RoleRegistry: sync FastAPI handlers run in a
        # threadpool, so concurrent record_benchmark()/latest_two() calls on
        # this one connection need a real lock, not just SQLite's own.
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                skill_domain TEXT NOT NULL,
                score REAL NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                recorded_at REAL NOT NULL,
                recorded_by TEXT NOT NULL DEFAULT 'system'
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_benchmark_model_skill "
            "ON benchmark_results(model_name, skill_domain, recorded_at DESC)"
        )
        self._conn.commit()

    def _row_to_result(self, row: sqlite3.Row) -> BenchmarkResult:
        return BenchmarkResult(
            id=row["id"],
            model_name=row["model_name"],
            skill_domain=row["skill_domain"],
            score=row["score"],
            notes=row["notes"],
            recorded_at=row["recorded_at"],
            recorded_by=row["recorded_by"],
        )

    def record_benchmark(
        self,
        model_name: str,
        skill_domain: str,
        score: float,
        notes: str = "",
        recorded_by: str = "system",
    ) -> BenchmarkResult:
        """Record one benchmark scan result. `score` is on whatever scale
        the skill domain's own benchmark suite uses (e.g. 0-100) — this
        registry only cares about relative change between consecutive
        scores for the same (model_name, skill_domain) pair."""
        with self._lock:
            now = time.time()
            cur = self._conn.execute(
                "INSERT INTO benchmark_results "
                "(model_name, skill_domain, score, notes, recorded_at, recorded_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (model_name, skill_domain, score, notes, now, recorded_by),
            )
            self._conn.commit()
            row_id = cur.lastrowid
            row = self._conn.execute(
                "SELECT * FROM benchmark_results WHERE id = ?", (row_id,)
            ).fetchone()
            return self._row_to_result(row)

    def history(
        self, model_name: str, skill_domain: Optional[str] = None, limit: int = 50
    ) -> List[BenchmarkResult]:
        with self._lock:
            if skill_domain:
                cur = self._conn.execute(
                    "SELECT * FROM benchmark_results WHERE model_name = ? AND skill_domain = ? "
                    "ORDER BY recorded_at DESC LIMIT ?",
                    (model_name, skill_domain, limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM benchmark_results WHERE model_name = ? "
                    "ORDER BY recorded_at DESC LIMIT ?",
                    (model_name, limit),
                )
            return [self._row_to_result(row) for row in cur.fetchall()]

    def latest_two(
        self, model_name: str, skill_domain: str
    ) -> tuple[Optional[BenchmarkResult], Optional[BenchmarkResult]]:
        """Returns (latest, prior) — either may be None if too few scans exist."""
        results = self.history(model_name, skill_domain, limit=2)
        latest = results[0] if len(results) >= 1 else None
        prior = results[1] if len(results) >= 2 else None
        return latest, prior

    def close(self) -> None:
        self._conn.close()


def compute_advancement_pct(prior_score: float, new_score: float) -> float:
    """% advancement of new_score over prior_score.

    A prior_score of 0 (or below) makes a percentage change undefined
    (division by zero / meaningless sign) — treated as a 0% advancement
    rather than raising, since a brand-new skill domain with no real
    baseline shouldn't be able to claim an infinite improvement.
    """
    if prior_score <= 0:
        return 0.0
    return round(((new_score - prior_score) / prior_score) * 100.0, 4)


_registry: Optional[BenchmarkRegistry] = None
_registry_lock = threading.Lock()


def get_benchmark_registry() -> BenchmarkRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_registry()`, `get_library()`, `get_marketplace()`)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = BenchmarkRegistry()
    return _registry
