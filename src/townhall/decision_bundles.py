"""Versioned, server-owned policy bundles for non-authorising decision previews.

Bundle selection is a server-side contract: a caller cannot drop mandatory
controls by passing a convenient subset of policy IDs. This module validates
only the *shape* of submitted data; it cannot attest that evidence is genuine.
The Town Hall's durable lifecycle gate owns actual release authorisation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class DecisionIntent(str, Enum):
    CHANGE = "change"
    RELEASE = "release"


@dataclass(frozen=True)
class PolicyBundle:
    intent: DecisionIntent
    policy_ids: tuple[str, ...]
    required_fields: tuple[str, ...]
    version: int = 1


_REQUIRED = ("monthly_cost_usd", "personal_data", "cross_border_transfer")
_BUNDLES: Mapping[DecisionIntent, PolicyBundle] = MappingProxyType(
    {
        DecisionIntent.CHANGE: PolicyBundle(
            DecisionIntent.CHANGE, ("zero-cost", "gdpr"), _REQUIRED
        ),
        # PRINCE2 currently has no executable evaluator, so release previews
        # fail closed until there is real, verifiable stage-gate evidence.
        DecisionIntent.RELEASE: PolicyBundle(
            DecisionIntent.RELEASE,
            ("zero-cost", "gdpr", "prince2"),
            _REQUIRED + ("build_evidence_id", "test_evidence_id"),
        ),
    }
)


def get_bundle(intent: DecisionIntent | str) -> PolicyBundle:
    """Resolve mandatory controls from a trusted local table, not user IDs."""
    try:
        return _BUNDLES[DecisionIntent(intent)]
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("unsupported Townhall decision intent") from exc


def validate_context(intent: DecisionIntent | str, context: Mapping[str, Any]) -> tuple[str, ...]:
    """Report deterministic input deficiencies; never fill in favourable defaults.

    Evidence identifiers are only syntax checks. Even a valid preview is not
    proof of compliance, human approval or authority to deploy anything.
    """
    bundle = get_bundle(intent)
    problems: list[str] = []
    for key in bundle.required_fields:
        if key not in context:
            problems.append(f"{key}:required")
            continue
        value = context[key]
        if key == "monthly_cost_usd":
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and (not isinstance(value, float) or math.isfinite(value))
                and value >= 0
            )
        elif key in ("personal_data", "cross_border_transfer"):
            valid = isinstance(value, bool)
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            problems.append(f"{key}:invalid")

    if context.get("personal_data") is True:
        if "lawful_basis" not in context:
            problems.append("lawful_basis:required")
        elif not isinstance(context["lawful_basis"], str) or not context["lawful_basis"].strip():
            problems.append("lawful_basis:invalid")
    if context.get("cross_border_transfer") is True:
        if "adequacy_decision" not in context:
            problems.append("adequacy_decision:required")
        elif not isinstance(context["adequacy_decision"], bool):
            problems.append("adequacy_decision:invalid")

    return tuple(problems)
