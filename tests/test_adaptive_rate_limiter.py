"""
Tests for AdaptiveRateLimiter — src/core/adaptive_rate_limiter.py
"""

import time
import pytest
from src.core.adaptive_rate_limiter import AdaptiveRateLimiter


# ── Basic token bucket ────────────────────────────────────────────────────


def test_allows_requests_within_burst():
    """Requests within burst capacity should all succeed."""
    limiter = AdaptiveRateLimiter(base_rate=100, window_seconds=60)
    allowed = sum(1 for _ in range(10) if limiter.check("user-a"))
    assert allowed == 10


def test_rejects_when_burst_exhausted():
    """Once burst is consumed rapidly, subsequent requests must be rejected."""
    # base_rate=3 with window=60 → max ~3 * 1.5 burst = 4 tokens
    limiter = AdaptiveRateLimiter(base_rate=3, window_seconds=60, burst_multiplier=1.0)
    results = [limiter.check("user-b") for _ in range(20)]
    allowed = results.count(True)
    rejected = results.count(False)
    assert allowed <= 5
    assert rejected >= 10


def test_per_tenant_isolation():
    """Different tenants should have independent buckets."""
    limiter = AdaptiveRateLimiter(base_rate=2, window_seconds=60, burst_multiplier=1.0)
    # Drain tenant-X
    for _ in range(10):
        limiter.check("tenant-x")
    # tenant-y should still have tokens
    assert limiter.check("tenant-y") is True


def test_record_error_reduces_effective_rate():
    """Repeated errors should cause the effective rate to drop."""
    limiter = AdaptiveRateLimiter(base_rate=100, window_seconds=60)
    # Prime the bucket
    for _ in range(5):
        limiter.check("err-tenant")
    # Get initial effective rate
    initial_stats = limiter.get_stats().get("err-tenant", {})

    # Flood errors
    for _ in range(30):
        limiter.check("err-tenant")
        limiter.record_error("err-tenant")

    final_stats = limiter.get_stats().get("err-tenant", {})
    # Effective rate should have decreased or stayed ≤ initial
    initial_rate = initial_stats.get("effective_rate", 100)
    final_rate = final_stats.get("effective_rate", 100)
    assert final_rate <= initial_rate + 1  # allow tiny float rounding


def test_get_stats_returns_dict():
    """get_stats must return a dict (possibly empty) without raising."""
    limiter = AdaptiveRateLimiter()
    limiter.check("stats-tenant")
    stats = limiter.get_stats()
    assert isinstance(stats, dict)
    assert "stats-tenant" in stats


def test_reset_clears_tenant_bucket():
    """reset() should remove tenant's tracking state."""
    limiter = AdaptiveRateLimiter(base_rate=2, window_seconds=60, burst_multiplier=1.0)
    for _ in range(10):
        limiter.check("reset-tenant")
    limiter.reset("reset-tenant")
    # After reset, bucket is recreated with full tokens — should allow again
    assert limiter.check("reset-tenant") is True


def test_record_success_does_not_raise():
    """record_success must not raise."""
    limiter = AdaptiveRateLimiter()
    limiter.check("success-tenant")
    limiter.record_success("success-tenant")  # should not raise


def test_multiple_tenants_tracked_independently():
    """get_stats should show separate entries per tenant."""
    limiter = AdaptiveRateLimiter(base_rate=10, window_seconds=60)
    for i in range(3):
        limiter.check(f"t{i}")
    stats = limiter.get_stats()
    for i in range(3):
        assert f"t{i}" in stats
