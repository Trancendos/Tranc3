# src/imind/protocol.py
# I-Mind — critical and sensitivity protocol for Trancendos.
#
# I-Mind governs how the platform handles sensitive subjects:
#   - Mental health disclosures
#   - Crisis indicators in user messages
#   - Sensitive personal data flags
#   - Escalation routing to human support
#
# All I-Mind activations are SECURITY-severity Observatory events.

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SensitivityLevel(str, Enum):
    NONE     = "none"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"   # Immediate human escalation


class SensitivityCategory(str, Enum):
    MENTAL_HEALTH  = "mental_health"
    CRISIS         = "crisis"
    SELF_HARM      = "self_harm"
    PERSONAL_DATA  = "personal_data"
    SAFEGUARDING   = "safeguarding"
    TRAUMA         = "trauma"


_CRISIS_PATTERNS = [
    re.compile(r"\b(suicide|suicidal|end my life|kill myself|want to die)\b", re.I),
    re.compile(r"\b(self[- ]harm|cut myself|hurt myself)\b", re.I),
    re.compile(r"\b(no reason to live|can't go on|give up on life)\b", re.I),
]

_MENTAL_HEALTH_PATTERNS = [
    re.compile(r"\b(depressed|depression|anxiety|anxious|panic attack|ptsd)\b", re.I),
    re.compile(r"\b(mental health|therapy|therapist|psychiatrist|medication for)\b", re.I),
]


@dataclass
class SensitivityAssessment:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    level: SensitivityLevel = SensitivityLevel.NONE
    categories: List[SensitivityCategory] = field(default_factory=list)
    escalate: bool = False
    response_modifier: str = ""   # Instruction prefix to inject into AI response
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level.value,
            "categories": [c.value for c in self.categories],
            "escalate": self.escalate,
            "response_modifier": self.response_modifier,
        }


class IMind:
    """
    I-Mind — sensitivity and crisis protocol engine.

    Scans all user messages before inference. Returns an assessment
    that modifiers the AI response and triggers escalation where needed.
    """

    def assess(self, text: str, actor: Optional[str] = None) -> SensitivityAssessment:
        categories: List[SensitivityCategory] = []
        level = SensitivityLevel.NONE

        # Crisis detection — highest priority
        for pat in _CRISIS_PATTERNS:
            if pat.search(text):
                categories.append(SensitivityCategory.CRISIS)
                level = SensitivityLevel.CRITICAL
                break

        # Self-harm
        if SensitivityCategory.CRISIS not in categories:
            for pat in _CRISIS_PATTERNS[1:]:
                if pat.search(text):
                    categories.append(SensitivityCategory.SELF_HARM)
                    if level.value < SensitivityLevel.HIGH.value:
                        level = SensitivityLevel.HIGH
                    break

        # Mental health
        for pat in _MENTAL_HEALTH_PATTERNS:
            if pat.search(text):
                if SensitivityCategory.MENTAL_HEALTH not in categories:
                    categories.append(SensitivityCategory.MENTAL_HEALTH)
                if level == SensitivityLevel.NONE:
                    level = SensitivityLevel.MEDIUM
                break

        escalate = level in (SensitivityLevel.CRITICAL, SensitivityLevel.HIGH)

        modifier = ""
        if level == SensitivityLevel.CRITICAL:
            modifier = (
                "IMPORTANT: The user may be in crisis. Respond with empathy, "
                "provide crisis helpline numbers (UK: 116 123 Samaritans, "
                "US: 988 Suicide & Crisis Lifeline), and encourage professional help. "
                "Do not minimise their feelings."
            )
        elif level == SensitivityLevel.HIGH:
            modifier = (
                "The user has mentioned self-harm. Respond with care and empathy. "
                "Provide mental health resources. Do not provide harmful information."
            )
        elif level == SensitivityLevel.MEDIUM:
            modifier = (
                "The user has mentioned mental health topics. "
                "Respond with warmth and empathy. Suggest professional support if appropriate."
            )

        assessment = SensitivityAssessment(
            level=level,
            categories=categories,
            escalate=escalate,
            response_modifier=modifier,
            metadata={"actor": actor},
        )

        if level != SensitivityLevel.NONE:
            self._emit(assessment, actor)

        return assessment

    def _emit(self, assessment: SensitivityAssessment, actor: Optional[str]) -> None:
        try:
            from src.observability.observatory import observe, EventCategory, EventSeverity
            observe(
                f"imind.sensitivity.{assessment.level.value}",
                actor=actor,
                category=EventCategory.SECURITY,
                severity=EventSeverity.SECURITY if assessment.escalate else EventSeverity.WARNING,
                service="imind",
                outcome="assessed",
                metadata=assessment.to_dict(),
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream



_imind: Optional[IMind] = None


def get_imind() -> IMind:
    global _imind
    if _imind is None:
        _imind = IMind()
    return _imind
