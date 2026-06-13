"""
DNA Config — Self-Optimizing Configuration
===========================================
Models configuration as "genetic code": a base config plus mutations.
Runs A/B-style evaluation and automatically promotes the best-performing
variant based on observed metrics. Works like feature flags but learns.

Stores performance data in SQLite. Zero external dependencies.

Named after the analogy that configuration drives system behaviour the
way DNA drives biological behaviour.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tranc3.core.dna_config")


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class Variant:
    """One configuration variant (base or mutation)."""
    variant_id: str
    config: Dict[str, Any]
    name: str = ""
    description: str = ""
    created_at: float = field(default_factory=time.time)

    # Accumulated performance stats
    total_score: float = 0.0
    sample_count: int = 0
    is_active: bool = True

    @property
    def mean_score(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.total_score / self.sample_count


@dataclass
class EvaluationResult:
    """Result of evaluating a variant."""
    variant_id: str
    score: float            # higher = better
    metric_name: str = "performance"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── DNAConfig ─────────────────────────────────────────────────────────────


class DNAConfig:
    """
    Self-optimizing configuration registry.

    Usage::

        dna = DNAConfig(db_path="data/dna_config.db")

        # Register base config
        dna.register_base({
            "batch_size": 32,
            "cache_ttl": 300,
            "concurrency": 4,
        })

        # Register mutations to evaluate
        dna.mutate({"batch_size": 64}, name="large-batch")
        dna.mutate({"concurrency": 8}, name="high-concurrency")

        # Get current best config to use
        cfg = dna.get_active_config()

        # After running: record how well it performed
        dna.record_score(cfg["_variant_id"], score=0.87)

        # Periodically promote best variant
        dna.promote_best()
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        auto_promote: bool = True,
        promote_min_samples: int = 10,
        exploration_fraction: float = 0.1,
    ) -> None:
        self._lock = threading.RLock()
        self._variants: Dict[str, Variant] = {}
        self._active_id: Optional[str] = None
        self._db_path = db_path
        self._auto_promote = auto_promote
        self._promote_min_samples = promote_min_samples
        self._exploration_fraction = exploration_fraction  # Thompson sampling ε

        if db_path:
            self._init_db(db_path)
            self._load_from_db()

    # ── Setup ─────────────────────────────────────────────────────────────

    def register_base(
        self,
        config: Dict[str, Any],
        name: str = "base",
        description: str = "",
    ) -> str:
        """Register the base (default) configuration."""
        vid = f"base-{uuid.uuid4().hex[:8]}"
        v = Variant(
            variant_id=vid,
            config=dict(config),
            name=name,
            description=description,
        )
        with self._lock:
            self._variants[vid] = v
            if self._active_id is None:
                self._active_id = vid
        if self._db_path:
            self._persist_variant(v)
        logger.info("dna_config: base registered variant_id=%s", vid)
        return vid

    def mutate(
        self,
        overrides: Dict[str, Any],
        base_id: Optional[str] = None,
        name: str = "",
        description: str = "",
    ) -> str:
        """Create a mutation of the base (or specified) variant."""
        with self._lock:
            if base_id is None:
                base_id = self._active_id
            if base_id is None or base_id not in self._variants:
                raise ValueError("No base variant registered. Call register_base() first.")
            base_config = dict(self._variants[base_id].config)

        merged = {**base_config, **overrides}
        vid = f"mut-{uuid.uuid4().hex[:8]}"
        v = Variant(
            variant_id=vid,
            config=merged,
            name=name or f"mutation-{vid[:6]}",
            description=description,
        )
        with self._lock:
            self._variants[vid] = v
        if self._db_path:
            self._persist_variant(v)
        logger.info("dna_config: mutation registered variant_id=%s base=%s", vid, base_id)
        return vid

    # ── Usage ─────────────────────────────────────────────────────────────

    def get_active_config(self) -> Dict[str, Any]:
        """
        Return the currently active configuration dict.
        Includes _variant_id key so callers can record scores.

        With exploration_fraction > 0, occasionally returns a random
        non-active variant to gather evaluation data (exploration).
        """
        with self._lock:
            active_variants = [v for v in self._variants.values() if v.is_active]
            if not active_variants:
                raise RuntimeError("No variants registered.")

            # Exploration: pick a random variant occasionally
            import random
            if (
                len(active_variants) > 1
                and random.random() < self._exploration_fraction
            ):
                v = random.choice(active_variants)
            else:
                if self._active_id and self._active_id in self._variants:
                    v = self._variants[self._active_id]
                else:
                    v = active_variants[0]

            config = dict(v.config)
            config["_variant_id"] = v.variant_id
            return config

    def get_variant(self, variant_id: str) -> Optional[Variant]:
        with self._lock:
            return self._variants.get(variant_id)

    def record_score(
        self,
        variant_id: str,
        score: float,
        metric_name: str = "performance",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a performance score for a variant."""
        with self._lock:
            if variant_id not in self._variants:
                logger.warning("dna_config: unknown variant_id=%s", variant_id)
                return
            v = self._variants[variant_id]
            v.total_score += score
            v.sample_count += 1

        if self._db_path:
            self._persist_eval(
                EvaluationResult(
                    variant_id=variant_id,
                    score=score,
                    metric_name=metric_name,
                    metadata=metadata or {},
                )
            )

        if self._auto_promote:
            self.promote_best()

    def promote_best(self) -> Optional[str]:
        """
        Evaluate all variants and promote the best one as active.
        Only considers variants with >= promote_min_samples.
        Returns the promoted variant_id (or None if unchanged).
        """
        with self._lock:
            candidates = [
                v for v in self._variants.values()
                if v.is_active and v.sample_count >= self._promote_min_samples
            ]
            if not candidates:
                return None

            best = max(candidates, key=lambda v: v.mean_score)
            if best.variant_id == self._active_id:
                return None

            old_id = self._active_id
            self._active_id = best.variant_id

        logger.info(
            "dna_config: promoted variant_id=%s mean_score=%.4f (was %s)",
            best.variant_id,
            best.mean_score,
            old_id,
        )
        if self._db_path:
            self._persist_active(best.variant_id)
        return best.variant_id

    def leaderboard(self) -> List[Dict[str, Any]]:
        """Return variants sorted by mean_score descending."""
        with self._lock:
            rows = [
                {
                    "variant_id": v.variant_id,
                    "name": v.name,
                    "mean_score": v.mean_score,
                    "sample_count": v.sample_count,
                    "is_active": v.is_active,
                    "is_current": v.variant_id == self._active_id,
                }
                for v in self._variants.values()
            ]
        return sorted(rows, key=lambda r: r["mean_score"], reverse=True)

    def deactivate(self, variant_id: str) -> None:
        """Stop a variant from being selected."""
        with self._lock:
            if variant_id in self._variants:
                self._variants[variant_id].is_active = False
                if self._active_id == variant_id:
                    # Fall back to best remaining
                    active = [
                        v for v in self._variants.values()
                        if v.is_active and v.variant_id != variant_id
                    ]
                    self._active_id = active[0].variant_id if active else None

    # ── SQLite persistence ─────────────────────────────────────────────────

    def _init_db(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS variants (
                variant_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                config TEXT,
                total_score REAL DEFAULT 0,
                sample_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variant_id TEXT,
                score REAL,
                metric_name TEXT,
                timestamp REAL,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS active_variant (
                singleton INTEGER PRIMARY KEY DEFAULT 1,
                variant_id TEXT
            );
            """
        )
        conn.commit()
        conn.close()

    def _persist_variant(self, v: Variant) -> None:
        try:
            conn = sqlite3.connect(self._db_path)  # type: ignore[arg-type]
            conn.execute(
                "INSERT OR REPLACE INTO variants VALUES (?,?,?,?,?,?,?,?)",
                (
                    v.variant_id, v.name, v.description,
                    json.dumps(v.config), v.total_score,
                    v.sample_count, int(v.is_active), v.created_at,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("dna_config db error: %s", exc)

    def _persist_eval(self, ev: EvaluationResult) -> None:
        try:
            conn = sqlite3.connect(self._db_path)  # type: ignore[arg-type]
            conn.execute(
                "INSERT INTO evaluations (variant_id, score, metric_name, timestamp, metadata) "
                "VALUES (?,?,?,?,?)",
                (ev.variant_id, ev.score, ev.metric_name, ev.timestamp, json.dumps(ev.metadata)),
            )
            # Also update summary in variants table
            conn.execute(
                "UPDATE variants SET total_score=total_score+?, sample_count=sample_count+1 "
                "WHERE variant_id=?",
                (ev.score, ev.variant_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("dna_config db eval error: %s", exc)

    def _persist_active(self, variant_id: str) -> None:
        try:
            conn = sqlite3.connect(self._db_path)  # type: ignore[arg-type]
            conn.execute(
                "INSERT OR REPLACE INTO active_variant (singleton, variant_id) VALUES (1, ?)",
                (variant_id,),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("dna_config db active error: %s", exc)

    def _load_from_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)  # type: ignore[arg-type]
            rows = conn.execute("SELECT * FROM variants").fetchall()
            for row in rows:
                vid, name, desc, config_json, total, count, active, created = row
                v = Variant(
                    variant_id=vid,
                    config=json.loads(config_json),
                    name=name or "",
                    description=desc or "",
                    created_at=created,
                    total_score=total,
                    sample_count=count,
                    is_active=bool(active),
                )
                self._variants[vid] = v
            row = conn.execute("SELECT variant_id FROM active_variant WHERE singleton=1").fetchone()
            if row:
                self._active_id = row[0]
            conn.close()
        except Exception as exc:
            logger.warning("dna_config db load error: %s", exc)
