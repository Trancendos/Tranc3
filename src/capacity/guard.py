"""
CapacityGuard — platform-wide capacity tracking with hard stops.

Every external service that has a usage quota is registered here.
The guard tracks usage against limits and enforces thresholds:

  80%  → WARNING  — Observatory event, log
  90%  → ALERT    — Observatory event (severity=WARNING), Cryptex notified
  95%  → CRITICAL — Observatory event (severity=CRITICAL), Cryptex notified, metric labelled
  100% → HARD STOP — raises CapacityExceededError, blocks all further calls

Usage:
    from src.capacity.guard import get_capacity_guard, CapacityService

    guard = get_capacity_guard()
    guard.consume(CapacityService.GROQ_REQUESTS, amount=1)  # raises if over limit
    guard.status()  # returns dict of all services and their utilisation
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger("tranc3.capacity")


# ── Capacity service identifiers ──────────────────────────────────────────────


class CapacityService(str, Enum):
    # AI providers — daily request limits
    GROQ_REQUESTS = "groq.requests.daily"  # 14,400/day free tier
    GEMINI_REQUESTS = "gemini.requests.daily"  # 1,500/day free tier
    CEREBRAS_TOKENS = "cerebras.tokens.daily"  # 1,000,000 tokens/day free tier
    SAMBANOVA_REQUESTS = "sambanova.requests.daily"  # free tier (conservative 500/day)
    OPENROUTER_REQUESTS = "openrouter.requests.minute"  # 20/min free tier
    HUGGINGFACE_REQUESTS = "huggingface.requests.daily"  # free tier (conservative 300/day)
    GITHUB_MODELS_REQUESTS = "github_models.requests.daily"  # 150/day (GitHub PAT free)

    # AI gateway — token budgets
    AI_TOKENS_DAILY = "ai.tokens.daily"  # configurable per tenant

    # Storage
    STORAGE_BYTES = "storage.bytes.total"  # configurable per deployment
    FILES_UPLOADS_DAILY = "files.uploads.daily"  # configurable

    # Queue
    QUEUE_DEPTH = "queue.depth"  # in-flight messages

    # Platform-level request budget (free-tier deployments)
    PLATFORM_REQUESTS_HOURLY = "platform.requests.hourly"
    PLATFORM_REQUESTS_DAILY = "platform.requests.daily"


# ── Threshold constants ───────────────────────────────────────────────────────

THRESHOLD_WARN = 0.80  # 80%  — WARNING log + Observatory
THRESHOLD_ALERT = 0.90  # 90%  — WARNING Observatory + Cryptex notified
THRESHOLD_CRITICAL = 0.95  # 95%  — CRITICAL Observatory + Cryptex notified
THRESHOLD_HARD = 1.00  # 100% — CapacityExceededError raised


class CapacityExceededError(Exception):
    """Raised when a service has hit its 100% hard stop."""

    def __init__(self, service: CapacityService, used: int, limit: int) -> None:
        self.service = service
        self.used = used
        self.limit = limit
        pct = round(used / limit * 100, 1) if limit else 0
        super().__init__(
            f"[{service.value}] capacity hard stop: {used}/{limit} ({pct}%) — "
            f"all further calls are blocked until the window resets."
        )


# ── Service limit registry ────────────────────────────────────────────────────


@dataclass
class ServiceLimit:
    service: CapacityService
    limit: int  # hard limit (provider-documented or configured)
    window_seconds: int  # rolling window for the counter
    description: str  # human-readable label
    # Runtime state (not part of config)
    _used: int = field(default=0, repr=False, compare=False)
    _window_start: float = field(default_factory=time.time, repr=False, compare=False)
    _last_threshold: float = field(default=0.0, repr=False, compare=False)

    def utilisation(self) -> float:
        """Current usage as a fraction of the limit (0.0 – 1.0+)."""
        return self._used / self.limit if self.limit > 0 else 0.0

    def reset_if_window_expired(self) -> None:
        now = time.time()
        if now - self._window_start >= self.window_seconds:
            self._used = 0
            self._window_start = now
            self._last_threshold = 0.0


# Default limits — all free-tier documented values
_DEFAULT_LIMITS: list[ServiceLimit] = [
    ServiceLimit(CapacityService.GROQ_REQUESTS, 14_400, 86_400, "Groq free tier — 14,400 req/day"),
    ServiceLimit(
        CapacityService.GEMINI_REQUESTS, 1_500, 86_400, "Gemini free tier — 1,500 req/day"
    ),
    ServiceLimit(
        CapacityService.CEREBRAS_TOKENS, 1_000_000, 86_400, "Cerebras free tier — 1M tokens/day"
    ),
    ServiceLimit(
        CapacityService.SAMBANOVA_REQUESTS,
        500,
        86_400,
        "SambaNova free tier — conservative 500 req/day",
    ),
    ServiceLimit(CapacityService.OPENROUTER_REQUESTS, 20, 60, "OpenRouter free tier — 20 req/min"),
    ServiceLimit(
        CapacityService.HUGGINGFACE_REQUESTS, 300, 86_400, "HuggingFace free tier — 300 req/day"
    ),
    ServiceLimit(
        CapacityService.GITHUB_MODELS_REQUESTS,
        150,
        86_400,
        "GitHub Models — 150 req/day (PAT free)",
    ),
    ServiceLimit(
        CapacityService.AI_TOKENS_DAILY, 100_000, 86_400, "AI gateway default tenant token budget"
    ),
    ServiceLimit(
        CapacityService.STORAGE_BYTES, 10_737_418_240, 86_400 * 365, "Storage — 10 GB default"
    ),  # 10 GB
    ServiceLimit(
        CapacityService.FILES_UPLOADS_DAILY, 1_000, 86_400, "File uploads — 1,000/day default"
    ),
    ServiceLimit(CapacityService.QUEUE_DEPTH, 10_000, 60, "Queue depth — 10k messages in-flight"),
    ServiceLimit(
        CapacityService.PLATFORM_REQUESTS_HOURLY,
        10_000,
        3_600,
        "Platform requests — 10k/hour default",
    ),
    ServiceLimit(
        CapacityService.PLATFORM_REQUESTS_DAILY,
        100_000,
        86_400,
        "Platform requests — 100k/day default",
    ),
]


# ── CapacityGuard ─────────────────────────────────────────────────────────────


class CapacityGuard:
    """
    Central capacity guard for all external services.
    Thread-safe. All threshold crossings emit Observatory events.
    """

    def __init__(self, limits: Optional[list[ServiceLimit]] = None) -> None:
        self._limits: Dict[CapacityService, ServiceLimit] = {
            sl.service: sl for sl in (limits or _DEFAULT_LIMITS)
        }
        self._lock = threading.Lock()
        self._observatory = None

    def _obs(self):
        if self._observatory is None:
            try:
                from src.observability.observatory import get_observatory

                self._observatory = get_observatory()
            except Exception:
                pass
        return self._observatory

    def configure(self, service: CapacityService, limit: int, window_seconds: int) -> None:
        """Override a service's limit at runtime (e.g. from env/config)."""
        with self._lock:
            if service in self._limits:
                self._limits[service].limit = limit
                self._limits[service].window_seconds = window_seconds
            else:
                self._limits[service] = ServiceLimit(service, limit, window_seconds, service.value)

    def consume(self, service: CapacityService, amount: int = 1) -> float:
        """
        Record consumption of `amount` units for the service.
        Returns current utilisation (0.0–1.0).
        Raises CapacityExceededError if utilisation >= 100%.
        Emits Observatory events at 80%, 90%, 95% thresholds.
        """
        if service not in self._limits:
            return 0.0

        with self._lock:
            sl = self._limits[service]
            sl.reset_if_window_expired()
            sl._used += amount
            util = sl.utilisation()
            self._check_thresholds(sl, util)

            if util >= THRESHOLD_HARD:
                raise CapacityExceededError(service, sl._used, sl.limit)

        return util

    def peek(self, service: CapacityService) -> float:
        """Return current utilisation without consuming or raising."""
        with self._lock:
            if service not in self._limits:
                return 0.0
            sl = self._limits[service]
            sl.reset_if_window_expired()
            return sl.utilisation()

    def _check_thresholds(self, sl: ServiceLimit, util: float) -> None:
        """Emit Observatory events when utilisation crosses a threshold band."""
        # Only emit when crossing a new threshold (not on every call)
        if util >= THRESHOLD_CRITICAL and sl._last_threshold < THRESHOLD_CRITICAL:
            sl._last_threshold = THRESHOLD_CRITICAL
            self._emit(
                sl,
                util,
                "critical",
                f"{sl.description}: {round(util * 100, 1)}% capacity — HARD STOP IMMINENT. "
                f"Used {sl._used}/{sl.limit} in this window.",
            )
        elif util >= THRESHOLD_ALERT and sl._last_threshold < THRESHOLD_ALERT:
            sl._last_threshold = THRESHOLD_ALERT
            self._emit(
                sl,
                util,
                "warning",
                f"{sl.description}: {round(util * 100, 1)}% capacity — approaching limit. "
                f"Used {sl._used}/{sl.limit}.",
            )
        elif util >= THRESHOLD_WARN and sl._last_threshold < THRESHOLD_WARN:
            sl._last_threshold = THRESHOLD_WARN
            self._emit(
                sl,
                util,
                "info",
                f"{sl.description}: {round(util * 100, 1)}% capacity — monitoring. "
                f"Used {sl._used}/{sl.limit}.",
            )

    def _emit(self, sl: ServiceLimit, util: float, severity_str: str, message: str) -> None:
        logger.warning("capacity [%s] %.1f%% — %s", sl.service.value, util * 100, message)
        obs = self._obs()
        if obs is None:
            return
        try:
            from src.observability.observatory import EventCategory, EventSeverity

            _sev_map = {
                "info": EventSeverity.INFO,
                "warning": EventSeverity.WARNING,
                "critical": EventSeverity.CRITICAL,
            }
            obs.record(
                "capacity.threshold_crossed",
                actor="system",
                target=sl.service.value,
                category=EventCategory.SYSTEM,
                severity=_sev_map.get(severity_str, EventSeverity.WARNING),
                service="tranc3-capacity-guard",
                outcome="warning",
                metadata={
                    "service": sl.service.value,
                    "used": sl._used,
                    "limit": sl.limit,
                    "utilisation_pct": round(util * 100, 2),
                    "threshold_crossed": f"{round(util * 100)}%",
                    "window_seconds": sl.window_seconds,
                    "description": sl.description,
                    "message": message,
                },
            )
        except Exception:
            pass

    def status(self) -> dict:
        """Return a dict of all services and their current utilisation."""
        with self._lock:
            result = {}
            for svc, sl in self._limits.items():
                sl.reset_if_window_expired()
                util = sl.utilisation()
                pct = round(util * 100, 2)
                result[svc.value] = {
                    "used": sl._used,
                    "limit": sl.limit,
                    "utilisation_pct": pct,
                    "window_seconds": sl.window_seconds,
                    "description": sl.description,
                    "status": (
                        "hard_stop"
                        if util >= 1.0
                        else "critical"
                        if util >= THRESHOLD_CRITICAL
                        else "alert"
                        if util >= THRESHOLD_ALERT
                        else "warning"
                        if util >= THRESHOLD_WARN
                        else "ok"
                    ),
                }
            return result

    def reset(self, service: CapacityService) -> None:
        """Manually reset a service counter (admin use only)."""
        with self._lock:
            if service in self._limits:
                sl = self._limits[service]
                sl._used = 0
                sl._window_start = time.time()
                sl._last_threshold = 0.0


# ── Singleton ─────────────────────────────────────────────────────────────────

_guard: Optional[CapacityGuard] = None
_guard_lock = threading.Lock()


def get_capacity_guard() -> CapacityGuard:
    global _guard
    if _guard is None:
        with _guard_lock:
            if _guard is None:
                _guard = CapacityGuard()
    return _guard
