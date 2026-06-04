# src/vrar3d/wellbeing_centre.py
# VRAR3D — AR/VR wellbeing centre for Trancendos.
#
# VRAR3D provides immersive wellbeing experiences:
#   - Guided meditation scenes (Three.js / A-Frame WebXR)
#   - Breathing exercises in 3D space
#   - Nature immersion environments (forest, ocean, mountains)
#   - Integration with Tranquility (mood + break prompts trigger scenes)
#   - Integration with Resonate (crisis support via calming environments)
#
# Foundation: Three.js + A-Frame for WebXR (browser-based, zero native install).
# Scenes are JSON descriptors rendered client-side.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SceneType(str, Enum):
    MEDITATION = "meditation"
    BREATHING = "breathing"
    NATURE = "nature"
    FOCUS = "focus"
    SLEEP = "sleep"
    CRISIS_CALM = "crisis_calm"  # Reserved for I-Mind CRITICAL escalation


class SceneStatus(str, Enum):
    AVAILABLE = "available"
    ACTIVE = "active"  # User currently in session
    DEPRECATED = "deprecated"


@dataclass
class WellbeingScene:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    scene_type: SceneType = SceneType.MEDITATION
    description: str = ""
    duration_seconds: int = 300
    status: SceneStatus = SceneStatus.AVAILABLE
    aframe_url: Optional[str] = None  # Path to A-Frame scene HTML
    thumbnail_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.scene_type.value,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "aframe_url": self.aframe_url,
            "tags": self.tags,
        }


@dataclass
class VRSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    scene_id: str = ""
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    mood_before: Optional[int] = None
    mood_after: Optional[int] = None
    completed: bool = False

    @property
    def duration_seconds(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "scene_id": self.scene_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "mood_before": self.mood_before,
            "mood_after": self.mood_after,
            "completed": self.completed,
        }


_DEFAULT_SCENES = [
    (
        "Forest Sanctuary",
        SceneType.NATURE,
        "A peaceful forest glade with birdsong and dappled light.",
        600,
        ["nature", "calming"],
    ),
    (
        "Ocean Horizon",
        SceneType.NATURE,
        "Gently rolling waves at sunrise — feel the rhythm.",
        600,
        ["nature", "sleep"],
    ),
    (
        "Breathing Space",
        SceneType.BREATHING,
        "4-7-8 breathing guide in a soft geometric space.",
        300,
        ["breathing", "anxiety"],
    ),
    (
        "Mountain Stillness",
        SceneType.MEDITATION,
        "High-altitude stillness — clear sky, no distraction.",
        900,
        ["meditation", "focus"],
    ),
    (
        "Focus Chamber",
        SceneType.FOCUS,
        "Minimal environment with Pomodoro timer integration.",
        1500,
        ["focus", "productivity"],
    ),
    (
        "Crisis Calm",
        SceneType.CRISIS_CALM,
        "A safe, warm space — gentle light, supportive presence.",
        300,
        ["crisis", "safety"],
    ),
]


class VRAR3D:
    """VRAR3D — AR/VR wellbeing centre."""

    def __init__(self):
        self._scenes: Dict[str, WellbeingScene] = {}
        self._sessions: Dict[str, VRSession] = {}
        self._seed_scenes()

    def _seed_scenes(self) -> None:
        for name, stype, desc, dur, tags in _DEFAULT_SCENES:
            scene = WellbeingScene(
                name=name, scene_type=stype, description=desc, duration_seconds=dur, tags=tags,
            )
            self._scenes[scene.id] = scene

    def list_scenes(self, scene_type: Optional[SceneType] = None) -> List[WellbeingScene]:
        scenes = [s for s in self._scenes.values() if s.status != SceneStatus.DEPRECATED]
        if scene_type:
            scenes = [s for s in scenes if s.scene_type == scene_type]
        return sorted(scenes, key=lambda s: s.name)

    def get_scene(self, scene_id: str) -> Optional[WellbeingScene]:
        return self._scenes.get(scene_id)

    def start_session(
        self, user_id: str, scene_id: str, mood_before: Optional[int] = None,
    ) -> Optional[VRSession]:
        if scene_id not in self._scenes:
            return None
        session = VRSession(user_id=user_id, scene_id=scene_id, mood_before=mood_before)
        self._sessions[session.id] = session
        self._emit("vrar3d.session.started", {"user_id": user_id, "scene_id": scene_id})
        return session

    def end_session(self, session_id: str, mood_after: Optional[int] = None) -> Optional[VRSession]:
        session = self._sessions.get(session_id)
        if not session or session.ended_at:
            return None
        session.ended_at = time.time()
        session.completed = True
        session.mood_after = mood_after
        self._emit(
            "vrar3d.session.completed",
            {
                "user_id": session.user_id,
                "scene_id": session.scene_id,
                "duration_seconds": round(session.duration_seconds, 1),
            },
        )
        return session

    def recommend_scene(
        self, mood: Optional[int] = None, sensitivity_level: str = "none",
    ) -> Optional[WellbeingScene]:
        """Recommend a scene based on mood or I-Mind sensitivity level."""
        if sensitivity_level == "critical":
            for s in self._scenes.values():
                if s.scene_type == SceneType.CRISIS_CALM:
                    return s
        if mood is not None and mood <= 2:
            candidates = [s for s in self._scenes.values() if SceneType.NATURE == s.scene_type]
            return candidates[0] if candidates else None
        # Default: breathing
        for s in self._scenes.values():
            if s.scene_type == SceneType.BREATHING:
                return s
        return None

    def stats(self) -> Dict[str, Any]:
        return {
            "service": "vrar3d",
            "total_scenes": len(self._scenes),
            "total_sessions": len(self._sessions),
            "completed_sessions": sum(1 for s in self._sessions.values() if s.completed),
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                event_type, category=EventCategory.DATA, service="vrar3d", metadata=metadata or {},
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


_vrar3d: Optional[VRAR3D] = None


def get_vrar3d() -> VRAR3D:
    global _vrar3d
    if _vrar3d is None:
        _vrar3d = VRAR3D()
    return _vrar3d
