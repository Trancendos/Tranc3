"""Adaptive provider rotation with zero-cost quota hard-stops."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.zero_cost.quota_tracker import get_quota_tracker
from src.zero_cost.registry import assert_zero_cost, get_chain

DEFAULT_STATE_PATH = Path("logs/adaptive_rotation_state.json")
PAID_CHAINS = frozenset({"near_zero_high_quality", "paid_default"})


@dataclass
class RotationState:
    chain_name: str
    providers: list[str]
    active_index: int = 0
    last_switch_ts: float = 0.0
    switch_count: int = 0
    last_error: str = ""


@dataclass
class AdaptiveProviderRotator:
    """Rotate through zero-cost providers; skip exhausted entries via QuotaTracker."""

    state_path: Path = field(default_factory=lambda: DEFAULT_STATE_PATH)
    chain_name: str = field(
        default_factory=lambda: os.getenv("ADAPTIVE_ROTATION_CHAIN", "zero_cost_cloud")
    )
    _state: RotationState = field(init=False)
    _quota: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._quota = get_quota_tracker()
        self._state = self._load_state()
        if not self._state.providers:
            self._refresh_chain_from_registry()
        self._persist()

    def _load_state(self) -> RotationState:
        if not self.state_path.exists():
            return RotationState(chain_name=self.chain_name, providers=[])
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return RotationState(
                chain_name=str(raw.get("chain_name", self.chain_name)),
                providers=list(raw.get("providers", [])),
                active_index=int(raw.get("active_index", 0)),
                last_switch_ts=float(raw.get("last_switch_ts", 0.0)),
                switch_count=int(raw.get("switch_count", 0)),
                last_error=str(raw.get("last_error", "")),
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return RotationState(chain_name=self.chain_name, providers=[])

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chain_name": self._state.chain_name,
            "providers": self._state.providers,
            "active_index": self._state.active_index,
            "last_switch_ts": self._state.last_switch_ts,
            "switch_count": self._state.switch_count,
            "last_error": self._state.last_error,
            "updated_at": time.time(),
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _refresh_chain_from_registry(self) -> None:
        chain = get_chain(self._state.chain_name)
        assert_zero_cost(chain)
        available = self._quota.available_from_chain(chain)
        self._state.providers = available
        if self._state.active_index >= len(self._state.providers):
            self._state.active_index = 0

    def _available_providers(self) -> list[str]:
        if not self._state.providers:
            self._refresh_chain_from_registry()
        return [p for p in self._state.providers if self._quota.is_available(p)]

    def active_provider(self) -> str:
        available = self._available_providers()
        if not available:
            self._state.last_error = "zero_cost_chain_exhausted"
            self._persist()
            return "offline"
        idx = min(self._state.active_index, len(available) - 1)
        return available[idx]

    def record_success(self, provider_id: str | None = None) -> None:
        pid = provider_id or self.active_provider()
        if pid != "offline":
            self._quota.record_success(pid)

    def record_failure(self, provider_id: str, reason: str = "provider_error") -> str:
        self._quota.mark_exhausted(provider_id, reason=reason)
        self._state.last_error = reason
        self._refresh_chain_from_registry()
        return self.active_provider()

    def switch_chain(self, chain_name: str) -> bool:
        if chain_name in PAID_CHAINS:
            return False
        try:
            chain = get_chain(chain_name)
            assert_zero_cost(chain)
        except (ValueError, RuntimeError):
            return False
        self._state.chain_name = chain_name
        self._state.active_index = 0
        self._state.switch_count += 1
        self._state.last_switch_ts = time.time()
        self._refresh_chain_from_registry()
        self._persist()
        return True

    def status(self) -> dict[str, Any]:
        available = self._available_providers()
        return {
            "state": {
                "chain_name": self._state.chain_name,
                "providers": self._state.providers,
                "available_providers": available,
                "active_index": self._state.active_index,
                "active_provider": self.active_provider(),
                "switch_count": self._state.switch_count,
                "last_error": self._state.last_error,
            },
            "quota": self._quota.status(),
        }


_rotator: AdaptiveProviderRotator | None = None


def get_provider_rotator() -> AdaptiveProviderRotator:
    """Process-wide singleton (mirrors get_proactive_orchestrator)."""
    global _rotator
    if _rotator is None:
        _rotator = AdaptiveProviderRotator()
    return _rotator
