"""
Platform Registry — Zero-Cost Vendor Inventory
===============================================
Tracks all free-tier platforms, their quotas, health, and current usage.
Provides the knowledge base for the MAPE-K loop's Analysis and Plan phases.

Zero-cost platforms tracked:
  Hosting:   Fly.io (free), Render.com (free), Railway (free), Oracle ARM64
  AI/LLM:    Ollama (local), Groq (free), Gemini Flash (free), OpenRouter :free
  Database:  Supabase (free), PlanetScale (free), Neon (free), SQLite (local)
  Cache:     Upstash Redis (free), KeyDB (self-hosted)
  Storage:   IPFS (self-hosted), Backblaze B2 (free 10GB)
  CI/CD:     Forgejo (self-hosted) — primary; all GitHub Actions DECOMMISSIONED
  Edge:      No Cloudflare Workers — all replaced by self-hosted Python workers
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PlatformCategory(str, Enum):
    HOSTING = "hosting"
    AI_LLM = "ai_llm"
    DATABASE = "database"
    CACHE = "cache"
    STORAGE = "storage"
    CI_CD = "ci_cd"
    MONITORING = "monitoring"
    MESSAGING = "messaging"


class PlatformHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    EXHAUSTED = "exhausted"   # quota used up
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class QuotaLimits:
    """Free-tier quota limits for a platform."""
    requests_per_month: Optional[int] = None
    requests_per_minute: Optional[int] = None
    bandwidth_gb_month: Optional[float] = None
    storage_gb: Optional[float] = None
    compute_hours_month: Optional[float] = None
    tokens_per_minute: Optional[int] = None
    tokens_per_day: Optional[int] = None
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformUsage:
    """Current usage snapshot for a platform."""
    requests_this_month: int = 0
    requests_this_minute: int = 0
    bandwidth_gb_used: float = 0.0
    storage_gb_used: float = 0.0
    compute_hours_used: float = 0.0
    tokens_used_today: int = 0
    tokens_used_this_minute: int = 0
    last_updated: float = field(default_factory=time.monotonic)
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Platform:
    """A zero-cost vendor/platform entry."""
    name: str
    category: PlatformCategory
    priority: int                          # lower = preferred
    health: PlatformHealth = PlatformHealth.UNKNOWN
    quota: QuotaLimits = field(default_factory=QuotaLimits)
    usage: PlatformUsage = field(default_factory=PlatformUsage)
    endpoint_env: Optional[str] = None    # env var holding the URL
    enabled: bool = True
    notes: str = ""

    def utilisation_pct(self) -> float:
        """Estimate quota utilisation 0.0–1.0."""
        ratios: List[float] = []
        if self.quota.requests_per_month and self.usage.requests_this_month:
            ratios.append(self.usage.requests_this_month / self.quota.requests_per_month)
        if self.quota.tokens_per_day and self.usage.tokens_used_today:
            ratios.append(self.usage.tokens_used_today / self.quota.tokens_per_day)
        if self.quota.bandwidth_gb_month and self.usage.bandwidth_gb_used:
            ratios.append(self.usage.bandwidth_gb_used / self.quota.bandwidth_gb_month)
        return max(ratios) if ratios else 0.0

    def is_available(self) -> bool:
        return (
            self.enabled
            and self.health not in (PlatformHealth.EXHAUSTED, PlatformHealth.OFFLINE)
            and self.utilisation_pct() < 0.9
        )


class PlatformRegistry:
    """
    Central inventory of all zero-cost platforms.

    Usage:
        registry = PlatformRegistry()
        best = registry.best_for(PlatformCategory.AI_LLM)
        registry.mark_exhausted("groq")
    """

    def __init__(self) -> None:
        self._platforms: Dict[str, Platform] = {}
        self._build_default_registry()

    def _build_default_registry(self) -> None:
        entries: List[Platform] = [
            # ---- AI / LLM ----
            Platform(
                name="ollama",
                category=PlatformCategory.AI_LLM,
                priority=1,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(),          # unlimited — runs locally
                endpoint_env="OLLAMA_URL",
                notes="Local — zero cost, zero latency, zero quota",
            ),
            Platform(
                name="groq",
                category=PlatformCategory.AI_LLM,
                priority=2,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(tokens_per_minute=14_400, tokens_per_day=500_000),
                endpoint_env="GROQ_API_KEY",
                notes="Free tier: 14.4k TPM / 500k TPD",
            ),
            Platform(
                name="gemini_flash",
                category=PlatformCategory.AI_LLM,
                priority=3,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(tokens_per_minute=32_000, requests_per_minute=15),
                endpoint_env="GEMINI_API_KEY",
                notes="Gemini 2.0 Flash free tier",
            ),
            Platform(
                name="openrouter_free",
                category=PlatformCategory.AI_LLM,
                priority=4,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(requests_per_minute=20),
                endpoint_env="OPENROUTER_API_KEY",
                notes=":free model suffix — zero cost",
            ),
            Platform(
                name="huggingface_inference",
                category=PlatformCategory.AI_LLM,
                priority=5,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(requests_per_month=30_000),
                endpoint_env="HF_API_TOKEN",
                notes="Serverless Inference free tier",
            ),
            # ---- Hosting ----
            Platform(
                name="fly_io",
                category=PlatformCategory.HOSTING,
                priority=1,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(compute_hours_month=160.0, bandwidth_gb_month=100.0),
                endpoint_env="FLY_API_TOKEN",
                notes="Fly.io free allowance; tranc3-backend + tranc3-bots",
            ),
            Platform(
                name="render",
                category=PlatformCategory.HOSTING,
                priority=2,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(compute_hours_month=750.0),
                endpoint_env="RENDER_API_KEY",
                notes="Render.com free tier — 750hr/month",
            ),
            Platform(
                name="railway_free",
                category=PlatformCategory.HOSTING,
                priority=3,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(custom={"credits_usd": 5.0}),
                endpoint_env="RAILWAY_TOKEN",
                notes="Railway $5 free credit/month",
            ),
            Platform(
                name="oracle_arm",
                category=PlatformCategory.HOSTING,
                priority=4,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(),   # truly always-free
                endpoint_env="OCI_CLI_KEY_FILE",
                notes="Oracle Always Free — 4 OCPU / 24 GB ARM64, unlimited",
            ),
            # ---- Database ----
            Platform(
                name="supabase",
                category=PlatformCategory.DATABASE,
                priority=1,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(storage_gb=0.5, bandwidth_gb_month=5.0),
                endpoint_env="DATABASE_URL",
                notes="Supabase free tier — 500MB DB, 5GB bandwidth",
            ),
            Platform(
                name="neon",
                category=PlatformCategory.DATABASE,
                priority=2,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(storage_gb=0.5),
                endpoint_env="NEON_DATABASE_URL",
                notes="Neon serverless Postgres free tier",
            ),
            Platform(
                name="sqlite_local",
                category=PlatformCategory.DATABASE,
                priority=3,
                health=PlatformHealth.HEALTHY,  # always available
                quota=QuotaLimits(),
                notes="Local SQLite — zero cost, zero quota",
            ),
            # ---- Cache ----
            Platform(
                name="upstash_redis",
                category=PlatformCategory.CACHE,
                priority=1,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(requests_per_month=500_000),
                endpoint_env="REDIS_URL",
                notes="Upstash free tier — 500k commands/month",
            ),
            # ---- CI/CD ----
            Platform(
                name="forgejo",
                category=PlatformCategory.CI_CD,
                priority=1,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(),   # self-hosted, unlimited
                endpoint_env="FORGEJO_URL",
                notes="Self-hosted Forgejo at trancendos.com/the-workshop — primary CI",
            ),
            # ---- Monitoring ----
            Platform(
                name="signoz",
                category=PlatformCategory.MONITORING,
                priority=1,
                health=PlatformHealth.UNKNOWN,
                quota=QuotaLimits(),   # self-hosted
                endpoint_env="SIGNOZ_URL",
                notes="Self-hosted SigNoz OpenTelemetry APM",
            ),
        ]
        for p in entries:
            self._platforms[p.name] = p

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[Platform]:
        return self._platforms.get(name)

    def all_for(self, category: PlatformCategory) -> List[Platform]:
        return sorted(
            [p for p in self._platforms.values() if p.category == category],
            key=lambda p: p.priority,
        )

    def best_for(self, category: PlatformCategory) -> Optional[Platform]:
        for p in self.all_for(category):
            if p.is_available():
                return p
        return None

    def snapshot(self) -> Dict[str, Any]:
        return {
            name: {
                "category": p.category.value,
                "health": p.health.value,
                "priority": p.priority,
                "utilisation_pct": round(p.utilisation_pct() * 100, 1),
                "available": p.is_available(),
            }
            for name, p in self._platforms.items()
        }

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def mark_exhausted(self, name: str) -> None:
        p = self._platforms.get(name)
        if p:
            p.health = PlatformHealth.EXHAUSTED
            logger.warning("Platform %s marked EXHAUSTED — will rotate to fallback", name)

    def mark_healthy(self, name: str) -> None:
        p = self._platforms.get(name)
        if p:
            p.health = PlatformHealth.HEALTHY

    def mark_offline(self, name: str) -> None:
        p = self._platforms.get(name)
        if p:
            p.health = PlatformHealth.OFFLINE
            logger.warning("Platform %s marked OFFLINE", name)

    def record_requests(self, name: str, count: int = 1) -> None:
        p = self._platforms.get(name)
        if p:
            p.usage.requests_this_month += count
            p.usage.requests_this_minute += count
            p.usage.last_updated = time.monotonic()

    def record_tokens(self, name: str, tokens: int) -> None:
        p = self._platforms.get(name)
        if p:
            p.usage.tokens_used_today += tokens
            p.usage.tokens_used_this_minute += tokens
            p.usage.last_updated = time.monotonic()
