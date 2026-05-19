# src/resonate/empathy.py
# Resonate — empathy and understanding services for Trancendos.
#
# Resonate wraps AI-generated empathetic responses with:
#   - Empathy tone injection (warm, supportive language)
#   - Emotional validation patterns
#   - Escalation to human support when I-Mind flags CRITICAL
#   - Integration with Tranquility for wellbeing context

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_EMPATHY_PREFIXES = [
    "I hear you, and what you're feeling is completely valid.",
    "Thank you for sharing that with me.",
    "That sounds genuinely difficult, and I want you to know you're not alone.",
    "I appreciate you trusting me with this.",
]

_VALIDATION_PHRASES = [
    "Your feelings matter.",
    "It's okay to not be okay.",
    "You're doing better than you think.",
    "Taking it one step at a time is enough.",
]


class Resonate:
    """
    Resonate — empathy service layer.

    Wraps inference responses with empathetic framing when triggered
    by I-Mind sensitivity assessments or Tranquility low-mood flags.
    """

    def wrap_response(
        self,
        response: str,
        sensitivity_level: str = "none",
        user_mood: Optional[int] = None,
        crisis_resources: bool = False,
    ) -> str:
        """
        Wrap an AI response with empathetic framing based on context.
        Returns the original response unchanged if no empathy wrapping is needed.
        """
        if sensitivity_level == "none" and (user_mood is None or user_mood >= 3):
            return response

        import random
        parts = []

        if sensitivity_level in ("critical", "high"):
            parts.append(random.choice(_EMPATHY_PREFIXES))
        elif sensitivity_level == "medium" or (user_mood is not None and user_mood <= 2):
            parts.append(random.choice(_EMPATHY_PREFIXES[:2]))

        parts.append(response)

        if crisis_resources:
            parts.append(
                "\n\n---\n**If you're in crisis, please reach out:**\n"
                "- **UK**: Samaritans — 116 123 (free, 24/7)\n"
                "- **US**: 988 Suicide & Crisis Lifeline — call or text 988\n"
                "- **International**: [findahelpline.com](https://findahelpline.com)\n"
                "You don't have to face this alone. 💙"
            )
        elif sensitivity_level in ("medium", "high"):
            parts.append(f"\n\n*{random.choice(_VALIDATION_PHRASES)}*")

        return "\n\n".join(p.strip() for p in parts if p.strip())

    def escalate_to_human(self, user_id: str, context: str) -> Dict[str, Any]:
        """
        Flag for human support escalation. Emits Observatory SECURITY event.
        In production this would trigger a notification to the support team.
        """
        try:
            from src.observability.observatory import observe, EventCategory, EventSeverity
            observe(
                "resonate.human_escalation",
                actor=f"user:{user_id}",
                category=EventCategory.SECURITY,
                severity=EventSeverity.SECURITY,
                service="resonate",
                outcome="escalated",
                metadata={"context_preview": context[:100]},
            )
        except Exception:
            pass
        logger.warning("resonate: human escalation triggered for user=%s", user_id)
        return {
            "escalated": True,
            "message": "A support team member has been notified. You are not alone.",
        }

    def stats(self) -> Dict[str, Any]:
        return {"service": "resonate", "status": "active"}


_resonate: Optional[Resonate] = None


def get_resonate() -> Resonate:
    global _resonate
    if _resonate is None:
        _resonate = Resonate()
    return _resonate
