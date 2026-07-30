# tests/test_provider_rotation_capacity_feed.py
# Tests for the additive CapacityGuard feed wired into
# ProviderLimit.record_request() (src/ai_gateway/provider_rotation.py) —
# see docs/governance/THRESHOLD-MATRIX.md §5. Verifies real provider usage
# reaches CapacityGuard, and that a CapacityGuard failure never affects
# provider_rotation.py's own rotation/hard-stop behavior.

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ai_gateway.provider_rotation import ProviderLimit
from src.capacity.guard import CapacityGuard, CapacityService, ServiceLimit


@pytest.fixture
def guard():
    return CapacityGuard(
        limits=[ServiceLimit(CapacityService.GROQ_REQUESTS, 100, 86_400, "test groq limit")]
    )


@pytest.fixture
def groq_provider():
    return ProviderLimit(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        daily_req_limit=10_000,
        hourly_req_limit=1_000,
        daily_token_limit=-1,
    )


class TestCapacityFeed:
    def test_request_feeds_matching_provider_into_guard(self, groq_provider, guard):
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            groq_provider.record_request(tokens_used=50)
        assert guard.peek(CapacityService.GROQ_REQUESTS) == pytest.approx(0.01)

    def test_unmapped_provider_is_a_no_op(self, guard):
        mistral = ProviderLimit(
            name="mistral",
            base_url="https://api.mistral.ai/v1",
            api_key_env="MISTRAL_API_KEY",
            daily_req_limit=2000,
            hourly_req_limit=100,
            daily_token_limit=-1,
        )
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            mistral.record_request(tokens_used=50)  # must not raise
        assert mistral._daily_req == 1

    def test_capacity_guard_hard_stop_never_propagates(self, groq_provider, guard):
        """Even if CapacityGuard's own 100% hard stop fires, it must never
        interrupt record_request() — provider_rotation.py's own
        hard_stop_threshold stays authoritative."""
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            for _ in range(101):
                groq_provider.record_request(tokens_used=1)  # would raise past 100 consumed
        assert groq_provider._daily_req == 101

    def test_capacity_guard_import_failure_never_propagates(self, groq_provider):
        with patch(
            "src.capacity.guard.get_capacity_guard", side_effect=RuntimeError("unavailable")
        ):
            groq_provider.record_request(tokens_used=10)  # must not raise
        assert groq_provider._daily_req == 1

    def test_record_request_still_updates_own_counters_regardless(self, groq_provider, guard):
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            groq_provider.record_request(tokens_used=100)
        assert groq_provider._daily_req == 1
        assert groq_provider._daily_tokens == 100
