"""
Liquid Time-Constant (LTC) adaptive router.

ODE-governed hidden state: dx/dt = -x/τ(u) + f(u)
where τ(u) is the input-dependent time constant — the "liquid" property.

When ncps + torch are available, uses CfC cells (Closed-form Continuous-time)
from MIT CSAIL for proper ODE-based routing. Otherwise uses a pure-Python
Euler-integration approximation that matches the qualitative behaviour.

All operations are synchronous; call from FastAPI via run_in_executor if needed.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

_NCPS_AVAILABLE = False
_TORCH_AVAILABLE = False

try:
    import torch  # type: ignore  # noqa: F401

    _TORCH_AVAILABLE = True
    try:
        from ncps.torch import CfC  # type: ignore  # noqa: F401
        from ncps.wirings import AutoNCP  # type: ignore  # noqa: F401

        _NCPS_AVAILABLE = True
    except ImportError:
        pass
except ImportError:
    pass


@dataclass
class RouteCell:
    """
    Single liquid neuron governing one route target (worker/endpoint).

    State x decays toward 0 at rate 1/tau, then recovers by input signal.
    tau is modulated by the input — high-pressure inputs shorten tau
    (faster response), low-pressure inputs extend tau (inertia).
    """

    name: str
    tau_base: float = 1.0  # baseline time constant (seconds)
    tau_min: float = 0.1  # minimum tau under pressure
    tau_max: float = 10.0  # maximum tau at rest
    state: float = 0.5  # x ∈ [0, 1] — current routing weight
    _last_update: float = field(default_factory=time.monotonic, repr=False)

    def step(self, signal: float, dt: float | None = None) -> float:
        """
        Euler integration step.

        signal: input pressure ∈ [0, 1] (e.g. normalised request rate)
        dt: elapsed time since last call (auto-computed if None)
        Returns updated routing weight.
        """
        now = time.monotonic()
        if dt is None:
            dt = now - self._last_update
        self._last_update = now

        # Modulate tau by signal — higher signal → shorter tau (responsive)
        tau = self.tau_base / (1.0 + signal * (self.tau_base / self.tau_min - 1.0))
        tau = max(self.tau_min, min(self.tau_max, tau))

        # Euler: dx = (-x/tau + signal) * dt
        dx = (-self.state / tau + signal) * dt
        self.state = max(0.0, min(1.0, self.state + dx))
        return self.state


@dataclass
class LiquidRoutingResult:
    target: str
    weight: float
    all_weights: Dict[str, float]
    method: str  # "ncps" | "ltc_euler"
    elapsed_ms: float


class LiquidRouter:
    """
    Multi-target liquid routing: distributes load using LTC neuron dynamics.

    Each target has a RouteCell whose state tracks "routing pressure".
    The router returns a softmax-normalised weight vector.

    When ncps is available, an offline-trained CfC network can replace
    the Euler cells for more accurate ODE-based routing. Use
    `enable_ncps(input_size, units)` to upgrade.

    Usage::

        router = LiquidRouter(["worker-a", "worker-b", "worker-c"])
        result = router.route(signals={"worker-a": 0.8, "worker-b": 0.3, "worker-c": 0.1})
        print(result.target)      # selected worker
        print(result.all_weights) # {"worker-a": 0.52, "worker-b": 0.31, ...}
    """

    def __init__(
        self,
        targets: List[str],
        tau_base: float = 1.0,
        softmax_temp: float = 1.0,
    ) -> None:
        self._cells: Dict[str, RouteCell] = {
            t: RouteCell(name=t, tau_base=tau_base) for t in targets
        }
        self._softmax_temp = softmax_temp
        self._ncps_model: Any = None
        self._method = "ltc_euler"

    def enable_ncps(self, input_size: int, units: int = 32) -> bool:
        """Upgrade to ncps CfC model if available. Returns True if activated."""
        if not _NCPS_AVAILABLE:
            return False
        try:
            from ncps.torch import CfC
            from ncps.wirings import AutoNCP

            wiring = AutoNCP(units=units, output_size=len(self._cells))
            self._ncps_model = CfC(input_size=input_size, wiring=wiring)
            self._ncps_model.eval()
            self._method = "ncps"
            return True
        except Exception:
            return False

    def _softmax(self, values: Dict[str, float]) -> Dict[str, float]:
        keys = list(values.keys())
        t = self._softmax_temp
        exp_vals = [math.exp(v / t) for v in values.values()]
        total = sum(exp_vals) or 1.0
        return {k: e / total for k, e in zip(keys, exp_vals, strict=False)}

    def route(
        self,
        signals: Dict[str, float] | None = None,
        dt: float | None = None,
    ) -> LiquidRoutingResult:
        """
        Compute routing weights and select highest-weight target.

        signals: per-target input pressures ∈ [0, 1]. Missing targets get 0.
        dt: time delta override (auto if None).
        """
        t0 = time.perf_counter()

        if self._ncps_model is not None:
            result = self._route_ncps(signals or {}, dt)
        else:
            result = self._route_euler(signals or {}, dt)

        result.elapsed_ms = (time.perf_counter() - t0) * 1000
        return result

    def _route_euler(self, signals: Dict[str, float], dt: float | None) -> LiquidRoutingResult:
        raw_weights: Dict[str, float] = {}
        for name, cell in self._cells.items():
            sig = max(0.0, min(1.0, signals.get(name, 0.0)))
            raw_weights[name] = cell.step(sig, dt)

        weights = self._softmax(raw_weights)
        target = max(weights, key=weights.get)
        return LiquidRoutingResult(
            target=target,
            weight=weights[target],
            all_weights=weights,
            method="ltc_euler",
            elapsed_ms=0.0,
        )

    def _route_ncps(self, signals: Dict[str, float], dt: float | None) -> LiquidRoutingResult:
        import torch

        sig_vals = [signals.get(n, 0.0) for n in self._cells]
        # CfC expects 3D input of shape (batch_size, seq_len, input_size)
        x = torch.tensor([[sig_vals]], dtype=torch.float32)
        timespan = torch.tensor([[dt or 1.0]], dtype=torch.float32)
        with torch.no_grad():
            out, _ = self._ncps_model(x, timespans=timespan)
        # out shape is (batch_size, seq_len, output_size); extract first step of first batch
        raw = {name: float(v) for name, v in zip(self._cells, out[0][0].tolist(), strict=False)}
        weights = self._softmax(raw)
        target = max(weights, key=weights.get)
        return LiquidRoutingResult(
            target=target,
            weight=weights[target],
            all_weights=weights,
            method="ncps",
            elapsed_ms=0.0,
        )

    def update_targets(self, targets: List[str], tau_base: float | None = None) -> None:
        """Add new targets or remove stale ones without full reset."""
        tau = tau_base or (list(self._cells.values())[0].tau_base if self._cells else 1.0)
        current = set(self._cells)
        new_set = set(targets)
        for t in new_set - current:
            self._cells[t] = RouteCell(name=t, tau_base=tau)
        for t in current - new_set:
            del self._cells[t]

    @property
    def targets(self) -> List[str]:
        return list(self._cells.keys())

    @property
    def method(self) -> str:
        return self._method
