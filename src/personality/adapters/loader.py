"""
Adapter loader — maps JSON personality profiles to (future) QLoRA trait adapters.

This is intentionally a thin, side-effect-free stub for v0.9.0 so that the rest
of the platform can begin referencing the concept without requiring trained
weights yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AdapterSpec:
    """Description of a single trait adapter."""

    name: str
    path: Path | None = None
    strength: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class AdapterLoader:
    """
    Loads and mixes trait adapters for a given personality profile.

    Current behaviour (scaffolding):
    - Returns an empty list of adapters (no weights exist yet).
    - Logs the requested profile so future training runs can be correlated.
    - Never mutates the base model.

    Future behaviour:
    - Resolve profile name → list of AdapterSpec
    - Load QLoRA weights from src/personality/adapters/<trait>/
    - Apply them with the requested strength
    """

    def __init__(self, adapters_root: Path | None = None) -> None:
        self.adapters_root = adapters_root or Path(__file__).parent

    def resolve_for_profile(self, profile_name: str) -> list[AdapterSpec]:
        """
        Return the list of adapters that should be active for this profile.

        Until real adapters are trained this always returns an empty list.
        """
        # Placeholder mapping — will be replaced by real trait composition.
        _ = profile_name
        return []

    def load(self, specs: list[AdapterSpec]) -> list[Any]:
        """
        Load adapter weights. Currently a no-op that returns an empty list.
        """
        if not specs:
            return []
        # Future: load peft / bitsandbytes adapters here.
        return []
