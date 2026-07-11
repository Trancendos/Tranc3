# src/relations/personality.py
"""Best-effort personality-quirk loader for the Relationship Matrix.

Reads `src/personality/profiles/*.json` keyed by `code_name`, which is the
same canonical AI name used by `src/entities/platform.py`'s `lead_ai` field
and the Role Assignment Registry. Not every Lead AI has a matching profile
(profiles predate the full 43-entity roster and some use different
spellings — e.g. "The Guardian" vs. "The Guardian (Anchor: Orb of Orisis)")
so every lookup falls back to a neutral default rather than raising.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

_PROFILES_DIR = Path(__file__).resolve().parents[2] / "src" / "personality" / "profiles"

_NEUTRAL_TRAITS = {
    "openness": 0.5,
    "agreeableness": 0.5,
    "empathy": 0.5,
    "assertiveness": 0.5,
    "neuroticism": 0.5,
    "humor": 0.5,
}


@dataclass
class PersonalityQuirks:
    code_name: str
    description: str = ""
    tone: str = "neutral"
    traits: Dict[str, float] = field(default_factory=lambda: dict(_NEUTRAL_TRAITS))
    system_prompt_prefix: str = ""
    found: bool = False

    @property
    def positivity_multiplier(self) -> float:
        """How much bigger a positive relationship nudge should land — driven
        by agreeableness/empathy. Ranges roughly 0.7x-1.3x."""
        agreeableness = self.traits.get("agreeableness", 0.5)
        empathy = self.traits.get("empathy", 0.5)
        return 0.7 + 0.6 * ((agreeableness + empathy) / 2)

    @property
    def negativity_multiplier(self) -> float:
        """How much bigger a negative relationship nudge should land — driven
        by assertiveness/neuroticism. Ranges roughly 0.7x-1.3x."""
        assertiveness = self.traits.get("assertiveness", 0.5)
        neuroticism = self.traits.get("neuroticism", 0.5)
        return 0.7 + 0.6 * ((assertiveness + neuroticism) / 2)


_cache: Dict[str, PersonalityQuirks] = {}
_index: Optional[Dict[str, Path]] = None


def _build_index() -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    if not _PROFILES_DIR.is_dir():
        return index
    for path in _PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        code_name = data.get("code_name")
        if code_name:
            index[code_name] = path
    return index


def get_quirks(code_name: str) -> PersonalityQuirks:
    """Best-effort lookup — returns a neutral default when no profile matches."""
    if code_name in _cache:
        return _cache[code_name]

    global _index
    if _index is None:
        _index = _build_index()

    path = _index.get(code_name)
    if path is None:
        result = PersonalityQuirks(code_name=code_name)
        _cache[code_name] = result
        return result

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        result = PersonalityQuirks(code_name=code_name)
        _cache[code_name] = result
        return result

    traits = dict(_NEUTRAL_TRAITS)
    traits.update(data.get("traits", {}))
    result = PersonalityQuirks(
        code_name=code_name,
        description=data.get("description", ""),
        tone=data.get("style", {}).get("tone", "neutral"),
        traits=traits,
        system_prompt_prefix=data.get("system_prompt_prefix", ""),
        found=True,
    )
    _cache[code_name] = result
    return result
