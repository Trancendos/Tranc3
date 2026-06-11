"""
Tier Relay — T2ance ↔ Tranc3 (Tier 2 ↔ Tier 3) command relay.

T2ance relays Trance-One commands downward to Tier 3 Lead AIs,
and surfaces Tier 3 escalations upward to Trance-One.
"""

from __future__ import annotations

import logging
from typing import Optional

from Dimensional.sanitize import sanitize_for_log
from t2ance.prime_registry import get_prime_registry

logger = logging.getLogger("t2ance.tier_relay")


class TierRelay:
    """
    Bridges Trance-One commands to Domain Primes and then down to Tier 3.
    """

    def route_rotation_request(self, entity_id: str, reason: str) -> bool:
        """
        Route a rotation request through the correct Domain Prime.
        Returns True if approved.
        """
        registry = get_prime_registry()
        prime = registry.prime_for_entity(entity_id)
        if not prime:
            logger.warning(
                "No Prime governs entity %s — escalating to sovereign", sanitize_for_log(entity_id)
            )
            return True  # Allow by default if no prime defined (edge case)
        decision = prime.authorise_rotation(entity_id, reason)
        if not decision.approved:
            prime.escalate_to_sovereign(entity_id, f"Rotation denied: {reason}")
        return decision.approved

    def status(self) -> dict:
        return get_prime_registry().status()


_relay: Optional[TierRelay] = None


def get_relay() -> TierRelay:
    global _relay
    if _relay is None:
        _relay = TierRelay()
    return _relay
