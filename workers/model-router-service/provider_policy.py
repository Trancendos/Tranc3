"""Luminous model-routing admission policy.

Integration point: call admit() before any provider execution.
No implicit provider, paid-tier, data-classification or external-network access.
"""
from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class RoutePolicy:
    allowed_providers: FrozenSet[str]
    allowed_models: FrozenSet[str]
    allow_external: bool = False
    allow_paid: bool = False
    permitted_classifications: FrozenSet[str] = frozenset({'public'})


@dataclass(frozen=True)
class RouteCandidate:
    provider: str
    model: str
    external: bool
    advertised_free: bool
    cost_verified: bool


class PolicyDenied(ValueError):
    """Request failed provider admission policy."""


def admit(candidate: RouteCandidate, policy: RoutePolicy, *, classification: str) -> None:
    if not candidate.provider or candidate.provider not in policy.allowed_providers:
        raise PolicyDenied('provider_not_allowed')
    if not candidate.model or candidate.model not in policy.allowed_models:
        raise PolicyDenied('model_not_allowed')
    if not classification or classification not in policy.permitted_classifications:
        raise PolicyDenied('classification_not_allowed')
    if candidate.external and not policy.allow_external:
        raise PolicyDenied('external_access_not_allowed')
    if not candidate.cost_verified:
        raise PolicyDenied('pricing_not_verified')
    if not candidate.advertised_free and not policy.allow_paid:
        raise PolicyDenied('paid_usage_not_allowed')
