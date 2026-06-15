"""
Quota Enforcer — x8 Free Provider Hard-Stop Rotation
======================================================
Tracks per-provider request/token usage against free-tier limits.
Enforces hard stops at a configurable threshold (default 80%).
Auto-rotates to the next available provider when a threshold is hit.

Providers supported (all zero-cost):
  1. ollama        — local, unlimited
  2. groq          — 14,400 RPD / 500K TPD
  3. cerebras      — 1M TPD, 60 RPM
  4. sambanova     — 80 RPD
  5. openrouter    — free models, ~50 RPD per model
  6. gemini        — 1,500 RPD / 1M TPD
  7. huggingface   — ~1,000 RPD
  8. github_models — 50 RPD
  9. offline       — always available, deterministic stub
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tranc3.mesh.quota_enforcer")

# ── Free-tier limits ───────────────────────────────────────────────────────────

PROVIDER_LIMITS: dict[str, dict[str, float]] = {
    "ollama": {
        "daily_requests": float("inf"),
        "daily_tokens": float("inf"),
    },
    "groq": {
        "daily_requests": 14_400.0,
        "daily_tokens": 500_000.0,
        "rpm": 30.0,
    },
    "cerebras": {
        "daily_tokens": 1_000_000.0,
        "rpm": 60.0,
    },
    "sambanova": {
        "daily_requests": 80.0,
    },
    "openrouter": {
        "daily_requests": 200.0,  # Conservative; varies by model
    },
    "gemini": {
        "daily_requests": 1_500.0,
        "daily_tokens": 1_000_000.0,
        "rpm": 15.0,
    },
    "huggingface": {
        "daily_requests": 1_000.0,
    },
    "github_models": {
        "daily_requests": 50.0,
        "daily_tokens": 50_000.0,
    },
    "offline": {
        "daily_requests": float("inf"),
        "daily_tokens": float("inf"),
    },
}

# Ordered rotation chain (most capable/fastest first)
ROTATION_ORDER = [
    "ollama",
    "groq",
    "cerebras",
    "sambanova",
    "openrouter",
    "gemini",
    "huggingface",
    "github_models",
    "offline",
]


# ── DB helpers ─────────────────────────────────────────────────────────────────


def _init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_usage (
            provider      TEXT NOT NULL,
            metric        TEXT NOT NULL,
            value         REAL NOT NULL DEFAULT 0,
            window_start  TEXT NOT NULL,
            PRIMARY KEY (provider, metric)
        )
        """
    )
    conn.commit()
    return conn


# ── Core enforcer ──────────────────────────────────────────────────────────────


@dataclass
class ProviderQuota:
    provider: str
    metric: str
    current: float
    limit: float
    window_start: str

    @property
    def pct(self) -> float:
        if self.limit == float("inf") or self.limit == 0:
            return 0.0
        return round(self.current / self.limit * 100, 2)

    @property
    def available(self) -> bool:
        return self.pct < 100.0


@dataclass
class ProviderStatus:
    provider: str
    available: bool
    quotas: list[ProviderQuota] = field(default_factory=list)
    blocked_reason: str = ""


