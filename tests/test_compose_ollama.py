"""Ollama service contract for live deploy."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_includes_ollama_for_zero_cost_inference():
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
    assert "ollama" in compose["services"]
    assert "ollama-data" in compose.get("volumes", {})
