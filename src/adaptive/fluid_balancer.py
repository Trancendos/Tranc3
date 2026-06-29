"""
src/adaptive/fluid_balancer.py
===============================
Fluidic load balancer — treats traffic like fluid flow.

Bernoulli-inspired: high-pressure channels flow faster. Turbulence detection
identifies unstable providers.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class FluidChannel:
    """Represents a provider connection with flow rate and viscosity (latency)."""

    provider: str
    flow_rate: float = 1.0  # requests/second capacity
    viscosity: float = 1.0  # latency factor (lower = smoother = preferred)
    pressure: float = 0.0  # current load pressure
    current_requests: int = 0
    latency_samples: list[float] = field(default_factory=list)
    error_rate: float = 0.0

    MAX_SAMPLES = 20

    @property
    def reynolds_number(self) -> float:
        """Simplified Reynolds number: high → turbulent, low → laminar."""
        if self.viscosity == 0:
            return float("inf")
        return self.flow_rate / self.viscosity

    @property
    def turbulent(self) -> bool:
        """Re > 2300 indicates turbulence in classical fluid dynamics (scaled here)."""
        return self.reynolds_number > 5.0 or self.variance > 100.0

    @property
    def variance(self) -> float:
        if len(self.latency_samples) < 2:
            return 0.0
        return statistics.variance(self.latency_samples)

    def record_latency(self, latency_ms: float, success: bool) -> None:
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > self.MAX_SAMPLES:
            self.latency_samples.pop(0)
        if self.latency_samples:
            avg_latency = statistics.mean(self.latency_samples)
            self.viscosity = max(0.01, avg_latency / 1000.0)  # normalise to seconds
        if not success:
            self.error_rate = min(1.0, self.error_rate * 0.9 + 0.1)
        else:
            self.error_rate = max(0.0, self.error_rate * 0.95)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "flow_rate": round(self.flow_rate, 4),
            "viscosity": round(self.viscosity, 4),
            "pressure": round(self.pressure, 4),
            "current_requests": self.current_requests,
            "reynolds_number": round(self.reynolds_number, 2),
            "turbulent": self.turbulent,
            "variance_ms": round(self.variance, 2),
            "error_rate": round(self.error_rate, 4),
        }


class FluidBalancer:
    """Fluidic load balancer with Bernoulli-like distribution."""

    TURBULENCE_THRESHOLD = 5.0  # Reynolds number above which channel is turbulent

    def __init__(self) -> None:
        self._channels: dict[str, FluidChannel] = {}
        self._total_pressure: float = 0.0

    def add_channel(self, provider: str, flow_rate: float = 1.0) -> FluidChannel:
        ch = FluidChannel(provider=provider, flow_rate=flow_rate)
        self._channels[provider] = ch
        return ch

    def add_pressure(self, request_count: float) -> None:
        """Record arriving requests as system-level pressure (no per-channel distribution).

        Call assign_request(provider) when a request is routed to a specific channel
        so that per-channel pressure stays balanced with record_result's -1 decrement.
        """
        self._total_pressure += request_count

    def assign_request(self, provider: str) -> None:
        """Increment pressure on the specific channel handling a request.

        Must be paired with a record_result call when the request completes.
        """
        if provider in self._channels:
            self._channels[provider].pressure = max(0.0, self._channels[provider].pressure + 1)

    def flow(self) -> dict[str, float]:
        """Distribute load following Bernoulli-like principles.

        High flow_rate + low viscosity channels receive more traffic.
        Returns allocation dict: {provider: fraction}.
        """
        if not self._channels:
            return {}

        laminar = {p: ch for p, ch in self._channels.items() if not ch.turbulent}
        if not laminar:
            laminar = dict(self._channels)  # fall back to all channels

        # Bernoulli score: flow_rate / viscosity, penalised by in-flight pressure
        scores = {
            p: max(0.01, ch.flow_rate / max(ch.viscosity, 0.001) / max(1.0, ch.pressure))
            for p, ch in laminar.items()
        }
        total = sum(scores.values())
        return {p: s / total for p, s in scores.items()}

    def detect_turbulence(self) -> list[str]:
        """Return list of turbulent (unstable) providers."""
        return [p for p, ch in self._channels.items() if ch.turbulent]

    def laminar_route(self, request: dict[str, Any] | None = None) -> Optional[str]:
        """Route request proportionally to flow allocation (weighted random)."""
        import random

        allocation = self.flow()
        if not allocation:
            return None
        providers = list(allocation.keys())
        weights = [allocation[p] for p in providers]
        return random.choices(providers, weights=weights, k=1)[0]

    def turbulent_fallback(self, request: dict[str, Any] | None = None) -> Optional[str]:
        """Emergency routing when primary channels are turbulent — use lowest error rate."""
        candidates = sorted(
            self._channels.values(),
            key=lambda ch: (ch.error_rate, ch.viscosity),
        )
        return candidates[0].provider if candidates else None

    def record_result(self, provider: str, latency_ms: float, success: bool) -> None:
        if provider in self._channels:
            self._channels[provider].record_latency(latency_ms, success)
            # Relieve pressure on completion
            self._channels[provider].pressure = max(0.0, self._channels[provider].pressure - 1)
            self._total_pressure = max(0.0, self._total_pressure - 1)

    def system_state(self) -> dict[str, Any]:
        turbulent = self.detect_turbulence()
        allocation = self.flow()
        return {
            "total_pressure": round(self._total_pressure, 2),
            "turbulent_channels": turbulent,
            "allocation": {p: round(v, 4) for p, v in allocation.items()},
            "channels": {p: ch.to_dict() for p, ch in self._channels.items()},
        }
