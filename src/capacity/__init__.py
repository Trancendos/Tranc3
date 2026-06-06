"""Capacity guard — hard stops at 80/90/95/100% utilisation for all external services."""

from .guard import (
    THRESHOLD_ALERT,
    THRESHOLD_CRITICAL,
    THRESHOLD_HARD,
    THRESHOLD_WARN,
    CapacityExceededError,
    CapacityGuard,
    CapacityService,
    ServiceLimit,
    get_capacity_guard,
)

__all__ = [
    "THRESHOLD_ALERT",
    "THRESHOLD_CRITICAL",
    "THRESHOLD_HARD",
    "THRESHOLD_WARN",
    "CapacityExceededError",
    "CapacityGuard",
    "CapacityService",
    "ServiceLimit",
    "get_capacity_guard",
]
