"""
NanoCode Bots — autonomous repair agents for the Tranc3 service mesh.

Each NanoBot targets a single FailureMode and carries out a concrete
remediation procedure (HTTP calls, Redis ops, vector-DB upserts, …).
The NanoCodeBotDispatcher selects and runs the right bot given either
an explicit failure mode or raw metrics from which it infers modes
automatically.
"""

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Dict, List

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared HTTP client (lazy singleton — avoids per-call connection overhead)
# ---------------------------------------------------------------------------

_shared_clients: Dict[float, httpx.AsyncClient] = {}


def _get_client(timeout: float = 15.0) -> httpx.AsyncClient:
    client = _shared_clients.get(timeout)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=timeout)
        _shared_clients[timeout] = client
    return client


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FailureMode(Enum):
    COMPLIANCE_METADATA_MISSING = "compliance_metadata_missing"
    STALE_EMBEDDING = "stale_embedding"
    FREE_TIER_APPROACHING = "free_tier_approaching"
    RATE_LIMIT_HIT = "rate_limit_hit"
    SERVICE_UNREACHABLE = "service_unreachable"
    CONFIG_DRIFT = "config_drift"
    MEMORY_LEAK = "memory_leak"
    HIGH_ERROR_RATE = "high_error_rate"
    DEPENDENCY_FAILED = "dependency_failed"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class BotResult:
    bot_id: str
    failure_mode: FailureMode
    service_id: str
    success: bool
    action_taken: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Abstract NanoBot
# ---------------------------------------------------------------------------


class NanoBot(ABC):
    failure_mode: ClassVar[FailureMode]

    def __init__(self) -> None:
        self.success_rate: float = 0.9
        self._invocation_count: int = 0

    @abstractmethod
    async def repair(self, service_id: str, context: Dict) -> BotResult:
        """Execute the repair procedure and return a BotResult."""

    def _update_success_rate(self, succeeded: bool) -> None:
        """Exponential moving average of success rate (α = 0.1)."""
        self._invocation_count += 1
        self.success_rate = 0.9 * self.success_rate + 0.1 * (1.0 if succeeded else 0.0)

    @property
    def bot_id(self) -> str:
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# Concrete bots
# ---------------------------------------------------------------------------


