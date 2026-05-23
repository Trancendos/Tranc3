# tests/test_resilience.py
# Tests for src/resilience/circuit_breaker.py
# Covers CircuitBreaker, Bulkhead (async), and ResilienceManager.

from __future__ import annotations

import time

import pytest

from src.resilience.circuit_breaker import (
    Bulkhead,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ResilienceManager,
)


# ── CircuitState enum ────────────────────────────────────────────────


class TestCircuitState:
    def test_enum_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_enum_is_str(self):
        assert isinstance(CircuitState.CLOSED, str)
        assert CircuitState.CLOSED == "closed"


# ── CircuitBreakerConfig ─────────────────────────────────────────────


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.recovery_timeout == 30.0
        assert cfg.half_open_max_calls == 3
        assert cfg.success_threshold == 2

    def test_custom_values(self):
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=10.0,
            half_open_max_calls=5,
            success_threshold=1,
        )
        assert cfg.failure_threshold == 3
        assert cfg.recovery_timeout == 10.0
        assert cfg.half_open_max_calls == 5
        assert cfg.success_threshold == 1


# ── CircuitBreaker ───────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test-svc")
        assert cb.state == CircuitState.CLOSED
        assert cb.name == "test-svc"

    def test_can_execute_when_closed(self):
        cb = CircuitBreaker("svc")
        assert cb.can_execute() is True

    def test_cannot_execute_when_open(self):
        cb = CircuitBreaker("svc")
        cb.state = CircuitState.OPEN
        assert cb.can_execute() is False

    def test_record_success_decrements_failure_count(self):
        cb = CircuitBreaker("svc")
        cb._failure_count = 3
        cb.record_success()
        assert cb._failure_count == 2
        assert cb._total_calls == 1

    def test_record_failure_increments_failure_count(self):
        cb = CircuitBreaker("svc")
        cb.record_failure()
        assert cb._failure_count == 1
        assert cb._total_calls == 1
        assert cb._total_failures == 1
        assert cb._last_failure_time is not None

    def test_closed_to_open_after_threshold(self):
        cb = CircuitBreaker("svc", CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_allows_limited_calls(self):
        cb = CircuitBreaker("svc", CircuitBreakerConfig(half_open_max_calls=2))
        cb.state = CircuitState.HALF_OPEN
        assert cb.can_execute() is True  # call 1
        assert cb.can_execute() is True  # call 2
        assert cb.can_execute() is False  # call 3 — exceeds max

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker("svc", CircuitBreakerConfig(success_threshold=2))
        cb.state = CircuitState.HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker("svc")
        cb.state = CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("svc", CircuitBreakerConfig(recovery_timeout=0.01))
        cb.state = CircuitState.OPEN
        cb._last_failure_time = time.time() - 1  # well past timeout
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_open_stays_open_before_recovery_timeout(self):
        cb = CircuitBreaker("svc", CircuitBreakerConfig(recovery_timeout=9999.0))
        cb.state = CircuitState.OPEN
        cb._last_failure_time = time.time()
        assert cb.can_execute() is False
        assert cb.state == CircuitState.OPEN

    def test_stats_structure(self):
        cb = CircuitBreaker("svc")
        cb.record_success()
        cb.record_failure()
        s = cb.stats
        assert s["name"] == "svc"
        assert s["state"] == "closed"
        assert s["total_calls"] == 2
        assert s["total_failures"] == 1
        assert 0.0 <= s["failure_rate"] <= 1.0

    def test_stats_failure_rate_zero_when_no_calls(self):
        cb = CircuitBreaker("svc")
        assert cb.stats["failure_rate"] == 0.0

    def test_failure_count_never_goes_below_zero(self):
        cb = CircuitBreaker("svc")
        cb.record_success()  # decrement from 0
        assert cb._failure_count == 0


# ── CircuitBreaker.call() ────────────────────────────────────────────


class TestCircuitBreakerCall:
    @pytest.mark.asyncio
    async def test_call_sync_function_success(self):
        cb = CircuitBreaker("svc")

        def sync_fn(x, y):
            return x + y

        result = await cb.call(sync_fn, 2, 3)
        assert result == 5
        assert cb._total_calls == 1

    @pytest.mark.asyncio
    async def test_call_async_function_success(self):
        cb = CircuitBreaker("svc")

        async def async_fn(x):
            return x * 2

        result = await cb.call(async_fn, 7)
        assert result == 14

    @pytest.mark.asyncio
    async def test_call_records_failure_on_exception(self):
        cb = CircuitBreaker("svc")

        def failing_fn():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await cb.call(failing_fn)
        assert cb._total_failures == 1

    @pytest.mark.asyncio
    async def test_call_rejects_when_open(self):
        cb = CircuitBreaker("svc")
        cb.state = CircuitState.OPEN
        with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
            await cb.call(lambda: None)

    @pytest.mark.asyncio
    async def test_call_with_kwargs(self):
        cb = CircuitBreaker("svc")

        def fn(a, b=10):
            return a + b

        result = await cb.call(fn, 5, b=20)
        assert result == 25


# ── Bulkhead ─────────────────────────────────────────────────────────


class TestBulkhead:
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        bh = Bulkhead("svc", max_concurrent=2, max_queue=2)
        acquired = await bh.acquire()
        assert acquired is True
        assert bh._active == 1
        bh.release()
        assert bh._active == 0

    @pytest.mark.asyncio
    async def test_stats_structure(self):
        bh = Bulkhead("svc")
        s = bh.stats
        assert s["name"] == "svc"
        assert "active" in s
        assert "queued" in s
        assert "rejected" in s


# ── ResilienceManager ────────────────────────────────────────────────


class TestResilienceManager:
    def test_get_breaker_creates_new(self):
        rm = ResilienceManager()
        cb = rm.get_breaker("my-svc")
        assert isinstance(cb, CircuitBreaker)
        assert cb.name == "my-svc"

    def test_get_breaker_returns_existing(self):
        rm = ResilienceManager()
        cb1 = rm.get_breaker("svc-a")
        cb2 = rm.get_breaker("svc-a")
        assert cb1 is cb2

    def test_get_breaker_with_config(self):
        rm = ResilienceManager()
        cfg = CircuitBreakerConfig(failure_threshold=2)
        cb = rm.get_breaker("svc-cfg", config=cfg)
        assert cb.config.failure_threshold == 2

    def test_get_bulkhead_creates_new(self):
        rm = ResilienceManager()
        bh = rm.get_bulkhead("my-svc", max_concurrent=5)
        assert isinstance(bh, Bulkhead)
        assert bh.name == "my-svc"

    def test_get_bulkhead_returns_existing(self):
        rm = ResilienceManager()
        bh1 = rm.get_bulkhead("svc-a")
        bh2 = rm.get_bulkhead("svc-a")
        assert bh1 is bh2

    def test_health_structure(self):
        rm = ResilienceManager()
        rm.get_breaker("svc-1")
        rm.get_bulkhead("svc-2")
        h = rm.health()
        assert "circuit_breakers" in h
        assert "bulkheads" in h
        assert "svc-1" in h["circuit_breakers"]
        assert "svc-2" in h["bulkheads"]

    def test_health_empty(self):
        rm = ResilienceManager()
        h = rm.health()
        assert h["circuit_breakers"] == {}
        assert h["bulkheads"] == {}
