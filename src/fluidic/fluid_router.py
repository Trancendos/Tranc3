# src/fluidic/fluid_router.py
# Fluidic router — adaptive request routing inspired by liquid neural networks
# Routes requests to the best available service based on health, load, and capability

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shared_core.models import ServiceHealth, ServiceInfo
from shared_core.registry import ServiceRegistry
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class RouteCell:
    """
    A single routing cell in the fluidic router.
    Inspired by liquid time-constant networks — each cell maintains
    a time-decaying state that influences routing decisions.
    """

    service_name: str
    weight: float = 1.0
    decay_rate: float = 0.1  # How quickly weight decays under load
    recovery_rate: float = 0.05  # How quickly weight recovers when idle
    last_used: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0
    response_times: List[float] = field(default_factory=list)
    max_history: int = 100

    @property
    def effective_weight(self) -> float:
        """Calculate effective weight based on health, response time, and error rate"""
        # Base weight
        w = self.weight

        # Error penalty
        if self.request_count > 0:
            error_rate = self.error_count / self.request_count
            w *= 1.0 - error_rate

        # Response time penalty (higher RT = lower weight)
        if self.response_times:
            avg_rt = sum(self.response_times[-20:]) / len(self.response_times[-20:])
            w *= 1.0 / (1.0 + avg_rt / 1000.0)  # Normalize to seconds

        # Time decay — weight recovers when idle
        idle_time = time.time() - self.last_used
        w += self.recovery_rate * idle_time

        return max(w, 0.01)  # Never zero

    def record_success(self, response_time: float) -> None:
        """Record a successful request"""
        self.request_count += 1
        self.last_used = time.time()
        self.response_times.append(response_time)
        if len(self.response_times) > self.max_history:
            self.response_times = self.response_times[-self.max_history :]

    def record_error(self) -> None:
        """Record a failed request"""
        self.request_count += 1
        self.error_count += 1
        self.last_used = time.time()

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "service": self.service_name,
            "weight": self.weight,
            "effective_weight": round(self.effective_weight, 3),
            "requests": self.request_count,
            "errors": self.error_count,
            "error_rate": (
                round(self.error_count / self.request_count, 3) if self.request_count > 0 else 0.0
            ),
            "avg_response_time": (
                round(sum(self.response_times[-20:]) / len(self.response_times[-20:]), 3)
                if self.response_times
                else 0.0
            ),
        }


class FluidicRouter:
    """
    Adaptive request router inspired by liquid neural networks.
    Routes requests to services based on real-time health, load, and performance.
    Weight-adjusted selection ensures traffic flows toward healthy services.
    """

    def __init__(self, registry: Optional[ServiceRegistry] = None):
        self.registry = registry or ServiceRegistry()
        self._cells: Dict[str, RouteCell] = {}

    def register_route(self, service_name: str, initial_weight: float = 1.0) -> None:
        """Register a service in the fluidic router"""
        self._cells[service_name] = RouteCell(
            service_name=service_name,
            weight=initial_weight,
        )
        logger.info(
            "Fluidic route registered: %s (weight=%s)",
            sanitize_for_log(service_name),
            sanitize_for_log(initial_weight),
        )  # codeql[py/cleartext-logging]

    def select(self, capability: str) -> Optional[ServiceInfo]:
        """
        Select the best service for a given capability using
        weighted random selection based on effective weights.
        """
        candidates = self.registry.find_by_capability(capability)
        if not candidates:
            return None

        # Get cells for available candidates
        available = []
        weights = []
        for svc in candidates:
            cell = self._cells.get(svc.name)
            if cell and svc.health != ServiceHealth.UNHEALTHY:
                available.append(svc)
                weights.append(cell.effective_weight)

        if not available:
            return None

        # Weighted random selection
        total = sum(weights)
        if total <= 0:
            return random.choice(available)  # nosec B311 — non-cryptographic random usage

        r = random.uniform(0, total)  # nosec B311 — non-cryptographic weighted routing
        cumulative = 0.0
        for svc, w in zip(available, weights, strict=False):
            cumulative += w
            if r <= cumulative:
                return svc

        return available[-1]  # Fallback

    def record_success(self, service_name: str, response_time: float) -> None:
        """Record a successful request to a service"""
        cell = self._cells.get(service_name)
        if cell:
            cell.record_success(response_time)

    def record_error(self, service_name: str) -> None:
        """Record a failed request to a service"""
        cell = self._cells.get(service_name)
        if cell:
            cell.record_error()

    @property
    def stats(self) -> Dict[str, Any]:
        """Get routing statistics for all cells"""
        return {
            "cells": {name: cell.stats for name, cell in self._cells.items()},
            "total_routes": sum(c.request_count for c in self._cells.values()),
        }


# Singleton
fluid_router = FluidicRouter()
