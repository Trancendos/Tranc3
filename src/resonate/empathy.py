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
import os
from typing import Any, Dict, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://notifications:8008").rstrip("/")
_INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
# If set, escalations are dispatched as a real outbound webhook (e.g. to a
# support team's Slack/PagerDuty/Ops-Genie inbox) via the notifications
# worker's webhook channel — the only channel in that worker with genuine
# pass/fail delivery semantics. Every other channel there (email/sms/push/
# in_app) is a zero-cost logging stub that always reports success, so it
# cannot be used to justify telling a user "a human was notified."
_ESCALATION_WEBHOOK_URL = os.getenv("RESONATE_ESCALATION_WEBHOOK_URL", "")

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
            parts.append(random.choice(_EMPATHY_PREFIXES))  # nosec B311 — non-cryptographic random usage

        elif sensitivity_level == "medium" or (user_mood is not None and user_mood <= 2):
            parts.append(random.choice(_EMPATHY_PREFIXES[:2]))  # nosec B311 — non-cryptographic empathy variation

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
            parts.append(f"\n\n*{random.choice(_VALIDATION_PHRASES)}*")  # nosec B311 — non-cryptographic phrase variation

        return "\n\n".join(p.strip() for p in parts if p.strip())

    async def escalate_to_human(self, user_id: str, context: str) -> Dict[str, Any]:
        """
        Flag for human support escalation. Emits an Observatory SECURITY event
        (always) and attempts a real dispatch through the notifications worker
        (best-effort). The returned message reflects what actually happened —
        it must never claim a human was notified unless dispatch genuinely
        succeeded, since this path is reached from crisis-support contexts.
        """
        try:
            from src.observability.observatory import EventCategory, EventSeverity, observe

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
            pass  # nosec B110 — observation failure must not block escalation
        logger.warning(
            "resonate: human escalation triggered for user=%s", sanitize_for_log(user_id)
        )  # codeql[py/cleartext-logging]

        dispatched = await self._dispatch_notification(user_id, context)

        if dispatched:
            return {
                "escalated": True,
                "message": (
                    "Your message has been flagged for urgent review by the support team. "
                    "You are not alone."
                ),
            }
        return {
            "escalated": True,
            "message": (
                "Your message has been logged and flagged internally, but we could not "
                "confirm live delivery to a support team member right now. If you are in "
                "immediate danger, please contact emergency services or a crisis line "
                "directly — see the resources below."
            ),
            "notification_dispatched": False,
        }

    async def _dispatch_notification(self, user_id: str, context: str) -> bool:
        """Best-effort real dispatch via the notifications worker. Never raises.

        Only returns True if a `RESONATE_ESCALATION_WEBHOOK_URL` is configured
        and the notifications worker's webhook channel confirms genuine
        delivery (`{"ok": true}` in the response body — this endpoint always
        returns HTTP 200 even on failure, so the status code alone can't be
        trusted). Without a configured webhook target there is no channel
        available that provides a real delivery guarantee, so this always
        returns False in that case rather than reporting a false positive.
        """
        if not _ESCALATION_WEBHOOK_URL:
            logger.warning(
                "resonate: no RESONATE_ESCALATION_WEBHOOK_URL configured — "
                "escalation cannot be confirmed delivered to a human"
            )
            return False
        try:
            import httpx

            headers = {"X-Internal-Secret": _INTERNAL_SECRET} if _INTERNAL_SECRET else {}
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
                resp = await client.post(
                    f"{NOTIFICATIONS_URL}/notifications/send",
                    json={
                        "user_id": user_id,
                        "channel": "webhook",
                        "priority": "urgent",
                        "subject": "Resonate human escalation",
                        "body": context[:500],
                        "metadata": {
                            "source": "resonate",
                            "user_id": user_id,
                            "webhook_url": _ESCALATION_WEBHOOK_URL,
                        },
                    },
                    headers=headers,
                )
                return bool(resp.json().get("ok", False))
        except Exception as exc:
            logger.warning("resonate: notification dispatch failed: %s", exc)
            return False

    def stats(self) -> Dict[str, Any]:
        return {"service": "resonate", "status": "active"}


_resonate: Optional[Resonate] = None


def get_resonate() -> Resonate:
    global _resonate
    if _resonate is None:
        _resonate = Resonate()
    return _resonate
