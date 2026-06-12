# src/evolution/adaptive_tuner.py
# Adaptive parameter tuning — runtime optimization using feedback loops

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Optional PSO acceleration via pyswarms
try:
    import numpy as np
    import pyswarms as ps
    _PSO_AVAILABLE = True
except ImportError:
    _PSO_AVAILABLE = False

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class Parameter:
    """A tunable parameter with bounds and current value"""

    name: str
    value: float
    min_value: float
    max_value: float
    step_size: float = 0.1
    history: List[float] = field(default_factory=list)
    max_history: int = 100

    def mutate(self) -> float:
        """Apply a random mutation to the parameter"""
        delta = random.uniform(-self.step_size, self.step_size)  # nosec B311 — non-cryptographic random usage

        new_value = max(self.min_value, min(self.max_value, self.value + delta))
        self.value = new_value
        self.history.append(new_value)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]
        return new_value

    def reset(self, value: Optional[float] = None) -> None:
        """Reset to a specific value or the midpoint"""
        self.value = value if value is not None else (self.min_value + self.max_value) / 2
        self.history.clear()


class AdaptiveTuner:
    """
    Runtime parameter tuner using hill climbing and simulated annealing.
    Continuously optimizes parameters based on a fitness function.
    """

    def __init__(
        self,
        fitness_fn: Callable[[Dict[str, float]], float],
        initial_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.fitness_fn = fitness_fn
        self._parameters: Dict[str, Parameter] = {}
        self._best_fitness = float("-inf")
        self._best_params: Dict[str, float] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

        if initial_params:
            for name, config in initial_params.items():
                self.add_parameter(
                    name,
                    config.get("value", 0.5),
                    config.get("min", 0.0),
                    config.get("max", 1.0),
                    config.get("step", 0.1),
                )

    def add_parameter(
        self,
        name: str,
        initial: float,
        min_value: float,
        max_value: float,
        step_size: float = 0.1,
    ) -> None:
        self._parameters[name] = Parameter(
            name=name,
            value=initial,
            min_value=min_value,
            max_value=max_value,
            step_size=step_size,
        )
        self._best_params[name] = initial

    async def start(self, interval: float = 60.0) -> None:
        self._running = True
        self._task = asyncio.create_task(self._tune_loop(interval))
        logger.info("AdaptiveTuner started (interval=%ss)", sanitize_for_log(interval))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _tune_loop(self, interval: float) -> None:
        while self._running:
            try:
                await asyncio.sleep(interval)
                await self.tune_step()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Tuning loop error: %s", sanitize_for_log(e))

    async def tune_step(self) -> Dict[str, Any]:
        current_params = {name: p.value for name, p in self._parameters.items()}
        current_fitness = await self._evaluate_fitness(current_params)

        best_mutation = None
        best_mutation_fitness = current_fitness

        for name, param in self._parameters.items():
            old_value = param.value
            param.mutate()

            mutated_params = {n: p.value for n, p in self._parameters.items()}
            mutated_fitness = await self._evaluate_fitness(mutated_params)

            if mutated_fitness > best_mutation_fitness:
                best_mutation = name
                best_mutation_fitness = mutated_fitness
            else:
                param.value = old_value

        if best_mutation_fitness > self._best_fitness:
            self._best_fitness = best_mutation_fitness
            self._best_params = {name: p.value for name, p in self._parameters.items()}
            logger.info(
                "New best fitness: %s (params: %s)",
                sanitize_for_log(f"{self._best_fitness:.4f}"),
                sanitize_for_log(self._best_params),
            )

        return {
            "current_fitness": current_fitness,
            "best_fitness": self._best_fitness,
            "best_params": self._best_params,
            "mutation": best_mutation,
        }

    async def _evaluate_fitness(self, params: Dict[str, float]) -> float:
        try:
            if asyncio.iscoroutinefunction(self.fitness_fn):
                return await self.fitness_fn(params)
            else:
                return self.fitness_fn(params)
        except Exception as e:
            logger.error("Fitness evaluation error: %s", sanitize_for_log(e))
            return float("-inf")

    def get_params(self) -> Dict[str, float]:
        return {name: p.value for name, p in self._parameters.items()}

    def set_params(self, params: Dict[str, float]) -> None:
        for name, value in params.items():
            if name in self._parameters:
                self._parameters[name].value = value

    def stats(self) -> Dict[str, Any]:
        return {
            "parameters": {
                name: {"value": p.value, "min": p.min_value, "max": p.max_value}
                for name, p in self._parameters.items()
            },
            "best_fitness": self._best_fitness,
            "best_params": self._best_params,
        }

    def pso_optimize(self, n_particles: int = 20, iters: int = 50) -> Dict[str, float]:
        """Run Particle Swarm Optimization over the parameter space.

        Falls back to current best params if pyswarms is unavailable.
        Use for high-dimensional spaces (10+ parameters) where hill climbing stalls.
        """
        if not _PSO_AVAILABLE or not self._parameters:
            return self.get_params()

        param_names = list(self._parameters.keys())
        n_dims = len(param_names)
        bounds = (
            np.array([self._parameters[n].min_value for n in param_names]),
            np.array([self._parameters[n].max_value for n in param_names]),
        )

        def _cost(particles: np.ndarray, **kwargs) -> np.ndarray:
            costs = np.zeros(len(particles))
            for i, particle in enumerate(particles):
                params = {n: float(v) for n, v in zip(param_names, particle)}
                try:
                    fitness = self.fitness_fn(params) if not asyncio.iscoroutinefunction(self.fitness_fn) else 0.0
                    costs[i] = -fitness  # PSO minimises; negate for fitness maximisation
                except Exception:
                    costs[i] = 1e9
            return costs

        try:
            options = {"c1": 0.5, "c2": 0.3, "w": 0.9}
            optimizer = ps.single.GlobalBestPSO(
                n_particles=n_particles, dimensions=n_dims, options=options, bounds=bounds
            )
            best_cost, best_pos = optimizer.optimize(_cost, iters=iters, verbose=False)
            best_params = {n: float(v) for n, v in zip(param_names, best_pos)}
            self.set_params(best_params)
            fitness = -best_cost
            if fitness > self._best_fitness:
                self._best_fitness = fitness
                self._best_params = best_params.copy()
            logger.info("PSO optimization complete: fitness=%.4f params=%s", fitness, best_params)
            return best_params
        except Exception as e:
            logger.warning("PSO optimization failed, using current params: %s", e)
            return self.get_params()
