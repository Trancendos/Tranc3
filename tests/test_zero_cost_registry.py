from __future__ import annotations

from src.zero_cost.registry import approved_ids, is_approved, load_registry


def test_load_registry():
    reg = load_registry()
    assert reg.get("version")
    assert len(reg.get("approved_self_hosted", [])) >= 5


def test_ollama_approved():
    assert is_approved("ollama")
    assert "ollama" in approved_ids()
