# tests/test_capacity_guard.py
# Tests for src/capacity/guard.py's CapacityGuard — previously had zero
# coverage and zero call sites anywhere in the codebase (see
# docs/governance/THRESHOLD-MATRIX.md §5). Verifies the 80/90/95/100%
# escalation ladder and Observatory event emission.

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.capacity.guard import (
    CapacityExceededError,
    CapacityGuard,
    CapacityService,
    ServiceLimit,
)
from src.observability.observatory import Observatory


@pytest.fixture
def guard():
    return CapacityGuard(
        limits=[ServiceLimit(CapacityService.GROQ_REQUESTS, 100, 86_400, "test groq limit")]
    )


class TestConsume:
    def test_below_threshold_returns_utilisation(self, guard):
        util = guard.consume(CapacityService.GROQ_REQUESTS, 10)
        assert util == pytest.approx(0.10)

    def test_accumulates_across_calls(self, guard):
        guard.consume(CapacityService.GROQ_REQUESTS, 30)
        util = guard.consume(CapacityService.GROQ_REQUESTS, 30)
        assert util == pytest.approx(0.60)

    def test_unregistered_service_returns_zero_without_raising(self, guard):
        assert guard.consume(CapacityService.QUEUE_DEPTH, 999999) == 0.0

    def test_hard_stop_at_100pct_raises(self, guard):
        with pytest.raises(CapacityExceededError):
            guard.consume(CapacityService.GROQ_REQUESTS, 100)

    def test_hard_stop_error_carries_service_and_usage(self, guard):
        with pytest.raises(CapacityExceededError) as exc_info:
            guard.consume(CapacityService.GROQ_REQUESTS, 150)
        assert exc_info.value.service == CapacityService.GROQ_REQUESTS
        assert exc_info.value.used == 150
        assert exc_info.value.limit == 100


class TestPeek:
    def test_does_not_consume(self, guard):
        guard.consume(CapacityService.GROQ_REQUESTS, 50)
        assert guard.peek(CapacityService.GROQ_REQUESTS) == pytest.approx(0.50)
        assert guard.peek(CapacityService.GROQ_REQUESTS) == pytest.approx(0.50)

    def test_unregistered_service_is_zero(self, guard):
        assert guard.peek(CapacityService.QUEUE_DEPTH) == 0.0


class TestThresholdEscalation:
    def test_emits_observatory_event_at_each_band(self, guard):
        test_obs = Observatory()
        with patch("src.observability.observatory.get_observatory", return_value=test_obs):
            guard.consume(CapacityService.GROQ_REQUESTS, 80)  # crosses 80%
            guard.consume(CapacityService.GROQ_REQUESTS, 10)  # crosses 90%
            guard.consume(CapacityService.GROQ_REQUESTS, 5)  # crosses 95%
        events = test_obs.recent(limit=20)
        types = [e.event_type for e in events]
        assert types.count("capacity.threshold_crossed") == 3

    def test_does_not_re_emit_within_same_band(self, guard):
        test_obs = Observatory()
        with patch("src.observability.observatory.get_observatory", return_value=test_obs):
            guard.consume(CapacityService.GROQ_REQUESTS, 81)
            guard.consume(CapacityService.GROQ_REQUESTS, 1)
        events = test_obs.recent(limit=20)
        assert len([e for e in events if e.event_type == "capacity.threshold_crossed"]) == 1

    def test_never_raises_when_observatory_unavailable(self, guard):
        with patch(
            "src.observability.observatory.get_observatory",
            side_effect=RuntimeError("unavailable"),
        ):
            # Should not raise despite Observatory being broken.
            guard.consume(CapacityService.GROQ_REQUESTS, 80)


class TestStatus:
    def test_status_reports_band_labels(self, guard):
        guard.consume(CapacityService.GROQ_REQUESTS, 96)
        status = guard.status()
        assert status[CapacityService.GROQ_REQUESTS.value]["status"] == "critical"

    def test_status_ok_below_warn_band(self, guard):
        status = guard.status()
        assert status[CapacityService.GROQ_REQUESTS.value]["status"] == "ok"


class TestConfigureAndReset:
    def test_configure_overrides_existing_limit(self, guard):
        guard.configure(CapacityService.GROQ_REQUESTS, 1000, 3600)
        util = guard.consume(CapacityService.GROQ_REQUESTS, 100)
        assert util == pytest.approx(0.10)

    def test_configure_adds_new_service(self, guard):
        guard.configure(CapacityService.QUEUE_DEPTH, 50, 60)
        util = guard.consume(CapacityService.QUEUE_DEPTH, 25)
        assert util == pytest.approx(0.50)

    def test_reset_clears_usage(self, guard):
        guard.consume(CapacityService.GROQ_REQUESTS, 90)
        guard.reset(CapacityService.GROQ_REQUESTS)
        assert guard.peek(CapacityService.GROQ_REQUESTS) == 0.0
