# src/relations/personality.py
"""Best-effort personality-quirk loader for the Relationship Matrix.

Reads `src/personality/profiles/*.json` keyed by `code_name`, which is the
same canonical AI name used by `src/entities/platform.py`'s `lead_ai` field
and the Role Assignment Registry. Not every Lead AI has a matching profile
(profiles predate the full 43-entity roster and some use different
spellings — e.g. "The Guardian" vs. "The Guardian (Marcus Magnolia)")
so every lookup falls back to a neutral default rather than raising.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

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


def _load_profile_dict(path: Path) -> Optional[Dict[str, Any]]:
    """Read+parse one profile file, returning None on any I/O, JSON, or
    shape problem — this loader's whole contract is "never raise, always
    fall back to neutral," so a malformed profile (unreadable file, invalid
    JSON, invalid UTF-8, a JSON array instead of an object, `"style": null`,
    etc.) is handled the same way as a missing one. A `logger.warning` is
    still emitted so operators can spot genuine data corruption rather than
    the module silently switching an AI to neutral forever.

    `ValueError` covers both `json.JSONDecodeError` and `UnicodeDecodeError`
    (raised by `read_text()` on invalid UTF-8) — both are `ValueError`
    subclasses. `RecursionError` is caught explicitly because it is *not* a
    `ValueError` subclass but deeply-nested JSON can still trigger it; letting
    it escape would crash `_build_index`, leave `_index` as None, and break
    every subsequent lookup — exactly the "never raise" failure this contract
    forbids.
    """
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError, RecursionError) as exc:
        logger.warning("personality profile %s could not be read/parsed: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning(
            "personality profile %s is not a JSON object (got %s) — ignoring",
            path,
            type(data).__name__,
        )
        return None
    return data


def _build_index() -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    if not _PROFILES_DIR.is_dir():
        return index
    for path in sorted(_PROFILES_DIR.glob("*.json")):
        data = _load_profile_dict(path)
        if data is None:
            continue
        code_name = data.get("code_name")
        # Must be a non-empty string: a non-string (e.g. a list) would be
        # unhashable and crash on `code_name in index`, and an empty string
        # is meaningless as a key.
        if not isinstance(code_name, str) or not code_name:
            logger.warning(
                "personality profile %s has a missing or non-string code_name — ignoring", path
            )
            continue
        if code_name in index:
            logger.warning(
                "personality profile code_name collision: %r defined in both %s and %s — using %s",
                code_name,
                index[code_name],
                path,
                path,
            )
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
    data = _load_profile_dict(path) if path is not None else None
    if data is None:
        result = PersonalityQuirks(code_name=code_name)
        _cache[code_name] = result
        return result

    traits = dict(_NEUTRAL_TRAITS)
    raw_traits = data.get("traits")
    if isinstance(raw_traits, dict):
        traits.update(raw_traits)

    style = data.get("style")
    tone = style.get("tone", "neutral") if isinstance(style, dict) else "neutral"

    result = PersonalityQuirks(
        code_name=code_name,
        description=data.get("description") or "",
        tone=tone,
        traits=traits,
        system_prompt_prefix=data.get("system_prompt_prefix") or "",
        found=True,
    )
    _cache[code_name] = result
    return result
