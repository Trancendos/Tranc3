"""Per-provider quota tracking with cooldown hard-stops for zero-cost rotation."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = Path("logs/zero_cost_quota_state.json")
DEFAULT_COOLDOWN_SECONDS = int(os.getenv("ZERO_COST_QUOTA_COOLDOWN_SECONDS", "3600"))
DEFAULT_DAILY_LIMIT = int(os.getenv("ZERO_COST_DAILY_REQUEST_LIMIT", "5000"))


@dataclass
class ProviderQuotaState:
    provider_id: str
    requests_today: int = 0
    last_request_ts: float = 0.0
    exhausted_until: float = 0.0
    last_error: str = ""

    def is_available(self, now: float | None = None) -> bool:
        ts = now if now is not None else time.time()
        return ts >= self.exhausted_until


@dataclass
class QuotaTracker:
    """Tracks usage and enforces cooldown when providers hit quota or hard errors."""

    state_path: Path = field(default_factory=lambda: DEFAULT_STATE_PATH)
    daily_limit: int = DEFAULT_DAILY_LIMIT
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
    providers: dict[str, ProviderQuotaState] = field(default_factory=dict)
    _day_key: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))

    def _ensure_provider(self, provider_id: str) -> ProviderQuotaState:
        if provider_id not in self.providers:
            self.providers[provider_id] = ProviderQuotaState(provider_id=provider_id)
        return self.providers[provider_id]

    def _roll_day_if_needed(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self._day_key:
            self._day_key = today
            for state in self.providers.values():
                state.requests_today = 0
                if state.exhausted_until <= time.time():
                    state.exhausted_until = 0.0

    def load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._day_key = raw.get("day_key", self._day_key)
        self.daily_limit = int(raw.get("daily_limit", self.daily_limit))
        self.cooldown_seconds = int(raw.get("cooldown_seconds", self.cooldown_seconds))
        self.providers = {}
        for item in raw.get("providers", []):
            pid = str(item.get("provider_id", ""))
            if not pid:
                continue
            self.providers[pid] = ProviderQuotaState(
                provider_id=pid,
                requests_today=int(item.get("requests_today", 0)),
                last_request_ts=float(item.get("last_request_ts", 0.0)),
                exhausted_until=float(item.get("exhausted_until", 0.0)),
                last_error=str(item.get("last_error", "")),
            )

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "day_key": self._day_key,
            "daily_limit": self.daily_limit,
            "cooldown_seconds": self.cooldown_seconds,
            "providers": [asdict(s) for s in self.providers.values()],
            "updated_at": time.time(),
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def is_available(self, provider_id: str) -> bool:
        self._roll_day_if_needed()
        state = self._ensure_provider(provider_id)
        return state.is_available()

    def record_success(self, provider_id: str) -> None:
        self._roll_day_if_needed()
        state = self._ensure_provider(provider_id)
        state.requests_today += 1
        state.last_request_ts = time.time()
        if state.requests_today >= self.daily_limit:
            self.mark_exhausted(provider_id, reason="daily_limit_reached")
        self.save()

    def mark_exhausted(self, provider_id: str, reason: str = "quota_exhausted") -> None:
        now = time.time()
        state = self._ensure_provider(provider_id)
        state.exhausted_until = now + self.cooldown_seconds
        state.last_error = reason
        self.save()

    def available_from_chain(self, chain: list[str]) -> list[str]:
        self._roll_day_if_needed()
        return [p for p in chain if self.is_available(p)]

    def status(self) -> dict[str, Any]:
        self._roll_day_if_needed()
        now = time.time()
        return {
            "day_key": self._day_key,
            "daily_limit": self.daily_limit,
            "cooldown_seconds": self.cooldown_seconds,
            "providers": {
                pid: {
                    **asdict(st),
                    "available": st.is_available(now),
                    "cooldown_remaining_s": max(0.0, st.exhausted_until - now),
                }
                for pid, st in self.providers.items()
            },
        }


_tracker: QuotaTracker | None = None


def get_quota_tracker() -> QuotaTracker:
    global _tracker
    if _tracker is None:
        _tracker = QuotaTracker()
        _tracker.load()
    return _tracker
