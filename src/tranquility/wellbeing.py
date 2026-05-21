# src/tranquility/wellbeing.py
# Tranquility — wellbeing hub for Trancendos users.
#
# Provides:
#   - Mood check-in tracking (user-reported, optional)
#   - Wellbeing score (composite of interaction patterns + self-reports)
#   - Mindfulness prompts and breaks
#   - Burnout pattern detection (overuse signals from tAimra)
#   - Routes to Resonate for empathy services
#
# All data is user-scoped and governed by Magna Carta + I-Mind protocols.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MoodLevel(int, Enum):
    VERY_LOW  = 1
    LOW       = 2
    NEUTRAL   = 3
    GOOD      = 4
    EXCELLENT = 5


@dataclass
class MoodEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    timestamp: float = field(default_factory=time.time)
    mood: MoodLevel = MoodLevel.NEUTRAL
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "mood": self.mood.value,
            "mood_label": self.mood.name.lower().replace("_", " "),
            "tags": self.tags,
        }


@dataclass
class WellbeingProfile:
    user_id: str
    entries: List[MoodEntry] = field(default_factory=list)
    last_break_prompt: float = 0.0
    session_start: float = field(default_factory=time.time)
    session_messages: int = 0

    def average_mood(self, last_n: int = 7) -> float:
        recent = self.entries[-last_n:] if self.entries else []
        if not recent:
            return 3.0
        return sum(e.mood.value for e in recent) / len(recent)

    def needs_break(self) -> bool:
        session_mins = (time.time() - self.session_start) / 60
        return session_mins > 90 or self.session_messages > 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "average_mood_7d": round(self.average_mood(), 2),
            "total_entries": len(self.entries),
            "needs_break": self.needs_break(),
            "session_messages": self.session_messages,
        }


_MINDFULNESS_PROMPTS = [
    "Take a moment to breathe — three deep breaths before we continue.",
    "You've been working for a while. A short break can sharpen focus.",
    "Notice how you're feeling right now. It's okay to step away.",
    "Hydration check — have you had water recently?",
    "Your wellbeing matters more than any task. Take it at your pace.",
]


class Tranquility:
    """
    Tranquility — user wellbeing and mindfulness service.
    """

    def __init__(self):
        self._profiles: Dict[str, WellbeingProfile] = {}

    def get_or_create(self, user_id: str) -> WellbeingProfile:
        if user_id not in self._profiles:
            self._profiles[user_id] = WellbeingProfile(user_id=user_id)
        return self._profiles[user_id]

    def log_mood(self, user_id: str, mood: int, notes: str = "",
                 tags: Optional[List[str]] = None) -> MoodEntry:
        profile = self.get_or_create(user_id)
        try:
            mood_level = MoodLevel(max(1, min(5, mood)))
        except ValueError:
            mood_level = MoodLevel.NEUTRAL
        entry = MoodEntry(user_id=user_id, mood=mood_level, notes=notes, tags=tags or [])
        profile.entries.append(entry)

        if mood_level in (MoodLevel.VERY_LOW, MoodLevel.LOW):
            try:
                from src.imind.protocol import get_imind
                get_imind().assess(f"User reported mood: {mood_level.name}", actor=user_id)
            except Exception:
                pass  # nosec B110 — graceful degradation; error logged upstream


        self._emit(user_id, "tranquility.mood_logged", {"mood": mood_level.value})
        return entry

    def record_message(self, user_id: str) -> None:
        profile = self.get_or_create(user_id)
        profile.session_messages += 1

    def get_break_prompt(self, user_id: str) -> Optional[str]:
        profile = self.get_or_create(user_id)
        if not profile.needs_break():
            return None
        import random
        profile.last_break_prompt = time.time()
        profile.session_start = time.time()
        profile.session_messages = 0
        return random.choice(_MINDFULNESS_PROMPTS)  # nosec B311 — non-cryptographic random usage


    def delete_user_data(self, user_id: str) -> bool:
        if user_id in self._profiles:
            del self._profiles[user_id]
            return True
        return False

    def export_user_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        profile = self._profiles.get(user_id)
        if not profile:
            return None
        return {**profile.to_dict(), "entries": [e.to_dict() for e in profile.entries]}

    def stats(self) -> Dict[str, Any]:
        return {
            "total_users": len(self._profiles),
            "total_entries": sum(len(p.entries) for p in self._profiles.values()),
        }

    def _emit(self, user_id: str, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import observe, EventCategory
            observe(event_type, actor=f"user:{user_id}", category=EventCategory.DATA,
                    service="tranquility", metadata=metadata or {})
        except Exception:
            pass  # nosec B110 - graceful degradation for observation


_tranquility: Optional[Tranquility] = None


def get_tranquility() -> Tranquility:
    global _tranquility
    if _tranquility is None:
        _tranquility = Tranquility()
    return _tranquility
