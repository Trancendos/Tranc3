"""
Tranc3 InfinityBridge Path Optimization
=========================================
Intelligent routing across light bridges with dynamic path selection,
health monitoring, and fallback routing.

Scoring Algorithm:
    Each path is scored using a weighted combination of:
    - Latency Score (40%): Lower avg_transition_ms = higher score
    - Load Score (30%): Lower transition volume = higher score
    - Health Score (20%): Based on recent failure rate and uptime
    - Capacity Score (10%): Available headroom before saturation

Zero-Cost: Uses in-process scoring and asyncio timers.
No external dependencies beyond existing InfinityBridge infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger("infinity.path_optimizer")


# ── Enums ────────────────────────────────────────────────────────────────────


class PathHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    CLOSED = "closed"


class OptimizationStrategy(str, Enum):
    LOWEST_LATENCY = "lowest_latency"
    LEAST_LOADED = "least_loaded"
    BALANCED = "balanced"
    PRIORITY_WEIGHTED = "priority_weighted"


class RouteType(str, Enum):
    DIRECT = "direct"
    MULTI_HOP = "multi_hop"
    FALLBACK = "fallback"


# ── Models ───────────────────────────────────────────────────────────────────


class PathMetrics(BaseModel):
    """Real-time metrics for a bridge path."""

    path_id: str = ""
    source: str = ""
    target: str = ""
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    current_transitions: int = 0
    max_capacity: int = 1000
    error_rate: float = 0.0
    success_rate: float = 1.0
    uptime_percentage: float = 100.0
    health: PathHealth = PathHealth.UNKNOWN
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def utilization(self) -> float:
        return min(1.0, self.current_transitions / max(1, self.max_capacity))

    @property
    def available_capacity(self) -> float:
        return max(0.0, 1.0 - self.utilization)


class PathScore(BaseModel):
    """Score for a bridge path from the optimization algorithm."""

    path_id: str = ""
    source: str = ""
    target: str = ""
    total_score: float = 0.0
    latency_score: float = 0.0
    load_score: float = 0.0
    health_score: float = 0.0
    capacity_score: float = 0.0
    strategy: OptimizationStrategy = OptimizationStrategy.BALANCED
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OptimizedRoute(BaseModel):
    """An optimized route across the InfinityBridge."""

    route_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: str = ""
    target: str = ""
    route_type: RouteType = RouteType.DIRECT
    path_ids: List[str] = Field(default_factory=list)
    hops: List[str] = Field(default_factory=list)
    total_score: float = 0.0
    estimated_latency_ms: float = 0.0
    strategy: OptimizationStrategy = OptimizationStrategy.BALANCED
    is_fallback: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PathOptimizerConfig(BaseModel):
    """Configuration for the path optimizer."""

    strategy: OptimizationStrategy = OptimizationStrategy.BALANCED
    latency_weight: float = 0.4
    load_weight: float = 0.3
    health_weight: float = 0.2
    capacity_weight: float = 0.1
    degraded_latency_ms: float = 500.0
    unhealthy_latency_ms: float = 2000.0
    degraded_error_rate: float = 0.05
    unhealthy_error_rate: float = 0.15
    health_check_interval_seconds: int = 15
    metrics_retention_samples: int = 50
    max_hops: int = 3
    enable_multi_hop: bool = True
    enable_fallback: bool = True
    fallback_score_threshold: float = 0.3


# ── Path Scorer ──────────────────────────────────────────────────────────────


class PathScorer:
    """Scores bridge paths based on multiple criteria."""

    def __init__(self, config: Optional[PathOptimizerConfig] = None):
        self._config = config or PathOptimizerConfig()
        logger.info("PathScorer initialized (strategy=%s)", self._config.strategy.value)

    def score(self, metrics: PathMetrics) -> PathScore:
        """Calculate a composite score for a path."""
        # Latency score
        if metrics.avg_latency_ms <= 0:
            latency_score = 1.0
        elif metrics.avg_latency_ms < 100:
            latency_score = 1.0 - (metrics.avg_latency_ms / 200.0)
        elif metrics.avg_latency_ms < self._config.degraded_latency_ms:
            latency_score = (
                0.5
                - (metrics.avg_latency_ms - 100) / (self._config.degraded_latency_ms - 100) * 0.3
            )
        elif metrics.avg_latency_ms < self._config.unhealthy_latency_ms:
            latency_score = (
                0.2
                - (metrics.avg_latency_ms - self._config.degraded_latency_ms)
                / (self._config.unhealthy_latency_ms - self._config.degraded_latency_ms)
                * 0.15
            )
        else:
            latency_score = 0.05
        latency_score = max(0.0, min(1.0, latency_score))

        # Load score
        load_score = 1.0 - metrics.utilization
        load_score = max(0.0, min(1.0, load_score))

        # Health score
        health_scores = {
            PathHealth.HEALTHY: 1.0,
            PathHealth.DEGRADED: 0.5,
            PathHealth.UNHEALTHY: 0.15,
            PathHealth.UNKNOWN: 0.4,
            PathHealth.CLOSED: 0.0,
        }
        health_score = health_scores.get(metrics.health, 0.4)
        if metrics.error_rate > self._config.unhealthy_error_rate:
            health_score *= 0.2
        elif metrics.error_rate > self._config.degraded_error_rate:
            health_score *= 0.6

        # Capacity score
        capacity_score = metrics.available_capacity

        # Weights by strategy
        if self._config.strategy == OptimizationStrategy.LOWEST_LATENCY:
            weights = (0.7, 0.1, 0.1, 0.1)
        elif self._config.strategy == OptimizationStrategy.LEAST_LOADED:
            weights = (0.1, 0.7, 0.1, 0.1)
        elif self._config.strategy == OptimizationStrategy.PRIORITY_WEIGHTED:
            weights = (0.3, 0.2, 0.3, 0.2)
        else:
            weights = (
                self._config.latency_weight,
                self._config.load_weight,
                self._config.health_weight,
                self._config.capacity_weight,
            )

        total_score = (
            weights[0] * latency_score
            + weights[1] * load_score
            + weights[2] * health_score
            + weights[3] * capacity_score
        )
        total_score = max(0.0, min(1.0, total_score))

        return PathScore(
            path_id=metrics.path_id,
            source=metrics.source,
            target=metrics.target,
            total_score=total_score,
            latency_score=latency_score,
            load_score=load_score,
            health_score=health_score,
            capacity_score=capacity_score,
            strategy=self._config.strategy,
        )


# ── Health Monitor ───────────────────────────────────────────────────────────


class PathHealthMonitor:
    """Monitors path health and detects degradation."""

    def __init__(self, config: Optional[PathOptimizerConfig] = None):
        self._config = config or PathOptimizerConfig()
        self._latency_samples: Dict[str, deque] = {}
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._success_counts: Dict[str, int] = defaultdict(int)
        self._health_overrides: Dict[str, PathHealth] = {}
        self._lock = asyncio.Lock()
        logger.info("PathHealthMonitor initialized")

    async def record_latency(self, path_id: str, latency_ms: float) -> None:
        async with self._lock:
            if path_id not in self._latency_samples:
                self._latency_samples[path_id] = deque(
                    maxlen=self._config.metrics_retention_samples
                )
            self._latency_samples[path_id].append(latency_ms)

    async def record_transition(self, path_id: str, success: bool = True) -> None:
        async with self._lock:
            if success:
                self._success_counts[path_id] += 1
            else:
                self._error_counts[path_id] += 1

    async def get_path_metrics(
        self,
        path_id: str,
        source: str = "",
        target: str = "",
        max_capacity: int = 1000,
    ) -> PathMetrics:
        async with self._lock:
            samples = list(self._latency_samples.get(path_id, []))
            if samples:
                avg_latency = sum(samples) / len(samples)
                sorted_samples = sorted(samples)
                p99_index = int(len(sorted_samples) * 0.99)
                p99_latency = sorted_samples[min(p99_index, len(sorted_samples) - 1)]
            else:
                avg_latency = 0.0
                p99_latency = 0.0

            total = self._success_counts[path_id] + self._error_counts[path_id]
            error_rate = self._error_counts[path_id] / max(1, total)
            success_rate = self._success_counts[path_id] / max(1, total)

            health = self._determine_health(avg_latency, error_rate)
            if path_id in self._health_overrides:
                health = self._health_overrides[path_id]

            return PathMetrics(
                path_id=path_id,
                source=source,
                target=target,
                avg_latency_ms=round(avg_latency, 2),
                p99_latency_ms=round(p99_latency, 2),
                current_transitions=self._success_counts[path_id],
                max_capacity=max_capacity,
                error_rate=round(error_rate, 4),
                success_rate=round(success_rate, 4),
                health=health,
            )

    async def set_health_override(self, path_id: str, health: PathHealth) -> None:
        async with self._lock:
            self._health_overrides[path_id] = health

    async def clear_health_override(self, path_id: str) -> None:
        async with self._lock:
            self._health_overrides.pop(path_id, None)

    async def detect_degradation(self, path_id: str) -> Optional[Dict[str, Any]]:
        metrics = await self.get_path_metrics(path_id)
        if metrics.health in (PathHealth.HEALTHY, PathHealth.UNKNOWN):
            return None
        return {
            "path_id": path_id,
            "health": metrics.health.value,
            "avg_latency_ms": metrics.avg_latency_ms,
            "error_rate": metrics.error_rate,
            "degradation_type": "latency"
            if metrics.avg_latency_ms > self._config.degraded_latency_ms
            else "errors"
            if metrics.error_rate > self._config.degraded_error_rate
            else "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _determine_health(self, avg_latency: float, error_rate: float) -> PathHealth:
        if (
            avg_latency > self._config.unhealthy_latency_ms
            or error_rate > self._config.unhealthy_error_rate
        ):
            return PathHealth.UNHEALTHY
        if (
            avg_latency > self._config.degraded_latency_ms
            or error_rate > self._config.degraded_error_rate
        ):
            return PathHealth.DEGRADED
        if avg_latency == 0 and error_rate == 0:
            return PathHealth.UNKNOWN
        return PathHealth.HEALTHY


# ── Fallback Router ──────────────────────────────────────────────────────────


class FallbackRouter:
    """Provides fallback routing when primary paths are degraded."""

    def __init__(self, config: Optional[PathOptimizerConfig] = None):
        self._config = config or PathOptimizerConfig()
        self._topology: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
        logger.info("FallbackRouter initialized")

    async def register_path(self, source: str, target: str) -> None:
        async with self._lock:
            self._topology[source].add(target)
            self._topology[target].add(source)

    async def unregister_path(self, source: str, target: str) -> None:
        async with self._lock:
            self._topology[source].discard(target)
            self._topology[target].discard(source)

    async def find_alternative_paths(
        self,
        source: str,
        target: str,
        exclude_paths: Optional[Set[str]] = None,
    ) -> List[List[str]]:
        exclude = exclude_paths or set()
        routes: List[List[str]] = []
        async with self._lock:
            if target in self._topology.get(source, set()):
                direct_id = f"{source}→{target}"
                if direct_id not in exclude:
                    routes.append([source, target])
            if self._config.enable_multi_hop:
                visited: Set[str] = {source}
                queue: List[Tuple[str, List[str]]] = [(source, [source])]
                while queue and len(routes) < 5:
                    current, path = queue.pop(0)
                    if len(path) - 1 >= self._config.max_hops:
                        continue
                    for neighbor in self._topology.get(current, set()):
                        if neighbor in visited and neighbor != target:
                            continue
                        new_path = path + [neighbor]
                        if neighbor == target:
                            path_id = "→".join(new_path)
                            if path_id not in exclude:
                                routes.append(new_path)
                        else:
                            visited.add(neighbor)
                            queue.append((neighbor, new_path))
        return routes

    async def get_fallback_route(
        self,
        source: str,
        target: str,
        scored_paths: Dict[str, PathScore],
        health_monitor: PathHealthMonitor,
    ) -> Optional[OptimizedRoute]:
        if not self._config.enable_fallback:
            return None
        alternatives = await self.find_alternative_paths(source, target)
        if not alternatives:
            return None
        best_route = alternatives[0]
        return OptimizedRoute(
            source=source,
            target=target,
            route_type=RouteType.FALLBACK,
            path_ids=["→".join(best_route)],
            hops=best_route,
            strategy=OptimizationStrategy.BALANCED,
            is_fallback=True,
        )


# ── Path Optimization Engine ────────────────────────────────────────────────


class PathOptimizationEngine:
    """Main engine for path optimization across the InfinityBridge."""

    def __init__(
        self,
        config: Optional[PathOptimizerConfig] = None,
        bridge_path_manager: Any = None,
    ):
        self._config = config or PathOptimizerConfig()
        self._bridge_path_manager = bridge_path_manager
        self._scorer = PathScorer(self._config)
        self._health_monitor = PathHealthMonitor(self._config)
        self._fallback_router = FallbackRouter(self._config)
        self._path_registry: Dict[str, Tuple[str, str]] = {}
        self._path_capacities: Dict[str, int] = {}
        self._score_cache: Dict[str, PathScore] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        self._start_time: Optional[float] = None
        logger.info("PathOptimizationEngine initialized (strategy=%s)", self._config.strategy.value)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def config(self) -> PathOptimizerConfig:
        return self._config

    @property
    def health_monitor(self) -> PathHealthMonitor:
        return self._health_monitor

    @property
    def fallback_router(self) -> FallbackRouter:
        return self._fallback_router

    @property
    def scorer(self) -> PathScorer:
        return self._scorer

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("PathOptimizationEngine started")

    async def stop(self) -> None:
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        logger.info("PathOptimizationEngine stopped")

    def register_path(self, source: str, target: str, max_capacity: int = 1000) -> str:
        path_id = f"{source}→{target}"
        self._path_registry[path_id] = (source, target)
        self._path_capacities[path_id] = max_capacity
        logger.info("Path registered: %s (capacity=%d)", path_id, max_capacity)
        return path_id

    async def register_path_async(self, source: str, target: str, max_capacity: int = 1000) -> str:
        path_id = f"{source}→{target}"
        self._path_registry[path_id] = (source, target)
        self._path_capacities[path_id] = max_capacity
        await self._fallback_router.register_path(source, target)
        logger.info("Path registered: %s (capacity=%d)", path_id, max_capacity)
        return path_id

    async def unregister_path(self, source: str, target: str) -> None:
        path_id = f"{source}→{target}"
        self._path_registry.pop(path_id, None)
        self._path_capacities.pop(path_id, None)
        self._score_cache.pop(path_id, None)
        await self._fallback_router.unregister_path(source, target)

    async def record_latency(self, path_id: str, latency_ms: float) -> None:
        await self._health_monitor.record_latency(path_id, latency_ms)

    async def record_transition(self, path_id: str, success: bool = True) -> None:
        await self._health_monitor.record_transition(path_id, success)

    async def get_path_score(self, path_id: str) -> Optional[PathScore]:
        if path_id not in self._path_registry:
            return None
        source, target = self._path_registry[path_id]
        capacity = self._path_capacities.get(path_id, 1000)
        metrics = await self._health_monitor.get_path_metrics(path_id, source, target, capacity)
        score = self._scorer.score(metrics)
        async with self._lock:
            self._score_cache[path_id] = score
        return score

    async def get_optimal_route(
        self,
        source: str,
        target: str,
        strategy: Optional[OptimizationStrategy] = None,
    ) -> Optional[OptimizedRoute]:
        candidate_paths = {
            pid: (s, t)
            for pid, (s, t) in self._path_registry.items()
            if s == source and t == target
        }
        if not candidate_paths:
            if self._config.enable_fallback:
                return await self._fallback_router.get_fallback_route(
                    source,
                    target,
                    self._score_cache,
                    self._health_monitor,
                )
            return None
        scored: Dict[str, PathScore] = {}
        for path_id in candidate_paths:
            score = await self.get_path_score(path_id)
            if score:
                scored[path_id] = score
        if not scored:
            return None
        best_path_id = max(scored, key=lambda pid: scored[pid].total_score)
        best_score = scored[best_path_id]
        metrics = await self._health_monitor.get_path_metrics(best_path_id)
        return OptimizedRoute(
            source=source,
            target=target,
            route_type=RouteType.DIRECT,
            path_ids=[best_path_id],
            hops=[source, target],
            total_score=best_score.total_score,
            estimated_latency_ms=metrics.avg_latency_ms,
            strategy=strategy or self._config.strategy,
            is_fallback=False,
        )

    async def get_all_scores(self) -> Dict[str, PathScore]:
        scores = {}
        for path_id in self._path_registry:
            score = await self.get_path_score(path_id)
            if score:
                scores[path_id] = score
        return scores

    async def get_degraded_paths(self) -> List[Dict[str, Any]]:
        degraded = []
        for path_id in self._path_registry:
            degradation = await self._health_monitor.detect_degradation(path_id)
            if degradation:
                degraded.append(degradation)
        return degraded

    async def get_status(self) -> Dict[str, Any]:
        scores = await self.get_all_scores()
        degraded = await self.get_degraded_paths()
        return {
            "running": self._running,
            "strategy": self._config.strategy.value,
            "registered_paths": len(self._path_registry),
            "scored_paths": len(scores),
            "degraded_paths": len(degraded),
            "degradation_details": degraded,
            "config": self._config.model_dump(),
            "uptime_seconds": time.time() - self._start_time if self._start_time else 0,
        }

    async def _health_check_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._config.health_check_interval_seconds)
                if not self._running:
                    break
                for path_id in list(self._path_registry.keys()):
                    degradation = await self._health_monitor.detect_degradation(path_id)
                    if degradation:
                        logger.warning("Path degradation detected: %s", path_id)
                        await self.get_path_score(path_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in health check loop: %s", e)


# ── Module Singleton ─────────────────────────────────────────────────────────

_path_optimizer: Optional[PathOptimizationEngine] = None


def get_path_optimizer(
    config: Optional[PathOptimizerConfig] = None,
    bridge_path_manager: Any = None,
) -> PathOptimizationEngine:
    global _path_optimizer
    if _path_optimizer is None:
        _path_optimizer = PathOptimizationEngine(config, bridge_path_manager)
    return _path_optimizer
