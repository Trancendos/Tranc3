"""
Nano Mesh — Sub-Millisecond In-Process Function Routing
=========================================================
Routes calls to registered in-process functions using the same
circuit-breaker + weighted-selection pattern as the ServiceMesh,
but without HTTP overhead — pure Python coroutine dispatch.

Use for:
  - Intra-worker function routing (nanoservice pattern)
  - A/B testing function variants
  - Canary function rollout
  - In-process circuit breaking for CPU-heavy operations

Zero-cost: stdlib only. No network I/O.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("tranc3.mesh.nano_mesh")

# ── Types ──────────────────────────────────────────────────────────────────────


@dataclass
class NanoFunction:
    """A registered in-process callable with health tracking."""

    name: str
    fn: Callable[..., Awaitable[Any]]
    weight: float = 1.0
    version: str = "1.0.0"
    is_canary: bool = False
    canary_pct: float = 0.0  # 0-100 traffic percentage for canary

    # Runtime stats
    call_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""
    open_until: float = 0.0  # circuit-open timestamp

    @property
    def error_rate(self) -> float:
        return self.error_count / self.call_count if self.call_count > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.call_count if self.call_count > 0 else 0.0

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self.open_until

    @property
    def effective_weight(self) -> float:
        if self.circuit_open:
            return 0.0
        w = self.weight * (1.0 - self.error_rate)
        if self.avg_latency_ms > 0:
            w *= 1.0 / (1.0 + self.avg_latency_ms / 100.0)
        return max(w, 0.001)

    def record_success(self, latency_ms: float) -> None:
        self.call_count += 1
        self.total_latency_ms += latency_ms

    def record_error(self, error: str) -> None:
        self.call_count += 1
        self.error_count += 1
        self.last_error = error
        # Open circuit after 5 consecutive errors (simple heuristic)
        if self.error_rate > 0.5 and self.call_count >= 5:
            self.open_until = time.monotonic() + 30.0
            logger.warning("nano_mesh: circuit opened for %s (error_rate=%.1f%%)", self.name, self.error_rate * 100)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "is_canary": self.is_canary,
            "weight": self.weight,
            "effective_weight": round(self.effective_weight, 3),
            "calls": self.call_count,
            "errors": self.error_count,
            "error_rate_pct": round(self.error_rate * 100, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "circuit_open": self.circuit_open,
        }


# ── Nano Mesh ──────────────────────────────────────────────────────────────────


class NanoMesh:
    """
    In-process function router.

    Features:
    - Weighted random selection among registered variants
    - Per-function circuit breaking (opens after >50% errors over ≥5 calls)
    - Canary routing (send X% traffic to new function version)
    - Power-of-Two-Choices selection for low-latency routing
    - Automatic fallback to healthiest function

    Usage::

        mesh = NanoMesh()

        @mesh.register("embed", weight=1.0)
        async def embed_v1(text: str) -> list[float]:
            ...

        @mesh.register("embed", weight=0.1, is_canary=True, canary_pct=10)
        async def embed_v2(text: str) -> list[float]:
            ...

        result = await mesh.call("embed", text="hello world")
    """

    def __init__(self) -> None:
        self._functions: dict[str, list[NanoFunction]] = {}

    # ── Registration ───────────────────────────────────────────────────────

    def register(
        self,
        capability: str,
        weight: float = 1.0,
        version: str = "1.0.0",
        is_canary: bool = False,
        canary_pct: float = 0.0,
    ) -> Callable:
        """Decorator: register an async function as a nano capability."""
        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            nano = NanoFunction(
                name=fn.__name__,
                fn=fn,
                weight=weight,
                version=version,
                is_canary=is_canary,
                canary_pct=canary_pct,
            )
            self._functions.setdefault(capability, []).append(nano)
            logger.debug(
                "nano_mesh: registered %s.%s (weight=%.2f, canary=%s)",
                capability, fn.__name__, weight, is_canary,
            )
            return fn
        return decorator

    def add(self, capability: str, fn: Callable, **kwargs: Any) -> NanoFunction:
        """Imperatively register a function as a nano capability."""
        nano = NanoFunction(name=fn.__name__, fn=fn, **kwargs)
        self._functions.setdefault(capability, []).append(nano)
        return nano

    # ── Selection ──────────────────────────────────────────────────────────

    def _select(self, capability: str) -> Optional[NanoFunction]:
        """Select best function using Power-of-Two-Choices + weighted random."""
        pool = [f for f in self._functions.get(capability, []) if not f.circuit_open]
        if not pool:
            return None
        if len(pool) == 1:
            return pool[0]

        # Power-of-Two-Choices: pick 2 random candidates, take higher effective weight
        if len(pool) >= 2:
            a, b = random.sample(pool, 2)  # nosec B311
            return a if a.effective_weight >= b.effective_weight else b

        return pool[0]

    def _select_canary(self, capability: str) -> Optional[NanoFunction]:
        """Route to canary version based on configured canary_pct."""
        canaries = [
            f for f in self._functions.get(capability, [])
            if f.is_canary and not f.circuit_open
        ]
        if not canaries:
            return None
        canary = canaries[0]
        if random.random() * 100 < canary.canary_pct:  # nosec B311
            return canary
        return None

    # ── Dispatch ───────────────────────────────────────────────────────────

    async def call(self, capability: str, *args: Any, **kwargs: Any) -> Any:
        """
        Dispatch to best registered function for capability.
        Canary routing → weighted selection → circuit-open fallback.
        """
        # Try canary first
        target = self._select_canary(capability) or self._select(capability)

        if target is None:
            # Try circuit-open functions as last resort (half-open probe)
            all_fns = self._functions.get(capability, [])
            if all_fns:
                target = all_fns[0]
                logger.warning("nano_mesh: all circuits open for %s — probing %s", capability, target.name)
            else:
                raise RuntimeError(f"nano_mesh: no function registered for capability '{capability}'")

        t0 = time.monotonic()
        try:
            result = await target.fn(*args, **kwargs)
            latency_ms = (time.monotonic() - t0) * 1000
            target.record_success(latency_ms)
            return result
        except Exception as exc:
            target.record_error(str(exc))
            # Fallback to next best
            fallback = self._select(capability)
            if fallback and fallback is not target:
                logger.warning(
                    "nano_mesh: %s failed (%s), falling back to %s",
                    target.name, exc, fallback.name,
                )
                t0 = time.monotonic()
                result = await fallback.fn(*args, **kwargs)
                fallback.record_success((time.monotonic() - t0) * 1000)
                return result
            raise

    # ── Stats ──────────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        return {
            cap: [f.stats for f in fns]
            for cap, fns in self._functions.items()
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_nano_mesh: Optional[NanoMesh] = None


def get_nano_mesh() -> NanoMesh:
    global _nano_mesh
    if _nano_mesh is None:
        _nano_mesh = NanoMesh()
    return _nano_mesh


__all__ = ["NanoFunction", "NanoMesh", "get_nano_mesh"]
