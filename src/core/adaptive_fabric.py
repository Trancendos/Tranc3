"""
Adaptive Fabric — fluidic, reactive, self-healing component system.

Architecture concepts implemented:
- Cell: autonomous self-contained unit (like biological cells)
- Cluster: group of cells that coordinate
- DNA/Genome: configuration that cells inherit and mutate
- Nano: micro-service particle (ultra-lightweight callable)
- Genetic: trait inheritance and expression between components
- Reactive: event-driven state propagation
- Quantum: superposition routing (try multiple providers in parallel)
- Dimensional: multi-context awareness (time, space, load, intent)
- Proactive: anticipatory prefetch/warmup
- Liquidic: shape-shifting interface adaptation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger("tranc3.adaptive_fabric")


# ─── DNA / Genetic Traits ────────────────────────────────────────────────────

class TraitExpression(Enum):
    DOMINANT = auto()    # always expressed
    RECESSIVE = auto()   # expressed only if no dominant present
    CODOMINANT = auto()  # both expressed simultaneously
    ADAPTIVE = auto()    # expressed based on environment


@dataclass
class Trait:
    """A single genetic trait — a named capability or behaviour modifier."""
    name: str
    value: Any
    expression: TraitExpression = TraitExpression.DOMINANT
    fitness: float = 1.0  # 0.0–1.0; natural selection favours higher values


@dataclass
class Genome:
    """The DNA of a Cell — defines its heritable configuration."""
    traits: Dict[str, Trait] = field(default_factory=dict)
    generation: int = 0
    lineage: List[str] = field(default_factory=list)

    def express(self, name: str, default: Any = None) -> Any:
        t = self.traits.get(name)
        return t.value if t else default

    def mutate(self, trait_name: str, new_value: Any, fitness: float = 1.0) -> "Genome":
        new_traits = {**self.traits, trait_name: Trait(trait_name, new_value, fitness=fitness)}
        return Genome(
            traits=new_traits,
            generation=self.generation + 1,
            lineage=[*self.lineage, f"gen{self.generation}:{trait_name}"],
        )

    def crossover(self, other: "Genome") -> "Genome":
        merged: Dict[str, Trait] = {}
        for name in set(self.traits) | set(other.traits):
            a = self.traits.get(name)
            b = other.traits.get(name)
            if a and b:
                # Dominant wins; on tie pick higher fitness
                if a.expression == TraitExpression.DOMINANT and b.expression != TraitExpression.DOMINANT:
                    merged[name] = a
                elif b.expression == TraitExpression.DOMINANT and a.expression != TraitExpression.DOMINANT:
                    merged[name] = b
                else:
                    merged[name] = a if a.fitness >= b.fitness else b
            else:
                merged[name] = (a or b)  # type: ignore[arg-type]
        return Genome(
            traits=merged,
            generation=max(self.generation, other.generation) + 1,
            lineage=[*self.lineage[:2], *other.lineage[:2], "crossover"],
        )


# ─── Nano Particle ───────────────────────────────────────────────────────────

class Nano:
    """
    Ultra-lightweight callable micro-unit.
    Nanos are composable, chainable, and stateless.
    """
    def __init__(self, fn: Callable, name: str = "", ttl_ms: int = 0):
        self.fn = fn
        self.name = name or fn.__name__
        self.ttl_ms = ttl_ms
        self._cache: Dict[str, Tuple[float, Any]] = {}

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self.ttl_ms:
            key = hashlib.md5(json.dumps([args, kwargs], default=str).encode()).hexdigest()  # nosec B324 — cache key only, not crypto
            cached = self._cache.get(key)
            if cached and (time.time() * 1000 - cached[0]) < self.ttl_ms:
                return cached[1]
        result = await self.fn(*args, **kwargs) if asyncio.iscoroutinefunction(self.fn) else self.fn(*args, **kwargs)
        if self.ttl_ms:
            self._cache[key] = (time.time() * 1000, result)
        return result

    def chain(self, other: "Nano") -> "Nano":
        async def chained(*args: Any, **kwargs: Any) -> Any:
            result = await self(*args, **kwargs)
            return await other(result)
        return Nano(chained, name=f"{self.name}→{other.name}")

    def __or__(self, other: "Nano") -> "Nano":
        return self.chain(other)


# ─── Reactive State ──────────────────────────────────────────────────────────

class ReactiveState:
    """
    Observable state container.
    Subscribers are called synchronously when state changes.
    """
    def __init__(self, initial: Any = None):
        self._value = initial
        self._subscribers: List[Callable] = []
        self._history: List[Tuple[float, Any]] = []

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, new_val: Any) -> None:
        if new_val != self._value:
            old = self._value
            self._value = new_val
            self._history.append((time.time(), new_val))
            if len(self._history) > 100:
                self._history = self._history[-100:]
            for sub in self._subscribers:
                try:
                    if asyncio.iscoroutinefunction(sub):
                        asyncio.create_task(sub(new_val, old))
                    else:
                        sub(new_val, old)
                except Exception as exc:
                    logger.error("reactive subscriber error: %s", exc)

    def subscribe(self, fn: Callable) -> Callable:
        self._subscribers.append(fn)
        return fn

    def unsubscribe(self, fn: Callable) -> None:
        self._subscribers = [s for s in self._subscribers if s is not fn]

    @property
    def history(self) -> List[Tuple[float, Any]]:
        return list(self._history)


# ─── Cell ────────────────────────────────────────────────────────────────────

class CellState(Enum):
    DORMANT = auto()
    ACTIVE = auto()
    DIVIDING = auto()
    DYING = auto()
    APOPTOSIS = auto()  # programmed self-destruction


class Cell:
    """
    Autonomous self-contained processing unit.
    Cells have a lifecycle, genome, reactive state, and can divide (spawn children).
    """
    def __init__(
        self,
        name: str,
        genome: Optional[Genome] = None,
        handler: Optional[Callable] = None,
        max_lifespan_s: float = 3600,
    ):
        self.id = str(uuid4())[:8]
        self.name = name
        self.genome = genome or Genome()
        self.handler = handler
        self.state = ReactiveState(CellState.DORMANT)
        self.health = ReactiveState(1.0)
        self.born_at = time.time()
        self.max_lifespan_s = max_lifespan_s
        self._children: List["Cell"] = []
        self._request_count = 0
        self._error_count = 0

    async def process(self, payload: Any) -> Any:
        if self.state.value == CellState.DYING or self.is_expired():
            self.state.value = CellState.APOPTOSIS
            raise RuntimeError(f"Cell {self.name}:{self.id} is dead")

        self.state.value = CellState.ACTIVE
        self._request_count += 1
        try:
            if self.handler:
                result = await self.handler(payload, self) if asyncio.iscoroutinefunction(self.handler) else self.handler(payload, self)
            else:
                result = payload
            # Health recovery on success
            self.health.value = min(1.0, self.health.value + 0.01)
            return result
        except Exception:
            self._error_count += 1
            # Health degrades on error
            error_rate = self._error_count / max(self._request_count, 1)
            self.health.value = max(0.0, 1.0 - error_rate)
            if self.health.value < 0.2:
                self.state.value = CellState.DYING
            raise
        finally:
            if self.state.value == CellState.ACTIVE:
                self.state.value = CellState.DORMANT

    def divide(self) -> "Cell":
        """Mitosis — spawn a child cell with inherited genome."""
        self.state.value = CellState.DIVIDING
        child = Cell(
            name=f"{self.name}:child",
            genome=self.genome.mutate("generation", self.genome.generation + 1),
            handler=self.handler,
            max_lifespan_s=self.max_lifespan_s,
        )
        self._children.append(child)
        self.state.value = CellState.DORMANT
        return child

    def is_expired(self) -> bool:
        return time.time() - self.born_at > self.max_lifespan_s

    @property
    def vitals(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.value.name,
            "health": self.health.value,
            "age_s": round(time.time() - self.born_at, 1),
            "requests": self._request_count,
            "errors": self._error_count,
            "genome_generation": self.genome.generation,
            "children": len(self._children),
        }


# ─── Cluster ─────────────────────────────────────────────────────────────────

class Cluster:
    """
    A group of Cells that collectively handle a workload.
    Provides load balancing, health-based routing, and auto-scaling.
    """
    def __init__(self, name: str, min_cells: int = 1, max_cells: int = 8):
        self.name = name
        self.min_cells = min_cells
        self.max_cells = max_cells
        self._cells: List[Cell] = []
        self._lock = asyncio.Lock()

    def seed(self, cell: Cell) -> "Cluster":
        self._cells.append(cell)
        return self

    def _healthy_cells(self) -> List[Cell]:
        return [c for c in self._cells if c.health.value > 0.3 and not c.is_expired()]

    def _pick_cell(self) -> Optional[Cell]:
        healthy = self._healthy_cells()
        if not healthy:
            return None
        # Weighted random by health score
        import random
        weights = [c.health.value for c in healthy]
        return random.choices(healthy, weights=weights, k=1)[0]

    async def process(self, payload: Any) -> Any:
        cell = self._pick_cell()
        if not cell:
            # Auto-scale: spawn new cell if prototype exists
            if self._cells and len(self._cells) < self.max_cells:
                cell = self._cells[0].divide()
                self._cells.append(cell)
            else:
                raise RuntimeError(f"Cluster {self.name}: no healthy cells available")
        return await cell.process(payload)

    def prune(self) -> int:
        before = len(self._cells)
        self._cells = [
            c for c in self._cells
            if not c.is_expired() and c.state.value != CellState.APOPTOSIS
        ]
        # Maintain minimum
        while len(self._cells) < self.min_cells and before > 0:
            self._cells.append(self._cells[0].divide() if self._cells else Cell(self.name))
        return before - len(self._cells)

    @property
    def status(self) -> dict:
        return {
            "name": self.name,
            "total_cells": len(self._cells),
            "healthy_cells": len(self._healthy_cells()),
            "cells": [c.vitals for c in self._cells],
        }


# ─── Dimensional Context ─────────────────────────────────────────────────────

class DimensionalContext:
    """
    Multi-dimensional awareness:
    - Temporal: time-of-day, recency, trends
    - Spatial: geographic region, latency zones
    - Load: current system pressure
    - Intent: what the user is trying to accomplish
    - Social: collaborative context
    """
    def __init__(self):
        self.temporal = ReactiveState({"hour": 0, "day_of_week": 0, "is_peak": False})
        self.load = ReactiveState({"cpu": 0.0, "memory": 0.0, "queue_depth": 0})
        self.intent = ReactiveState({"category": "general", "urgency": 0.5, "complexity": 0.5})
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    def refresh(self) -> None:
        import datetime
        now = datetime.datetime.utcnow()
        hour = now.hour
        peak_hours = set(range(9, 18))  # 9am–6pm UTC
        self.temporal.value = {
            "hour": hour,
            "day_of_week": now.weekday(),
            "is_peak": hour in peak_hours,
            "ts": time.time(),
        }

    def set_intent(self, category: str, urgency: float = 0.5, complexity: float = 0.5) -> None:
        self.intent.value = {"category": category, "urgency": urgency, "complexity": complexity}

    def get_routing_hints(self) -> dict:
        """Returns routing recommendations based on current dimensions."""
        self.refresh()
        temporal = self.temporal.value
        intent = self.intent.value
        load = self.load.value

        hints = {}
        # During peak hours, prefer local Ollama to avoid API rate limits
        if temporal.get("is_peak"):
            hints["prefer_local"] = True
        # High complexity → use larger model
        if intent.get("complexity", 0.5) > 0.8:
            hints["prefer_large_model"] = True
        # High urgency → prefer low-latency providers
        if intent.get("urgency", 0.5) > 0.8:
            hints["prefer_low_latency"] = True
            hints["provider_priority"] = ["groq", "cerebras", "ollama"]
        # High load → prefer fast local
        if load.get("cpu", 0) > 0.8:
            hints["prefer_local"] = True
        return hints


# ─── Quantum Router ──────────────────────────────────────────────────────────

class QuantumRouter:
    """
    Superposition routing: dispatch to multiple providers simultaneously,
    return the first successful response (race), cancel others.

    This gives the reliability of redundancy with the latency of the fastest provider.
    """
    def __init__(self, timeout_s: float = 30.0):
        self.timeout_s = timeout_s

    async def race(self, callables: List[Callable], *args: Any, **kwargs: Any) -> Any:
        """Execute all callables concurrently, return first success."""
        if not callables:
            raise ValueError("QuantumRouter.race: no callables provided")

        pending = {asyncio.create_task(fn(*args, **kwargs)) for fn in callables}
        end_time = time.time() + self.timeout_s
        while pending:
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=remaining,
            )
            if not done:
                break
            for task in done:
                if task.exception() is None:
                    for p in pending:
                        p.cancel()
                    return task.result()
                # Task failed — log and continue racing remaining tasks
                logger.debug("QuantumRouter: provider task failed: %s", task.exception())
        for p in pending:
            p.cancel()
        raise RuntimeError("QuantumRouter: all providers failed or timed out")


# ─── Liquidic Interface ──────────────────────────────────────────────────────

class LiquidicAdapter:
    """
    Shape-shifting interface that adapts to the caller's context.
    Transforms inputs/outputs based on detected format, language, and intent.
    """
    SUPPORTED_FORMATS = {"json", "text", "markdown", "html", "csv", "yaml"}

    def __init__(self, target_format: str = "json"):
        self.target_format = target_format
        self._transforms: Dict[str, Callable] = {}

    def register_transform(self, from_fmt: str, to_fmt: str, fn: Callable) -> None:
        self._transforms[f"{from_fmt}→{to_fmt}"] = fn

    def adapt(self, data: Any, from_format: str = "auto") -> Any:
        if from_format == "auto":
            from_format = self._detect_format(data)
        key = f"{from_format}→{self.target_format}"
        transform = self._transforms.get(key)
        if transform:
            return transform(data)
        if from_format == self.target_format:
            return data
        # Default: JSON passthrough
        if self.target_format == "json":
            return {"data": data, "source_format": from_format}
        return str(data)

    @staticmethod
    def _detect_format(data: Any) -> str:
        if isinstance(data, (dict, list)):
            return "json"
        if isinstance(data, str):
            s = data.strip()
            if s.startswith("{") or s.startswith("["):
                return "json"
            if s.startswith("#") or "**" in s:
                return "markdown"
            if s.startswith("<"):
                return "html"
        return "text"


# ─── Proactive Prefetch ──────────────────────────────────────────────────────

class ProactiveCache:
    """
    Anticipatory caching — prefetches resources before they're explicitly requested,
    based on access patterns and predictive scoring.
    """
    def __init__(self, capacity: int = 256):
        self.capacity = capacity
        self._cache: Dict[str, Tuple[float, Any, float]] = {}  # key → (ts, value, score)
        self._access_counts: Dict[str, int] = defaultdict(int)
        self._access_sequences: List[str] = []

    def get(self, key: str) -> Optional[Any]:
        self._access_counts[key] += 1
        self._access_sequences.append(key)
        if len(self._access_sequences) > 1000:
            self._access_sequences = self._access_sequences[-500:]
        entry = self._cache.get(key)
        if entry:
            return entry[1]
        return None

    def put(self, key: str, value: Any, score: float = 1.0) -> None:
        if len(self._cache) >= self.capacity:
            # Evict lowest-score entry
            worst = min(self._cache, key=lambda k: self._cache[k][2])
            del self._cache[worst]
        self._cache[key] = (time.time(), value, score)

    def predict_next(self) -> List[str]:
        """Predict next likely keys based on bigram access patterns."""
        if len(self._access_sequences) < 2:
            return []
        last = self._access_sequences[-1]
        bigrams: Dict[str, int] = defaultdict(int)
        for i in range(len(self._access_sequences) - 1):
            if self._access_sequences[i] == last:
                bigrams[self._access_sequences[i + 1]] += 1
        if not bigrams:
            return []
        return sorted(bigrams, key=bigrams.get, reverse=True)[:3]  # type: ignore[arg-type]

    async def prefetch(self, fetcher: Callable, keys: List[str]) -> None:
        """Silently fetch and cache predicted keys."""
        for key in keys:
            if key not in self._cache:
                try:
                    value = await fetcher(key) if asyncio.iscoroutinefunction(fetcher) else fetcher(key)
                    self.put(key, value, score=0.5)
                except Exception:  # noqa: BLE001 — prefetch errors are non-fatal by design
                    logger.debug("ProactiveCache.prefetch: key=%s fetch failed", key)


# ─── Global Fabric ───────────────────────────────────────────────────────────

class AdaptiveFabric:
    """
    Top-level adaptive fabric — wires together all subsystems:
    Cells + Clusters + Reactive + Quantum + Dimensional + Liquidic + Proactive
    """
    def __init__(self):
        self.clusters: Dict[str, Cluster] = {}
        self.context = DimensionalContext()
        self.router = QuantumRouter()
        self.cache = ProactiveCache()
        self._health = ReactiveState(1.0)
        self._event_log: List[dict] = []

    def register_cluster(self, cluster: Cluster) -> "AdaptiveFabric":
        self.clusters[cluster.name] = cluster
        return self

    def nano(self, fn: Callable = None, ttl_ms: int = 0) -> Callable:
        """Decorator to wrap any function as a Nano particle."""
        def decorator(f: Callable) -> Nano:
            return Nano(f, name=f.__name__, ttl_ms=ttl_ms)
        if fn:
            return decorator(fn)
        return decorator

    async def dispatch(self, cluster_name: str, payload: Any) -> Any:
        cluster = self.clusters.get(cluster_name)
        if not cluster:
            raise KeyError(f"Cluster '{cluster_name}' not registered in AdaptiveFabric")
        hints = self.context.get_routing_hints()
        self._event_log.append({
            "ts": time.time(), "event": "dispatch",
            "cluster": cluster_name, "hints": hints,
        })
        return await cluster.process(payload)

    def status(self) -> dict:
        return {
            "health": self._health.value,
            "clusters": {name: c.status for name, c in self.clusters.items()},
            "context": {
                "temporal": self.context.temporal.value,
                "intent": self.context.intent.value,
            },
            "cache_size": len(self.cache._cache),
            "recent_events": self._event_log[-10:],
        }


# Singleton fabric instance
fabric = AdaptiveFabric()

__all__ = [
    "Trait", "TraitExpression", "Genome",
    "Nano", "ReactiveState",
    "Cell", "CellState", "Cluster",
    "DimensionalContext", "QuantumRouter",
    "LiquidicAdapter", "ProactiveCache",
    "AdaptiveFabric", "fabric",
]