class QuotaEnforcer:
    """
    Tracks and enforces free-tier request/token quotas.

    Usage::

        enforcer = QuotaEnforcer()
        provider = enforcer.select_provider()         # best available
        enforcer.record_request(provider, tokens=256) # track usage
        if enforcer.is_blocked(provider):             # hard stop check
            provider = enforcer.next_provider(provider)
    """

    def __init__(
        self,
        db_path: str = "data/quota_enforcer.db",
        threshold_pct: float = 80.0,
    ) -> None:
        self._db = _init_db(Path(db_path))
        self.threshold_pct = threshold_pct
        self._lock = threading.Lock()

    # ── Usage tracking ─────────────────────────────────────────────────────

    def record_request(self, provider: str, tokens: float = 0.0) -> None:
        """Increment daily_requests (+1) and daily_tokens (+tokens) for provider."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._inc(provider, "daily_requests", 1.0, today)
        if tokens > 0:
            self._inc(provider, "daily_tokens", tokens, today)

    def _inc(self, provider: str, metric: str, delta: float, today: str) -> None:
        with self._lock:
            row = self._db.execute(
                "SELECT value, window_start FROM provider_usage WHERE provider=? AND metric=?",
                (provider, metric),
            ).fetchone()

            if row is None:
                self._db.execute(
                    "INSERT INTO provider_usage (provider, metric, value, window_start) VALUES (?,?,?,?)",
                    (provider, metric, delta, today),
                )
            else:
                current_value, window_start = row
                # Reset counter if new day
                if window_start != today:
                    current_value = 0.0
                self._db.execute(
                    "UPDATE provider_usage SET value=?, window_start=? WHERE provider=? AND metric=?",
                    (current_value + delta, today, provider, metric),
                )
            self._db.commit()

    def get_usage(self, provider: str) -> dict[str, ProviderQuota]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self._db.execute(
            "SELECT metric, value, window_start FROM provider_usage WHERE provider=?",
            (provider,),
        ).fetchall()
        recorded = {r[0]: (r[1], r[2]) for r in rows}

        quotas: dict[str, ProviderQuota] = {}
        for metric, limit in PROVIDER_LIMITS.get(provider, {}).items():
            value, ws = recorded.get(metric, (0.0, today))
            # Auto-reset if new day
            if ws != today:
                value = 0.0
            quotas[metric] = ProviderQuota(
                provider=provider,
                metric=metric,
                current=value,
                limit=limit,
                window_start=ws,
            )
        return quotas

    # ── Hard-stop logic ────────────────────────────────────────────────────

    def is_blocked(self, provider: str) -> bool:
        """Return True if provider has hit hard-stop threshold on any metric."""
        for q in self.get_usage(provider).values():
            if q.limit != float("inf") and q.pct >= self.threshold_pct:
                return True
        return False

    def get_status(self, provider: str) -> ProviderStatus:
        quotas = list(self.get_usage(provider).values())
        blocked = any(q.limit != float("inf") and q.pct >= self.threshold_pct for q in quotas)
        reason = ""
        if blocked:
            over = [q for q in quotas if q.limit != float("inf") and q.pct >= self.threshold_pct]
            reason = ", ".join(f"{q.metric}={q.pct:.0f}%" for q in over)
        return ProviderStatus(
            provider=provider,
            available=not blocked,
            quotas=quotas,
            blocked_reason=reason,
        )

    # ── Selection / rotation ───────────────────────────────────────────────

    def select_provider(
        self,
        preferred: Optional[str] = None,
        exclude: Optional[list[str]] = None,
    ) -> str:
        """Select best available provider; rotates automatically on threshold breach."""
        exclude = exclude or []
        if preferred and preferred not in exclude and not self.is_blocked(preferred):
            return preferred

        for provider in ROTATION_ORDER:
            if provider in exclude:
                continue
            if not self.is_blocked(provider):
                if preferred and provider != preferred:
                    logger.info(
                        "quota_enforcer: rotated %s → %s",
                        preferred,
                        provider,
                    )
                return provider

        logger.warning("quota_enforcer: all providers at threshold — using offline")
        return "offline"

    def next_provider(self, current: str) -> str:
        """Return the next provider after *current* in the rotation chain."""
        try:
            idx = ROTATION_ORDER.index(current)
        except ValueError:
            idx = -1
        remaining = ROTATION_ORDER[idx + 1 :] + ROTATION_ORDER[: idx + 1]
        for provider in remaining:
            if not self.is_blocked(provider):
                return provider
        return "offline"

    def all_statuses(self) -> list[ProviderStatus]:
        return [self.get_status(p) for p in ROTATION_ORDER]

    def dashboard(self) -> dict:
        statuses = self.all_statuses()
        return {
            "providers": [
                {
                    "provider": s.provider,
                    "available": s.available,
                    "blocked_reason": s.blocked_reason,
                    "quotas": {
                        q.metric: {"pct": q.pct, "current": q.current, "limit": q.limit}
                        for q in s.quotas
                    },
                }
                for s in statuses
            ],
            "threshold_pct": self.threshold_pct,
            "available_count": sum(1 for s in statuses if s.available),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_enforcer: Optional[QuotaEnforcer] = None


def get_enforcer() -> QuotaEnforcer:
    global _enforcer
    if _enforcer is None:
        _enforcer = QuotaEnforcer(
            threshold_pct=float(os.environ.get("QUOTA_THRESHOLD_PCT", "80")),
        )
    return _enforcer


__all__ = [
    "PROVIDER_LIMITS",
    "ROTATION_ORDER",
    "ProviderQuota",
    "ProviderStatus",
    "QuotaEnforcer",
    "get_enforcer",
]
