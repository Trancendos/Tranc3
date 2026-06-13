"""Self-tuning rate limiter. Tightens on high error rates, loosens on low."""
import time
import threading
from collections import defaultdict, deque
from typing import Dict


class _TenantBucket:
    """Token bucket + sliding window for a single tenant."""

    def __init__(self, rate: int, window_seconds: int, burst_multiplier: float):
        self.rate = rate
        self.window_seconds = window_seconds
        self.burst_multiplier = burst_multiplier

        self._tokens = float(rate)
        self._max_tokens = rate * burst_multiplier
        self._last_refill = time.monotonic()

        # Sliding window for request timestamps
        self._window: deque = deque()

        # Error/success tracking
        self._errors: deque = deque()   # timestamps of errors
        self._successes: deque = deque()  # timestamps of successes

        # Adjusted rate (can be tuned up/down)
        self._effective_rate = float(rate)
        self._last_tune = time.monotonic()
        self._tune_interval = 60.0  # seconds between auto-tune

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill = elapsed * (self._effective_rate / self.window_seconds)
        self._tokens = min(self._max_tokens, self._tokens + refill)
        self._last_refill = now

    def _prune(self, now: float):
        cutoff = now - self.window_seconds
        while self._window and self._window[0] < cutoff:
            self._window.popleft()
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()
        while self._successes and self._successes[0] < cutoff:
            self._successes.popleft()

    def allow(self) -> bool:
        now = time.monotonic()
        self._refill()
        self._prune(now)

        # Check both token bucket and sliding window count
        window_count = len(self._window)
        if self._tokens >= 1.0 and window_count < int(self._effective_rate):
            self._tokens -= 1.0
            self._window.append(now)
            return True
        return False

    def record_error(self):
        self._errors.append(time.monotonic())
        self._maybe_tune()

    def record_success(self):
        self._successes.append(time.monotonic())
        self._maybe_tune()

    def _maybe_tune(self):
        now = time.monotonic()
        if now - self._last_tune < self._tune_interval:
            return
        self._last_tune = now
        self._adjust()

    def _adjust(self):
        now = time.monotonic()
        cutoff = now - self.window_seconds
        error_count = sum(1 for t in self._errors if t > cutoff)
        success_count = sum(1 for t in self._successes if t > cutoff)
        total = error_count + success_count
        if total == 0:
            return

        error_rate = error_count / total

        if error_rate > 0.10:
            # Tighten: reduce effective rate by 20%
            self._effective_rate = max(1.0, self._effective_rate * 0.80)
        elif error_rate < 0.01 and now - self._last_tune >= 300:
            # Loosen: increase effective rate by 10%, capped at 2x base
            max_rate = self.rate * 2.0
            self._effective_rate = min(max_rate, self._effective_rate * 1.10)

    def stats(self) -> Dict:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        return {
            "effective_rate": self._effective_rate,
            "tokens": self._tokens,
            "window_count": len(self._window),
            "error_count": sum(1 for t in self._errors if t > cutoff),
            "success_count": sum(1 for t in self._successes if t > cutoff),
        }


class AdaptiveRateLimiter:
    def __init__(
        self,
        base_rate: int = 100,
        window_seconds: int = 60,
        burst_multiplier: float = 1.5,
    ):
        self._base_rate = base_rate
        self._window = window_seconds
        self._burst = burst_multiplier
        self._buckets: Dict[str, _TenantBucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, tenant_id: str) -> _TenantBucket:
        with self._lock:
            if tenant_id not in self._buckets:
                self._buckets[tenant_id] = _TenantBucket(
                    self._base_rate, self._window, self._burst
                )
            return self._buckets[tenant_id]

    def check(self, tenant_id: str = "global") -> bool:
        """Returns True if the request is allowed, False if rate-limited."""
        bucket = self._get_bucket(tenant_id)
        with self._lock:
            return bucket.allow()

    def record_error(self, tenant_id: str = "global"):
        """Record an error for adaptive tuning."""
        self._get_bucket(tenant_id).record_error()
        self._adjust_rates()

    def record_success(self, tenant_id: str = "global"):
        """Record a success for adaptive tuning."""
        self._get_bucket(tenant_id).record_success()

    def _adjust_rates(self):
        """Trigger rate adjustment across all tenants."""
        with self._lock:
            for bucket in self._buckets.values():
                bucket._adjust()

    def get_stats(self) -> Dict:
        """Return stats for all tracked tenants."""
        with self._lock:
            return {
                tenant_id: bucket.stats()
                for tenant_id, bucket in self._buckets.items()
            }

    def reset(self, tenant_id: str = "global"):
        """Remove a tenant bucket (resets to base_rate on next check)."""
        with self._lock:
            self._buckets.pop(tenant_id, None)
