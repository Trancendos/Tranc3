"""Mock-only builder for an opt-in YCloud queued template notification.

No network client, provider API key, customer data reads or send capability.
Operator-owned provider submission must be implemented/reviewed separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from src.security.ice_box.automation_policy import AutomationPlan

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")
_TEMPLATE = re.compile(r"^[a-z0-9_]{1,128}$")
_CORRELATION = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_LANGUAGE = re.compile(r"^[a-z]{2,3}(?:_[A-Z]{2})?$")


class AlertNotAuthorised(ValueError):
    """The application is not configured/approved to prepare an external alert."""


@dataclass(frozen=True)
class YCloudAlertConfig:
    enabled: bool = False
    recipient_opted_in: bool = False
    template_approved: bool = False
    sender_e164: str = ""
    recipient_e164: str = ""
    template_name: str = ""
    language_code: str = "en_GB"


def prepare_queued_template(
    plan: AutomationPlan, config: YCloudAlertConfig, correlation_id: str
) -> Mapping[str, object]:
    """Build a non-executing queued request shape for a static approved template.

    The template must have NO dynamic variables/media. Incident details remain
    in an authenticated internal console; no evidence or case ID enters WhatsApp.
    """
    if not (config.enabled and config.recipient_opted_in and config.template_approved):
        raise AlertNotAuthorised("external channel not enabled and fully approved")
    if plan.priority != "urgent" or not plan.review_required:
        raise AlertNotAuthorised("notification is limited to urgent human-review events")
    if not all(
        (
            _E164.fullmatch(config.sender_e164),
            _E164.fullmatch(config.recipient_e164),
            _TEMPLATE.fullmatch(config.template_name),
            _LANGUAGE.fullmatch(config.language_code),
            _CORRELATION.fullmatch(correlation_id),
        )
    ):
        raise AlertNotAuthorised("invalid provider alert configuration")
    return {
        "from": config.sender_e164,
        "to": config.recipient_e164,
        "type": "template",
        "template": {
            "name": config.template_name,
            "language": {"code": config.language_code},
        },
        "filterBlocked": True,
        "filterUnsubscribed": True,
        "externalId": correlation_id,
    }
