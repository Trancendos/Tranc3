from __future__ import annotations

import pytest

from src.adaptive import get_provider_rotator
from src.adaptive.provider_rotator import AdaptiveProviderRotator


def test_rotator_status_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAPTIVE_ROTATION_CHAIN", "zero_cost_cloud")
    rotator = AdaptiveProviderRotator()
    status = rotator.status()
    assert "state" in status
    assert "zero_cost" in status["state"]["chain_name"] or status["state"]["chain_name"].startswith(
        "zero_cost",
    )


def test_switch_chain_rejects_paid(monkeypatch: pytest.MonkeyPatch) -> None:
    rotator = AdaptiveProviderRotator()
    assert rotator.switch_chain("near_zero_high_quality") is False
    assert rotator.switch_chain("zero_cost_full") is True


def test_active_provider_fallback_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAPTIVE_ROTATION_CHAIN", "zero_cost_cloud")
    rotator = AdaptiveProviderRotator()
    rotator._state.providers = ["offline"]
    assert rotator.active_provider() == "offline"


def test_get_provider_rotator_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.adaptive.provider_rotator as mod

    monkeypatch.setattr(mod, "_rotator", None)
    a = get_provider_rotator()
    b = get_provider_rotator()
    assert a is b
    assert isinstance(a, AdaptiveProviderRotator)