class ComplianceMetadataBot(NanoBot):
    """
    Injects required GDPR / compliance metadata fields into a service's
    configuration via its /config/compliance endpoint.

    Required fields injected:
      - data_controller, data_processor, lawful_basis, retention_days,
        dpia_required, consent_mechanism, breach_notification_hrs
    """

    failure_mode: ClassVar[FailureMode] = FailureMode.COMPLIANCE_METADATA_MISSING

    _REQUIRED_FIELDS = {
        "data_controller": "Tranc3-AI-Platform",
        "data_processor": "Tranc3-Service-Mesh",
        "lawful_basis": "legitimate_interest",
        "retention_days": 90,
        "dpia_required": True,
        "consent_mechanism": "opt-in",
        "breach_notification_hrs": 72,
    }

    async def repair(self, service_id: str, context: Dict) -> BotResult:
        t0 = time.perf_counter()
        endpoint = context.get("endpoint", "")
        success = False
        action = ""

        try:
            client = _get_client(timeout=15.0)
            # Step 1: fetch existing config
            resp = await client.get(f"{endpoint}/config/compliance")
            existing: Dict = {}
            if resp.status_code == 200:
                existing = resp.json()

            # Merge: only inject missing fields
            payload = {**self._REQUIRED_FIELDS, **existing}
            # Always ensure required keys present
            for k, v in self._REQUIRED_FIELDS.items():
                payload.setdefault(k, v)

            # Step 2: push updated config
            patch_resp = await client.post(
                f"{endpoint}/config/compliance",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            patch_resp.raise_for_status()

            # Step 3: validate with re-check
            verify_resp = await client.get(f"{endpoint}/config/compliance/validate")
            if verify_resp.status_code == 200:
                data = verify_resp.json()
                success = data.get("valid", False)
                action = (
                    f"Injected {len(self._REQUIRED_FIELDS)} GDPR fields; "
                    f"validation={'pass' if success else 'fail'}"
                )
            else:
                # Treat successful POST as partial success
                success = patch_resp.status_code < 300
                action = "Injected compliance metadata; validation endpoint unavailable"

        except httpx.HTTPStatusError as exc:
            action = (
                f"HTTP error during compliance injection: {exc.response.status_code}"
            )
            logger.error("[ComplianceMetadataBot] %s — %s", service_id, action)
        except Exception as exc:
            action = f"Repair failed: {exc}"
            logger.error("[ComplianceMetadataBot] %s — %s", service_id, exc)

        self._update_success_rate(success)
        return BotResult(
            bot_id=self.bot_id,
            failure_mode=self.failure_mode,
            service_id=service_id,
            success=success,
            action_taken=action,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )


class StaleEmbeddingBot(NanoBot):
    """
    Re-embeds stale content by:
      1. Fetching content items from the service's /content/stale endpoint.
      2. Calling the local embedding service to compute fresh vectors.
      3. Upserting results into Qdrant.
    """

    failure_mode: ClassVar[FailureMode] = FailureMode.STALE_EMBEDDING

    def __init__(self) -> None:
        super().__init__()
        self._qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self._embed_url = os.getenv("EMBED_URL", "http://localhost:8001/embed")

    async def repair(self, service_id: str, context: Dict) -> BotResult:
        t0 = time.perf_counter()
        endpoint = context.get("endpoint", "")
        success = False
        upserted = 0
        action = ""

        try:
            client = _get_client(timeout=60.0)
            # Step 1: get stale content list
            stale_resp = await client.get(
                f"{endpoint}/content/stale",
                params={"limit": 50},
            )
            stale_resp.raise_for_status()
            stale_items: List[Dict] = stale_resp.json().get("items", [])

            if not stale_items:
                return BotResult(
                    bot_id=self.bot_id,
                    failure_mode=self.failure_mode,
                    service_id=service_id,
                    success=True,
                    action_taken="No stale embeddings found — nothing to do",
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )

            # Step 2: embed in batches of 16
            batch_size = 16
            qdrant_points = []
            for i in range(0, len(stale_items), batch_size):
                batch = stale_items[i : i + batch_size]
                texts = [item.get("text", "") for item in batch]
                embed_resp = await client.post(
                    self._embed_url,
                    json={"texts": texts},
                    headers={"Content-Type": "application/json"},
                )
                embed_resp.raise_for_status()
                vectors = embed_resp.json().get("embeddings", [])

                for item, vec in zip(batch, vectors, strict=False):
                    qdrant_points.append(
                        {
                            "id": item.get("id"),
                            "vector": vec,
                            "payload": {
                                "service_id": service_id,
                                "content_id": item.get("id"),
                                "updated_at": time.time(),
                            },
                        }
                    )

            # Step 3: upsert to Qdrant
            collection = context.get("qdrant_collection", f"tranc3_{service_id}")
            upsert_resp = await client.put(
                f"{self._qdrant_url}/collections/{collection}/points",
                json={"points": qdrant_points},
                headers={"Content-Type": "application/json"},
            )
            upsert_resp.raise_for_status()
            upserted = len(qdrant_points)
            success = True
            action = (
                f"Re-embedded and upserted {upserted} stale items "
                f"into Qdrant collection '{collection}'"
            )

        except Exception as exc:
            action = f"StaleEmbeddingBot repair failed: {exc}"
            logger.error("[StaleEmbeddingBot] %s — %s", service_id, exc)

        self._update_success_rate(success)
        return BotResult(
            bot_id=self.bot_id,
            failure_mode=self.failure_mode,
            service_id=service_id,
            success=success,
            action_taken=action,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )


class FreeTierBot(NanoBot):
    """
    Enables conservation mode when a service's free-tier quota approaches
    the limit:
      - Reduces outbound request rate via /config/rate_limit.
      - Enables response caching via /config/cache.
      - Pre-warms the next tier by calling /tier/upgrade/prepare.
    """

    failure_mode: ClassVar[FailureMode] = FailureMode.FREE_TIER_APPROACHING

    _CONSERVATION_RATE_LIMIT_RPS = 2  # requests per second in conservation mode
    _CACHE_TTL_SEC = 3600  # 1-hour cache TTL when conserving

    async def repair(self, service_id: str, context: Dict) -> BotResult:
        t0 = time.perf_counter()
        endpoint = context.get("endpoint", "")
        actions_taken: List[str] = []
        success = False

        try:
            client = _get_client(timeout=15.0)
            # 1. Reduce request rate
            rate_resp = await client.post(
                f"{endpoint}/config/rate_limit",
                json={
                    "mode": "conservation",
                    "rps": self._CONSERVATION_RATE_LIMIT_RPS,
                    "burst": self._CONSERVATION_RATE_LIMIT_RPS * 2,
                },
            )
            if rate_resp.status_code < 300:
                actions_taken.append(
                    f"Rate limited to {self._CONSERVATION_RATE_LIMIT_RPS} RPS"
                )

            # 2. Enable caching
            cache_resp = await client.post(
                f"{endpoint}/config/cache",
                json={
                    "enabled": True,
                    "ttl_sec": self._CACHE_TTL_SEC,
                    "strategy": "lru",
                    "max_size_mb": 256,
                },
            )
            if cache_resp.status_code < 300:
                actions_taken.append(f"Enabled LRU cache (TTL={self._CACHE_TTL_SEC}s)")

            # 3. Pre-warm next tier
            try:
                tier_resp = await client.post(
                    f"{endpoint}/tier/upgrade/prepare",
                    json={"reason": "free_tier_conservation", "notify": True},
                )
                if tier_resp.status_code < 300:
                    actions_taken.append("Next-tier upgrade preparation triggered")
            except Exception:
                # Non-critical — not every service has tier management
                pass  # nosec B110 — graceful degradation for optional tier feature

            success = len(actions_taken) >= 1

        except Exception as exc:
            actions_taken.append(f"Error: {exc}")
            logger.error("[FreeTierBot] %s — %s", service_id, exc)

        self._update_success_rate(success)
        return BotResult(
            bot_id=self.bot_id,
            failure_mode=self.failure_mode,
            service_id=service_id,
            success=success,
            action_taken="; ".join(actions_taken) if actions_taken else "No actions",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )


class RateLimitBot(NanoBot):
    """
    Handles RATE_LIMIT_HIT by:
      1. Rotating to a backup API token from the environment pool.
      2. Enabling Redis-backed request queuing to smooth traffic spikes.
    """

    failure_mode: ClassVar[FailureMode] = FailureMode.RATE_LIMIT_HIT

    def __init__(self) -> None:
        super().__init__()
        self._redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        # Pool of backup tokens: TOKEN_POOL_0, TOKEN_POOL_1, …
        self._token_pool = self._load_token_pool()
        self._current_token_idx: Dict[str, int] = {}

    @staticmethod
    def _load_token_pool() -> List[str]:
        tokens = []
        i = 0
        while True:
            tok = os.getenv(f"TOKEN_POOL_{i}")
            if tok is None:
                break
            tokens.append(tok)
            i += 1
        if not tokens:
            # Fallback: look for a single backup token
            fallback = os.getenv("BACKUP_API_TOKEN")
            if fallback:
                tokens.append(fallback)
        return tokens

    async def repair(self, service_id: str, context: Dict) -> BotResult:
        t0 = time.perf_counter()
        endpoint = context.get("endpoint", "")
        actions: List[str] = []
        success = False

        try:
            client = _get_client(timeout=15.0)
            # 1. Rotate API token
            if self._token_pool:
                idx = self._current_token_idx.get(service_id, 0)
                next_idx = (idx + 1) % len(self._token_pool)
                self._current_token_idx[service_id] = next_idx
                new_token = self._token_pool[next_idx]

                token_resp = await client.post(
                    f"{endpoint}/config/token",
                    json={"token": new_token, "reason": "rate_limit_rotation"},
                )
                if token_resp.status_code < 300:
                    actions.append(f"Rotated to token pool index {next_idx}")
                    success = True
            else:
                actions.append("No backup tokens in pool")

            # 2. Enable Redis-backed request queue
            queue_resp = await client.post(
                f"{endpoint}/config/queue",
                json={
                    "enabled": True,
                    "backend": "redis",
                    "redis_url": self._redis_url,
                    "queue_key": f"tranc3:ratelimit:{service_id}",
                    "max_depth": 500,
                    "drain_rps": 5,
                },
            )
            if queue_resp.status_code < 300:
                actions.append("Enabled Redis request queuing")
                success = True

        except Exception as exc:
            actions.append(f"Error: {exc}")
            logger.error("[RateLimitBot] %s — %s", service_id, exc)

        self._update_success_rate(success)
        return BotResult(
            bot_id=self.bot_id,
            failure_mode=self.failure_mode,
            service_id=service_id,
            success=success,
            action_taken="; ".join(actions) if actions else "No actions",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )


class ServiceUnreachableBot(NanoBot):
    """
    Attempts to recover an unreachable service via three strategies in order:
      1. Restart ping — POST /admin/restart and wait for health to recover.
      2. Failover to replica — POST /admin/failover to switch traffic.
      3. Activate circuit breaker — POST /admin/circuit_breaker/open.
    """

    failure_mode: ClassVar[FailureMode] = FailureMode.SERVICE_UNREACHABLE

    _HEALTH_POLL_INTERVAL = 3.0  # seconds between restart health polls
    _HEALTH_POLL_RETRIES = 5  # max polls after restart

    async def repair(self, service_id: str, context: Dict) -> BotResult:
        t0 = time.perf_counter()
        endpoint = context.get("endpoint", "")
        health_endpoint = context.get("health_endpoint", f"{endpoint}/health")
        actions: List[str] = []
        success = False

        client = _get_client(timeout=20.0)
        # Strategy 1: restart ping
        try:
            restart_resp = await client.post(
                f"{endpoint}/admin/restart",
                json={"reason": "service_unreachable_auto_repair"},
            )
            if restart_resp.status_code < 300:
                actions.append("Restart signal sent")
                # Poll health until recovery or timeout
                for _ in range(self._HEALTH_POLL_RETRIES):
                    await asyncio.sleep(self._HEALTH_POLL_INTERVAL)
                    try:
                        hresp = await client.get(health_endpoint)
                        if hresp.status_code == 200:
                            actions.append("Service recovered after restart")
                            success = True
                            break
                    except Exception:
                        pass  # nosec B110 — graceful degradation; error logged upstream

        except Exception as exc:
            actions.append(f"Restart failed: {exc}")
            logger.warning("[ServiceUnreachableBot] Restart attempt failed: %s", exc)

        if success:
            self._update_success_rate(True)
            return BotResult(
                bot_id=self.bot_id,
                failure_mode=self.failure_mode,
                service_id=service_id,
                success=True,
                action_taken="; ".join(actions),
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Strategy 2: failover to replica
        try:
            replica_url = context.get("replica_endpoint", f"{endpoint}-replica")
            failover_resp = await client.post(
                f"{endpoint}/admin/failover",
                json={
                    "target": replica_url,
                    "mode": "active-passive",
                    "reason": "primary_unreachable",
                },
            )
            if failover_resp.status_code < 300:
                actions.append(f"Failover to replica {replica_url}")
                success = True
        except Exception as exc:
            actions.append(f"Failover failed: {exc}")
            logger.warning("[ServiceUnreachableBot] Failover failed: %s", exc)

        if success:
            self._update_success_rate(True)
            return BotResult(
                bot_id=self.bot_id,
                failure_mode=self.failure_mode,
                service_id=service_id,
                success=True,
                action_taken="; ".join(actions),
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Strategy 3: circuit breaker
        try:
            cb_resp = await client.post(
                f"{endpoint}/admin/circuit_breaker/open",
                json={
                    "duration_sec": 300,
                    "reason": "auto_repair_all_strategies_failed",
                },
            )
            if cb_resp.status_code < 300:
                actions.append("Circuit breaker activated (300 s)")
                # Partial success: at least we stopped the bleeding
                success = True
        except Exception as exc:
            actions.append(f"Circuit breaker failed: {exc}")
            logger.error("[ServiceUnreachableBot] All strategies failed: %s", exc)

        self._update_success_rate(success)
        return BotResult(
            bot_id=self.bot_id,
            failure_mode=self.failure_mode,
            service_id=service_id,
            success=success,
            action_taken="; ".join(actions) if actions else "All strategies exhausted",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class NanoCodeBotDispatcher:
    """
    Routes incoming failure events to the appropriate NanoBot and records
    execution history for observability.
    """

    def __init__(self) -> None:
        self._bots: Dict[FailureMode, NanoBot] = {}
        self._history: List[BotResult] = []

        # Register all built-in bots
        for bot_cls in [
            ComplianceMetadataBot,
            StaleEmbeddingBot,
            FreeTierBot,
            RateLimitBot,
            ServiceUnreachableBot,
        ]:
            instance = bot_cls()
            self._bots[instance.failure_mode] = instance

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        failure_mode: FailureMode,
        service_id: str,
        context: Dict = None,
    ) -> BotResult:
        """Find the right bot for *failure_mode* and execute its repair."""
        if context is None:
            context = {}
        bot = self._bots.get(failure_mode)
        if bot is None:
            logger.warning("No bot registered for failure mode %s", failure_mode.value)
            return BotResult(
                bot_id="dispatcher",
                failure_mode=failure_mode,
                service_id=service_id,
                success=False,
                action_taken=f"No bot registered for {failure_mode.value}",
                duration_ms=0.0,
            )

        logger.info(
            "Dispatching %s to %s for service %s",
            failure_mode.value,
            bot.bot_id,
            service_id,
        )
        result = await bot.repair(service_id, context)
        self._history.append(result)
        # Keep bounded history
        if len(self._history) > 10_000:
            self._history = self._history[-5_000:]
        return result

    async def auto_dispatch(self, service_id: str, metrics: Dict) -> List[BotResult]:
        """
        Infer failure modes from *metrics* and dispatch the appropriate bots.
        Returns a list of BotResults, one per detected failure mode.
        """
        modes = self._infer_failure_modes(metrics)
        if not modes:
            return []

        context = {
            "endpoint": metrics.get("endpoint", ""),
            "health_endpoint": metrics.get("health_endpoint", ""),
        }
        results = []
        for mode in modes:
            result = await self.dispatch(mode, service_id, context)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_bot_stats(self) -> Dict:
        stats = {}
        for mode, bot in self._bots.items():
            invocations = [r for r in self._history if r.failure_mode == mode]
            stats[mode.value] = {
                "bot_id": bot.bot_id,
                "success_rate_ema": round(bot.success_rate, 4),
                "total_invocations": bot._invocation_count,
                "recent_successes": sum(1 for r in invocations[-100:] if r.success),
                "recent_failures": sum(1 for r in invocations[-100:] if not r.success),
            }
        return stats

    # ------------------------------------------------------------------
    # Failure mode inference
    # ------------------------------------------------------------------

    def _infer_failure_modes(self, metrics: Dict) -> List[FailureMode]:
        """
        Rule-based failure mode detection from a metrics dict.

        Expected keys (all optional):
          compliance_score, free_tier_usage, error_rate, memory_percent,
          embedding_age_hours, response_time_ms, endpoint
        """
        modes: List[FailureMode] = []

        compliance = metrics.get("compliance_score", 1.0)
        if compliance < 0.5:
            modes.append(FailureMode.COMPLIANCE_METADATA_MISSING)

        embedding_age = metrics.get("embedding_age_hours", 0.0)
        if embedding_age > 24.0:
            modes.append(FailureMode.STALE_EMBEDDING)

        free_tier = metrics.get("free_tier_usage", 0.0)
        if 0.80 <= free_tier < 1.0:
            modes.append(FailureMode.FREE_TIER_APPROACHING)

        error_rate = metrics.get("error_rate", 0.0)
        if error_rate > 0.3:
            modes.append(FailureMode.RATE_LIMIT_HIT)
        if error_rate > 0.5:
            modes.append(FailureMode.HIGH_ERROR_RATE)

        if metrics.get("unreachable", False):
            modes.append(FailureMode.SERVICE_UNREACHABLE)

        memory = metrics.get("memory_percent", 0.0)
        if memory > 90.0:
            modes.append(FailureMode.MEMORY_LEAK)

        return modes


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

dispatcher = NanoCodeBotDispatcher()
