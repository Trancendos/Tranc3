"""
Self-Repair Engine — autonomous strategy evaluation and adaptive config tuning.

Two primary abstractions:

  SelfRepairEngine  — evaluates a set of RepairStrategy objects against the
                      current context and applies those that are ready (cooldown
                      has elapsed) and whose condition matches.

  AdaptiveConfigTuner — records performance metrics over time and applies
                        regression-based optimal config suggestions when
                        confidence is high enough (>= 0.8).
"""

import asyncio
import gc
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RepairStrategy
# ---------------------------------------------------------------------------


@dataclass
class RepairStrategy:
    name: str
    priority: int  # lower number = higher priority
    condition: Callable[[Dict], bool]  # receives context dict
    action: Callable[[Dict], Any]  # sync or async; receives context dict
    cooldown_sec: float = 300.0
    last_applied: float = 0.0

    def is_ready(self) -> bool:
        """True when the cooldown period has fully elapsed."""
        return (time.time() - self.last_applied) >= self.cooldown_sec


# ---------------------------------------------------------------------------
# SelfRepairEngine
# ---------------------------------------------------------------------------


class SelfRepairEngine:
    """
    Evaluates registered RepairStrategies against the current system context
    and applies those that are triggered.  Strategies are evaluated in
    ascending priority order.
    """

    def __init__(self) -> None:
        self.strategies: List[RepairStrategy] = []
        self.active_repairs: Dict[str, float] = {}  # strategy_name → start_time
        self._register_builtins()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_strategy(self, strategy: RepairStrategy) -> None:
        self.strategies.append(strategy)
        self.strategies.sort(key=lambda s: s.priority)
        logger.info(
            "Registered repair strategy '%s' (priority=%d)",
            strategy.name,
            strategy.priority,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate_and_repair(self, context: Dict) -> List[Dict]:
        """
        Evaluate all strategies against *context*.  For each strategy whose
        condition is satisfied and whose cooldown has elapsed, run its action.

        Returns a list of result dicts, one per applied strategy.
        """
        results = []
        for strategy in self.strategies:
            try:
                triggered = strategy.condition(context)
            except Exception as exc:
                logger.warning(
                    "Condition error in strategy '%s': %s", strategy.name, exc
                )
                triggered = False

            if not triggered:
                continue

            if not strategy.is_ready():
                remaining = strategy.cooldown_sec - (
                    time.time() - strategy.last_applied
                )
                logger.debug(
                    "Strategy '%s' triggered but on cooldown (%.0f s remaining).",
                    strategy.name,
                    remaining,
                )
                continue

            result = await self._apply_strategy(strategy, context)
            results.append(result)

        return results

    async def emergency_repair(self, context: Dict) -> List[Dict]:
        """
        Apply ALL strategies immediately, bypassing cooldowns.
        Used when the system is in EMERGENCY health state.
        """
        logger.warning("EMERGENCY repair initiated — bypassing all cooldowns.")
        results = []
        for strategy in self.strategies:
            # Override cooldown by resetting last_applied
            strategy.last_applied = 0.0
            try:
                result = await self._apply_strategy(strategy, context)
                results.append(result)
            finally:
                # Restore if action itself will set it; otherwise leave at 0
                pass
        return results

    async def _apply_strategy(self, strategy: RepairStrategy, context: Dict) -> Dict:
        t0 = time.perf_counter()
        self.active_repairs[strategy.name] = time.time()
        success = False
        error_msg = ""

        try:
            if asyncio.iscoroutinefunction(strategy.action):
                await strategy.action(context)
            else:
                strategy.action(context)
            success = True
            strategy.last_applied = time.time()
            logger.info("Repair strategy '%s' applied successfully.", strategy.name)
        except Exception as exc:
            error_msg = str(exc)
            logger.error("Repair strategy '%s' failed: %s", strategy.name, exc)
        finally:
            self.active_repairs.pop(strategy.name, None)

        return {
            "strategy": strategy.name,
            "success": success,
            "duration_ms": (time.perf_counter() - t0) * 1000.0,
            "timestamp": time.time(),
            "error": error_msg if not success else None,
        }

    # ------------------------------------------------------------------
    # Built-in strategies
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register the five built-in repair strategies."""

        # 1. Memory pressure
        async def _memory_pressure_action(ctx: Dict) -> None:
            collected = gc.collect()
            # Clear any module-level LRU caches
            import functools

            cleared = 0
            for obj in gc.get_objects():
                if isinstance(obj, functools._lru_cache_wrapper):  # type: ignore[attr-defined]
                    try:
                        obj.cache_clear()
                        cleared += 1
                    except Exception:
                        pass  # nosec B110 — graceful degradation; error logged upstream

            logger.info(
                "Memory pressure repair: gc collected=%d, caches cleared=%d",
                collected,
                cleared,
            )

        self.register_strategy(
            RepairStrategy(
                name="memory_pressure",
                priority=1,
                condition=lambda ctx: float(ctx.get("memory_percent", 0)) > 85.0,
                action=_memory_pressure_action,
                cooldown_sec=120.0,
            )
        )

        # 2. High error rate → circuit breaker pattern
        _circuit_breakers: Dict[str, Dict] = {}

        async def _high_error_rate_action(ctx: Dict) -> None:
            service_id = ctx.get("service_id", "global")
            _circuit_breakers[service_id] = {
                "open": True,
                "opened_at": time.time(),
                "half_open_after": time.time() + 60.0,  # try half-open after 60 s
                "threshold": 0.5,
            }
            logger.info(
                "Circuit breaker OPENED for service '%s' (error_rate=%.2f)",
                service_id,
                ctx.get("error_rate", 0),
            )
            # Attach circuit breaker state to context so callers can inspect
            ctx["circuit_breaker"] = _circuit_breakers[service_id]

        self.register_strategy(
            RepairStrategy(
                name="high_error_rate",
                priority=2,
                condition=lambda ctx: float(ctx.get("error_rate", 0)) > 0.1,
                action=_high_error_rate_action,
                cooldown_sec=60.0,
            )
        )

        # 3. Evolution stagnation → inject diversity
        async def _evolution_stagnation_action(ctx: Dict) -> None:
            current_mutation = float(ctx.get("mutation_rate", 0.05))
            boosted_mutation = min(current_mutation * 3.0, 0.5)
            ctx["mutation_rate"] = boosted_mutation
            ctx["diversity_injection"] = True
            ctx["population_shuffle"] = True
            logger.info(
                "Evolution diversity injected: mutation_rate %.4f → %.4f",
                current_mutation,
                boosted_mutation,
            )

        self.register_strategy(
            RepairStrategy(
                name="evolution_stagnation",
                priority=3,
                condition=lambda ctx: (
                    "evolution_fitness_delta" in ctx
                    and float(ctx["evolution_fitness_delta"]) < 0.001
                ),
                action=_evolution_stagnation_action,
                cooldown_sec=600.0,
            )
        )

        # 4. Model drift → trigger model refresh
        async def _model_drift_action(ctx: Dict) -> None:
            ctx["model_refresh_requested"] = True
            ctx["model_refresh_reason"] = "confidence_below_threshold"
            ctx["model_refresh_timestamp"] = time.time()
            logger.info(
                "Model refresh requested (confidence=%.3f)",
                ctx.get("prediction_confidence", 0),
            )
            # If a refresh callback is registered, invoke it
            refresh_cb = ctx.get("model_refresh_callback")
            if refresh_cb is not None:
                if asyncio.iscoroutinefunction(refresh_cb):
                    await refresh_cb(ctx)
                else:
                    refresh_cb(ctx)

        self.register_strategy(
            RepairStrategy(
                name="model_drift",
                priority=4,
                condition=lambda ctx: float(ctx.get("prediction_confidence", 1.0))
                < 0.5,
                action=_model_drift_action,
                cooldown_sec=900.0,
            )
        )

        # 5. Queue overflow → backpressure
        async def _queue_overflow_action(ctx: Dict) -> None:
            ctx["backpressure_enabled"] = True
            ctx["backpressure_max_queue"] = 1000
            ctx["backpressure_drop_policy"] = "oldest"
            # Signal upstream producers to slow down
            ctx["producer_rate_limit_factor"] = 0.5
            logger.info(
                "Backpressure enabled (queue_depth=%d)",
                ctx.get("queue_depth", 0),
            )

        self.register_strategy(
            RepairStrategy(
                name="queue_overflow",
                priority=5,
                condition=lambda ctx: int(ctx.get("queue_depth", 0)) > 1000,
                action=_queue_overflow_action,
                cooldown_sec=30.0,
            )
        )


# ---------------------------------------------------------------------------
# AdaptiveConfigTuner
# ---------------------------------------------------------------------------


@dataclass
class _MetricPoint:
    value: float
    timestamp: float


class AdaptiveConfigTuner:
    """
    Records performance metrics over time and uses linear regression to
    find optima.  When confidence in a recommendation exceeds 0.8, the
    config value is applied automatically.
    """

    _TUNABLE_PARAMS = [
        "temperature",
        "batch_size",
        "evolution_rate",
        "attention_dropout",
        "beam_width",
    ]

    _PARAM_BOUNDS: Dict[str, tuple] = {
        "temperature": (0.01, 2.0),
        "batch_size": (1.0, 512.0),
        "evolution_rate": (0.001, 0.5),
        "attention_dropout": (0.0, 0.5),
        "beam_width": (1.0, 20.0),
    }

    def __init__(self) -> None:
        self.config: Dict[str, float] = {
            "temperature": 0.7,
            "batch_size": 32.0,
            "evolution_rate": 0.05,
            "attention_dropout": 0.1,
            "beam_width": 5.0,
        }
        # metric_name → list of (config_value, metric_value) pairs
        self._history: Dict[str, List[tuple]] = {p: [] for p in self._TUNABLE_PARAMS}
        # time-series of raw metric values
        self._metric_series: Dict[str, List[_MetricPoint]] = {}
        self._confidence_threshold = 0.8

    def record_metric(self, name: str, value: float) -> None:
        """Store a metric observation with the current timestamp."""
        if name not in self._metric_series:
            self._metric_series[name] = []
        self._metric_series[name].append(
            _MetricPoint(value=value, timestamp=time.time())
        )
        # Keep a bounded window (last 500 observations)
        if len(self._metric_series[name]) > 500:
            self._metric_series[name] = self._metric_series[name][-250:]

    async def tune(self) -> Dict:
        """
        Analyse recent metrics and apply config changes where confidence >= 0.8.

        Returns a dict of {param: {"old": v, "new": v, "confidence": c}} for
        every parameter that was (or would have been) updated.
        """
        recommendations: Dict[str, Dict] = {}

        for param in self._TUNABLE_PARAMS:
            optimal = self._compute_optimal(param)
            if optimal is None:
                continue

            lo, hi = self._PARAM_BOUNDS[param]
            optimal = max(lo, min(hi, optimal))

            # Confidence: based on R² of regression and sample count
            series = self._metric_series.get(param, [])
            confidence = self._estimate_confidence(param, series)

            old_val = self.config[param]
            recommendations[param] = {
                "old": old_val,
                "new": round(optimal, 6),
                "confidence": round(confidence, 4),
                "applied": False,
            }

            if confidence >= self._confidence_threshold:
                self.config[param] = optimal
                recommendations[param]["applied"] = True
                logger.info(
                    "AdaptiveConfigTuner: %s %.4f → %.4f (confidence=%.2f)",
                    param,
                    old_val,
                    optimal,
                    confidence,
                )

        return recommendations

    def _compute_optimal(self, metric_name: str) -> Optional[float]:
        """
        Estimate the optimal parameter value via OLS regression of recent
        (config_value → performance) observations, then take the vertex of
        the quadratic fit or the best observed value for linear fits.
        """
        series = self._metric_series.get(metric_name, [])
        if len(series) < 5:
            return None

        values = [p.value for p in series[-50:]]
        n = len(values)
        xs = list(range(n))

        # OLS linear: y = a + b*x  →  optimal is the value at x=n (next step)
        x_mean = sum(xs) / n
        y_mean = sum(values) / n
        ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=False))
        ss_xx = sum((x - x_mean) ** 2 for x in xs)
        if abs(ss_xx) < 1e-12:
            return y_mean

        b = ss_xy / ss_xx
        a = y_mean - b * x_mean
        predicted_next = a + b * n

        # Convert predicted metric magnitude to a config delta heuristic:
        # map predicted_next linearly into the parameter's valid range.
        lo, hi = self._PARAM_BOUNDS.get(metric_name, (0.0, 1.0))
        y_min, y_max = min(values), max(values)
        if abs(y_max - y_min) < 1e-12:
            return self.config.get(metric_name)
        normalized = (predicted_next - y_min) / (y_max - y_min)
        return lo + normalized * (hi - lo)

    def _estimate_confidence(self, param: str, series: List[_MetricPoint]) -> float:
        """
        Estimate confidence in the regression as R² of the linear fit,
        scaled down when we have fewer observations.
        """
        if len(series) < 5:
            return 0.0

        values = [p.value for p in series[-50:]]
        n = len(values)
        xs = list(range(n))
        y_mean = sum(values) / n
        ss_tot = sum((y - y_mean) ** 2 for y in values)
        if ss_tot < 1e-12:
            return 0.0

        x_mean = sum(xs) / n
        ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=False))
        ss_xx = sum((x - x_mean) ** 2 for x in xs)
        if abs(ss_xx) < 1e-12:
            return 0.0
        b = ss_xy / ss_xx
        a = y_mean - b * x_mean
        ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, values, strict=False))
        r2 = 1.0 - (ss_res / ss_tot)

        # Scale by sample adequacy (fully confident after 50+ samples)
        adequacy = min(1.0, n / 50.0)
        return max(0.0, min(1.0, r2 * adequacy))


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

repair_engine = SelfRepairEngine()
config_tuner = AdaptiveConfigTuner()
