"""
Adaptive zero-cost provider rotation.

Rotates among **approved free-tier** cloud providers when local Ollama is
unavailable or rate-limited, without selecting paid tiers.

Environment:
  ADAPTIVE_ROTATION_ENABLED=true
  ADAPTIVE_ROTATION_CHAIN=zero_cost_cloud | zero_cost_full | zero_cost_high_throughput
  ADAPTIVE_COOLDOWN_SECONDS=300
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from src.ai_gateway.zero_cost_config import ROUTING_CHAINS, discover_available_providers

logger = logging.getLogger("tranc3.adaptive.rotator")

# Only chains with $0.00 estimated cost
_ZERO_COST_CHAINS = {
    "zero_cost_full",
    "zero_cost_cloud",
    "zero_cost_reasoning",
    "zero_cost_high_throughput",
}

# Paid chain excluded from automatic rotation
_PAID_PROVIDERS = frozenset({"deepseek"})


@dataclass
class ProviderHealth:
    name: str
    available: bool
    failures: int = 0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0
    cooldown_until: float = 0.0


@dataclass
class RotationState:
    chain_name: str
    providers: list[str]
    index: int = 0
    health: dict[str, ProviderHealth] = field(default_factory=dict)
    last_rotation_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_name": self.chain_name,
            "providers": self.providers,
            "active_index": self.index,
            "active_provider": self.providers[self.index] if self.providers else None,
            "last_rotation_at": self.last_rotation_at,
            "health": {
                k: {
                    "available": v.available,
                    "failures": v.failures,
                    "cooldown_until": v.cooldown_until,
                }
                for k, v in self.health.items()
            },
        }


class AdaptiveProviderRotator:
    """Round-robin + cooldown rotation across zero-cost provider chains."""

    def __init__(self) -> None:
        from src.platform.infrastructure_mode import default_rotation_chain, get_infrastructure_mode

        self._cooldown = float(os.environ.get("ADAPTIVE_COOLDOWN_SECONDS", "300"))
        chain = default_rotation_chain()
        if chain not in ROUTING_CHAINS or chain not in _ZERO_COST_CHAINS:
            chain = "zero_cost_cloud"
        self._state = self._build_state(chain)
        logger.info(
            "Adaptive rotator mode=%s chain=%s providers=%s",
            get_infrastructure_mode().value,
            chain,
            self._state.providers,
        )

    def _build_state(self, chain_name: str) -> RotationState:
        chain = ROUTING_CHAINS[chain_name]
        discovered = discover_available_providers()
        providers = [
            p
            for p in chain.providers
            if p not in _PAID_PROVIDERS and (p == "offline" or discovered.get(p, False))
        ]
        if "offline" not in providers:
            providers.append("offline")
        health = {
            p: ProviderHealth(name=p, available=discovered.get(p, p == "offline"))
            for p in providers
        }
        return RotationState(chain_name=chain_name, providers=providers, health=health)

    def refresh_availability(self) -> None:
        discovered = discover_available_providers()
        for name, h in self._state.health.items():
            if name == "offline":
                h.available = True
            else:
                h.available = discovered.get(name, False)
            if h.cooldown_until and time.monotonic() >= h.cooldown_until:
                h.cooldown_until = 0.0
                h.failures = 0

    def active_provider(self) -> str | None:
        self.refresh_availability()
        if not self._state.providers:
            return "offline"
        now = time.monotonic()
        for _ in range(len(self._state.providers)):
            name = self._state.providers[self._state.index]
            h = self._state.health.get(name)
            if h and h.available and now >= h.cooldown_until:
                return name
            self._rotate()
        return "offline"

    def record_success(self, provider: str) -> None:
        h = self._state.health.get(provider)
        if h:
            h.last_success_at = time.monotonic()
            h.failures = 0
            h.cooldown_until = 0.0

    def record_failure(self, provider: str, *, rate_limited: bool = False) -> None:
        h = self._state.health.get(provider)
        if not h:
            return
        h.failures += 1
        h.last_failure_at = time.monotonic()
        if rate_limited or h.failures >= 3:
            h.cooldown_until = time.monotonic() + self._cooldown
            h.available = False
            logger.warning("Provider %s on cooldown %.0fs", provider, self._cooldown)
        self._rotate()

    def _rotate(self) -> None:
        if not self._state.providers:
            return
        self._state.index = (self._state.index + 1) % len(self._state.providers)
        self._state.last_rotation_at = time.monotonic()

    def switch_chain(self, chain_name: str) -> bool:
        if chain_name not in _ZERO_COST_CHAINS:
            return False
        self._state = self._build_state(chain_name)
        return True

    def status(self) -> dict[str, Any]:
        from src.platform.infrastructure_mode import infrastructure_status

        self.refresh_availability()
        return {
            "enabled": os.environ.get("ADAPTIVE_ROTATION_ENABLED", "true").lower()
            in ("1", "true", "yes"),
            "cooldown_seconds": self._cooldown,
            "infrastructure": infrastructure_status(),
            "state": self._state.to_dict(),
            "discovered": discover_available_providers(),
        }


_rotator: AdaptiveProviderRotator | None = None


def get_provider_rotator() -> AdaptiveProviderRotator:
    global _rotator
    if _rotator is None:
        _rotator = AdaptiveProviderRotator()
    return _rotator
