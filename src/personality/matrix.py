"""
TRANC3 — Personality Matrix
The layer that sits above the base model and shapes who it is.

A "personality" is a JSON profile that defines:
  - The system prompt (core instructions and character)
  - Generation parameters (temperature, sampling behaviour)
  - Communication style directives
  - Domain emphasis (what it knows to prioritise)

The base model is neutral. The matrix makes it Tranc3.
Swap the profile JSON to get a different entity — no retraining needed.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class PersonalityProfile:
    name: str
    version: str
    system_prompt: str

    # Generation parameters — override inference defaults
    temperature: float = 0.8
    top_k: int = 50
    top_p: float = 0.92
    repetition_penalty: float = 1.15
    max_new_tokens: int = 512

    # Style metadata (used by avatar and UI layers later)
    tone: str = "warm"  # warm | professional | direct | creative
    domain_focus: str = "general"
    avatar_id: Optional[str] = None

    # Extended context injected before every conversation
    context_preamble: str = ""

    @classmethod
    def from_file(cls, path: str) -> "PersonalityProfile":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "PersonalityProfile":
        """Map both the rich JSON profile schema and the flat dataclass schema."""
        behavior = data.get("behavior", {})
        style = data.get("style", {})
        return cls(
            name=data.get("name") or data.get("id") or data.get("code_name", "unknown"),
            version=data.get("version", "1.0.0"),
            system_prompt=data.get("system_prompt") or data.get("system_prompt_prefix", ""),
            temperature=behavior.get("temperature", data.get("temperature", 0.8)),
            top_k=behavior.get("top_k", data.get("top_k", 50)),
            top_p=behavior.get("top_p", data.get("top_p", 0.92)),
            repetition_penalty=behavior.get("repetition_penalty", data.get("repetition_penalty", 1.15)),
            max_new_tokens=behavior.get("max_tokens", data.get("max_new_tokens", 512)),
            tone=style.get("tone", data.get("tone", "warm")),
            domain_focus=data.get("domain", data.get("domain_focus", "general")),
            avatar_id=data.get("avatar_id"),
            context_preamble=data.get("context_preamble", ""),
        )

    def to_file(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2)

    def build_system_prompt(self, user_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Assembles the full system prompt including any user-specific context.
        user_context can carry things like: name, history summary, current mood flag.
        """
        prompt = self.system_prompt

        if self.context_preamble:
            prompt = self.context_preamble.strip() + "\n\n" + prompt

        if user_context:
            context_lines = "\n".join(f"- {k}: {v}" for k, v in user_context.items() if v)
            if context_lines:
                prompt += f"\n\nUser context:\n{context_lines}"

        return prompt.strip()


class PersonalityMatrix:
    """
    Registry of all available personality profiles.
    Loads from the profiles directory; profiles can be added at runtime
    without touching any code.
    """

    def __init__(self, profiles_dir: str = "src/personality/profiles"):
        self.profiles_dir = Path(profiles_dir)
        self._registry: Dict[str, PersonalityProfile] = {}
        self._load_all()

    def _load_all(self):
        if not self.profiles_dir.exists():
            return
        for path in self.profiles_dir.glob("*.json"):
            try:
                profile = PersonalityProfile.from_file(str(path))
                self._registry[profile.name] = profile
            except Exception as e:
                print(f"[PersonalityMatrix] Could not load {path.name}: {e}")

        print(
            f"[PersonalityMatrix] Loaded {len(self._registry)} profile(s): "
            f"{', '.join(self._registry.keys())}"
        )

    def get(self, name: str) -> PersonalityProfile:
        if name not in self._registry:
            available = list(self._registry.keys())
            raise KeyError(f"Profile '{name}' not found. Available: {available}")
        return self._registry[name]

    def list_profiles(self):
        return list(self._registry.keys())

    def register(self, profile: PersonalityProfile):
        self._registry[profile.name] = profile
        profile.to_file(str(self.profiles_dir / f"{profile.name}.json"))
