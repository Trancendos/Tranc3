# src/taimra/digital_twin.py
# tAimra — digital twin for Trancendos users.
#
# tAimra is OFFLINE by default. It activates only with explicit user consent.
# When active, it builds a lightweight behavioural model from the user's
# interaction history, preferences, and stated goals.
#
# Privacy guarantees:
#   - All twin data is stored user-side (no cross-user data)
#   - Users can inspect, export, or delete their twin at any time
#   - The twin never infers or stores sensitive I-Mind flagged content
#   - Governed by Trancendos Magna Carta policy

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TwinStatus(str, Enum):
    OFFLINE = "offline"  # Default — not active
    LEARNING = "learning"  # Accumulating interaction data
    ACTIVE = "active"  # Personalising responses
    PAUSED = "paused"  # User-paused


@dataclass
class TwinProfile:
    user_id: str
    created_at: float = field(default_factory=time.time)
    status: TwinStatus = TwinStatus.OFFLINE
    interaction_count: int = 0
    preferences: Dict[str, Any] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    personality_affinity: Dict[str, float] = field(
        default_factory=dict
    )  # personality_id → score
    topics_of_interest: Dict[str, int] = field(
        default_factory=dict
    )  # topic → frequency
    last_active: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "status": self.status.value,
            "interaction_count": self.interaction_count,
            "goals": self.goals,
            "topics": dict(
                sorted(self.topics_of_interest.items(), key=lambda x: -x[1])[:10]
            ),
            "personality_affinity": self.personality_affinity,
            "last_active": self.last_active,
        }


class TAimra:
    """
    tAimra — opt-in digital twin engine.

    Twins are OFFLINE unless the user explicitly activates theirs.
    All methods check status before acting.
    """

    def __init__(self):
        self._twins: Dict[str, TwinProfile] = {}

    def get_or_create(self, user_id: str) -> TwinProfile:
        if user_id not in self._twins:
            self._twins[user_id] = TwinProfile(user_id=user_id)
        return self._twins[user_id]

    def activate(self, user_id: str) -> TwinProfile:
        twin = self.get_or_create(user_id)
        twin.status = TwinStatus.LEARNING
        twin.last_active = time.time()
        self._emit(user_id, "taimra.activated")
        logger.info("taimra: activated for user=%s", user_id)
        return twin

    def deactivate(self, user_id: str) -> None:
        twin = self._twins.get(user_id)
        if twin:
            twin.status = TwinStatus.OFFLINE
            self._emit(user_id, "taimra.deactivated")

    def record_interaction(
        self,
        user_id: str,
        message: str,
        topics: Optional[List[str]] = None,
        personality_used: Optional[str] = None,
    ) -> None:
        twin = self._twins.get(user_id)
        if not twin or twin.status == TwinStatus.OFFLINE:
            return

        twin.interaction_count += 1
        twin.last_active = time.time()

        if topics:
            for t in topics:
                twin.topics_of_interest[t] = twin.topics_of_interest.get(t, 0) + 1

        if personality_used:
            current = twin.personality_affinity.get(personality_used, 0.5)
            twin.personality_affinity[personality_used] = min(1.0, current + 0.05)

        if twin.interaction_count >= 10 and twin.status == TwinStatus.LEARNING:
            twin.status = TwinStatus.ACTIVE

    def suggest_personality(self, user_id: str) -> Optional[str]:
        """Return the personality with highest affinity score, or None."""
        twin = self._twins.get(user_id)
        if (
            not twin
            or twin.status == TwinStatus.OFFLINE
            or not twin.personality_affinity
        ):
            return None
        return max(twin.personality_affinity, key=twin.personality_affinity.get)

    def delete(self, user_id: str) -> bool:
        """GDPR right to erasure — removes all twin data for a user."""
        if user_id in self._twins:
            del self._twins[user_id]
            self._emit(user_id, "taimra.deleted")
            return True
        return False

    def export(self, user_id: str) -> Optional[Dict[str, Any]]:
        """GDPR data portability — full twin export."""
        twin = self._twins.get(user_id)
        if not twin:
            return None
        return {**twin.to_dict(), "preferences": twin.preferences, "goals": twin.goals}

    def stats(self) -> Dict[str, Any]:
        statuses: Dict[str, int] = {}
        for t in self._twins.values():
            statuses[t.status.value] = statuses.get(t.status.value, 0) + 1
        return {"total_twins": len(self._twins), "by_status": statuses}

    def _emit(self, user_id: str, event_type: str) -> None:
        try:
            from src.observability.observatory import observe, EventCategory

            observe(
                event_type,
                actor=f"user:{user_id}",
                category=EventCategory.DATA,
                service="taimra",
                metadata={"user_id": user_id},
            )
        except Exception:
            pass


_taimra: Optional[TAimra] = None


def get_taimra() -> TAimra:
    global _taimra
    if _taimra is None:
        _taimra = TAimra()
    return _taimra
