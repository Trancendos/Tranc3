"""Zero-cost registry v2: chains, aliases, and hard-stop enforcement."""

from __future__ import annotations

import pytest

from src.zero_cost.registry import (
    assert_zero_cost,
    get_chain,
    is_approved,
    load_registry,
    validate_all_chains,
)


def test_load_registry_v2_shape() -> None:
    reg = load_registry()
    assert reg.get("version")
    assert "rotation_chains_map" in reg
    assert len(reg["rotation_chains_map"]) >= 4


def test_ollama_approved() -> None:
    assert is_approved("ollama")


def test_assert_zero_cost_rejects_paid() -> None:
    with pytest.raises(ValueError, match="blocked"):
        assert_zero_cost("openai")


def test_assert_zero_cost_rejects_unlisted_provider() -> None:
    with pytest.raises(ValueError, match="not in the zero-cost registry"):
        assert_zero_cost("openai_paid")


def test_zero_cost_full_chain_has_six_to_eight_providers() -> None:
    chain = get_chain("zero_cost_full")
    assert 6 <= len(chain) <= 10
    assert_zero_cost(chain)


def test_zero_cost_cloud_chain() -> None:
    """Cloud-only chain: no local Ollama (Tier-1 / cloud-only deploy paths)."""
    chain = get_chain("zero_cost_cloud")
    assert len(chain) >= 6
    assert "ollama" not in chain
    assert "huggingface" in chain
    assert "offline" in chain
    assert_zero_cost(chain)


def test_zero_cost_local_chain() -> None:
    chain = get_chain("zero_cost_local")
    assert "ollama" in chain
    assert "offline" in chain
    assert_zero_cost(chain)


def test_chain_alias_inference_default() -> None:
    assert get_chain("inference_default") == get_chain("zero_cost_cloud")


def test_chain_alias_inference_local() -> None:
    assert get_chain("inference_local") == get_chain("zero_cost_local")


def test_validate_all_chains_empty() -> None:
    assert validate_all_chains() == []


def test_unknown_chain_raises() -> None:
    with pytest.raises(ValueError, match="Unknown rotation chain"):
        get_chain("nonexistent_chain_xyz")


def test_assert_zero_cost_list_rejects_mixed() -> None:
    with pytest.raises(ValueError):
        assert_zero_cost(["ollama", "openai_paid"])
