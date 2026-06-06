"""
Tests for resilience primitives: Bulkhead, rate limiters, and RetryPolicy.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.mesh.bulkhead import Bulkhead, BulkheadFullError, BulkheadTimeoutError
from src.mesh.rate_limiter import (
    SlidingWindowLimiter,
    TokenBucketLimiter,
    FixedWindowLimiter,
)
from src.mesh.retry import RetryPolicy, RetryExhaustedError, with_retry, with_retry_sync


# ── Bulkhead ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulkhead_basic_execution():
    bh = Bulkhead("test-basic", max_concurrent=2, max_queue=5)

    async def work():
        return 42

    result = await bh.execute(work())
    assert result == 42


@pytest.mark.asyncio
async def test_bulkhead_concurrent_limit():
    """Tasks beyond max_concurrent are queued, not rejected (while queue has space)."""
    bh = Bulkhead("test-concurrent", max_concurrent=2, max_queue=10, queue_timeout=2.0)
    results = []

    async def slow_work(n: int):
        await asyncio.sleep(0.05)
        results.append(n)
        return n

    tasks = [bh.execute(slow_work(i)) for i in range(5)]
    outputs = await asyncio.gather(*tasks)
    assert sorted(outputs) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_bulkhead_queue_overflow_rejection():
    """When both active and queue slots are full, BulkheadFullError is raised."""
    bh = Bulkhead("test-full", max_concurrent=1, max_queue=1, queue_timeout=5.0)
    event = asyncio.Event()

    async def hold():
        await event.wait()

    # Fill the 1 active slot
    task1 = asyncio.ensure_future(bh.execute(hold()))
    await asyncio.sleep(0.01)  # let task1 acquire the slot

    # Fill the 1 queue slot
    task2 = asyncio.ensure_future(bh.execute(hold()))
    await asyncio.sleep(0.01)

    # Third task should be rejected
    with pytest.raises(BulkheadFullError):
        await bh.execute(hold())

    event.set()
    await asyncio.gather(task1, task2, return_exceptions=True)


@pytest.mark.asyncio
async def test_bulkhead_queue_timeout():
    """Queued task times out when no slot becomes available."""
    bh = Bulkhead("test-timeout", max_concurrent=1, max_queue=1, queue_timeout=0.05)
    event = asyncio.Event()

    async def hold():
        await event.wait()

    task1 = asyncio.ensure_future(bh.execute(hold()))
    await asyncio.sleep(0.01)

    with pytest.raises(BulkheadTimeoutError):
        await bh.execute(hold())

    event.set()
    await task1


@pytest.mark.asyncio
async def test_bulkhead_metrics():
    bh = Bulkhead("test-metrics", max_concurrent=3, max_queue=5)

    async def work():
        return 1

    for _ in range(4):
        await bh.execute(work())

    m = bh.get_metrics()
    assert m.total_executions == 4
    assert m.total_rejections == 0
    assert m.avg_execution_time >= 0.0


# ── TokenBucketLimiter ────────────────────────────────────────────────────────


def test_token_bucket_allows_up_to_max():
    lim = TokenBucketLimiter("tb-test", max_requests=5, window_ms=1000)
    for _ in range(5):
        r = lim.consume("user")
        assert r.allowed is True
    # 6th should be denied
    r = lim.consume("user")
    assert r.allowed is False


def test_token_bucket_burst_capacity():
    lim = TokenBucketLimiter("tb-burst", max_requests=3, window_ms=1000, burst_capacity=6)
    for _ in range(6):
        r = lim.consume("u")
        assert r.allowed is True
    r = lim.consume("u")
    assert r.allowed is False


def test_token_bucket_refill():
    lim = TokenBucketLimiter("tb-refill", max_requests=2, window_ms=100)
    for _ in range(2):
        lim.consume("u")
    # exhaust
    assert lim.consume("u").allowed is False
    time.sleep(0.12)  # wait for refill
    assert lim.consume("u").allowed is True


# ── SlidingWindowLimiter ──────────────────────────────────────────────────────


def test_sliding_window_basic():
    lim = SlidingWindowLimiter("sw-test", max_requests=3, window_ms=500)
    for _ in range(3):
        r = lim.consume("k")
        assert r.allowed is True
    r = lim.consume("k")
    assert r.allowed is False
    assert r.remaining == 0


def test_sliding_window_expiry():
    lim = SlidingWindowLimiter("sw-expiry", max_requests=2, window_ms=100)
    lim.consume("k")
    lim.consume("k")
    assert lim.consume("k").allowed is False
    time.sleep(0.11)
    assert lim.consume("k").allowed is True


def test_fixed_window_basic():
    lim = FixedWindowLimiter("fw-test", max_requests=3, window_ms=500)
    for _ in range(3):
        r = lim.consume("k")
        assert r.allowed is True
    assert lim.consume("k").allowed is False


# ── RetryPolicy ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_succeeds_first_try():
    policy = RetryPolicy(max_attempts=3)
    calls = []

    async def fn():
        calls.append(1)
        return "ok"

    result = await with_retry(fn, policy)
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_retries_on_exception():
    policy = RetryPolicy(max_attempts=3, initial_delay_ms=1.0, jitter=False)
    calls = []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("fail")
        return "success"

    result = await with_retry(fn, policy)
    assert result == "success"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    policy = RetryPolicy(max_attempts=3, initial_delay_ms=1.0, jitter=False)

    async def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RetryExhaustedError) as exc_info:
        await with_retry(fn, policy)
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, RuntimeError)


@pytest.mark.asyncio
async def test_retry_non_retryable_raises_immediately():
    policy = RetryPolicy(
        max_attempts=5,
        retryable_exceptions=(ValueError,),
        initial_delay_ms=1.0,
    )
    calls = []

    async def fn():
        calls.append(1)
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        await with_retry(fn, policy)
    assert len(calls) == 1


def test_retry_sync_version():
    policy = RetryPolicy(max_attempts=3, initial_delay_ms=1.0, jitter=False)
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise IOError("transient")
        return "done"

    result = with_retry_sync(fn, policy)
    assert result == "done"
    assert len(calls) == 2


def test_retry_on_retry_callback():
    policy = RetryPolicy(max_attempts=3, initial_delay_ms=1.0, jitter=False)
    retried: list[int] = []

    def on_retry(attempt, exc, delay):
        retried.append(attempt)

    policy.on_retry = on_retry
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("fail")
        return "ok"

    with_retry_sync(fn, policy)
    assert retried == [1, 2]
