"""Fail-safe, deterministic IceBox triage policy.

No payload bytes, findings text, credentials, personal data or external calls.
This is policy advice, not an execution or release authorization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Disposition = Literal["allow_static", "hold_for_review", "isolate_and_review"]
NotificationPriority = Literal["none", "review", "urgent"]


@dataclass(frozen=True)
class AutomationPlan:
    disposition: Disposition
    review_required: bool
    priority: NotificationPriority
    allow_automatic_release: bool = False
    dynamic_execution_enabled: bool = False

    def as_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def plan_scan(verdict: str, *, quarantined: bool) -> AutomationPlan:
    """Conservative next-action hint; no I/O or side effects.

    Unknown verdicts must not be interpreted as clean. A quarantine
    record can never be automatically released after a later clean scan.
    """
    if not isinstance(verdict, str) or type(quarantined) is not bool:
        raise TypeError("verdict must be str and quarantined must be bool")
    normalized = verdict.casefold()
    if normalized == "clean" and not quarantined:
        return AutomationPlan("allow_static", False, "none")
    if normalized in ("malicious", "quarantined"):
        return AutomationPlan("isolate_and_review", True, "urgent")
    return AutomationPlan("hold_for_review", True, "review")
