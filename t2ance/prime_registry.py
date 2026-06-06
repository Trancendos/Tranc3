"""
Prime Registry — T2ance Tier 2
================================
Registry of all Domain Primes. Single point of access for resolving
which Prime governs a given entity or pillar.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from t2ance.domain_authority import DOMAIN_ENTITY_MAP, DomainPrime, PrimeDomain

logger = logging.getLogger("t2ance.prime_registry")


class PrimeRegistry:
    """
    Registry of all 9 T2ance Domain Primes.
    Resolves entity → governing Prime lookups.
    """

    def __init__(self) -> None:
        self._primes: Dict[PrimeDomain, DomainPrime] = {
            domain: DomainPrime(domain) for domain in PrimeDomain
        }
        self._entity_to_domain: Dict[str, PrimeDomain] = {
            entity_id: domain
            for domain, entities in DOMAIN_ENTITY_MAP.items()
            for entity_id in entities
        }
        logger.info(
            "T2ance Prime Registry: %d primes, %d entities mapped",
            len(self._primes),
            len(self._entity_to_domain),
        )

    def get_prime(self, domain: PrimeDomain) -> DomainPrime:
        return self._primes[domain]

    def prime_for_entity(self, entity_id: str) -> Optional[DomainPrime]:
        domain = self._entity_to_domain.get(entity_id)
        return self._primes.get(domain) if domain else None

    def all_primes(self) -> List[DomainPrime]:
        return list(self._primes.values())

    def status(self) -> dict:
        return {
            "tier": 2,
            "label": "T2ance",
            "total_primes": len(self._primes),
            "total_entities_mapped": len(self._entity_to_domain),
            "primes": [p.status() for p in self._primes.values()],
        }


_registry: Optional[PrimeRegistry] = None


def get_prime_registry() -> PrimeRegistry:
    global _registry
    if _registry is None:
        _registry = PrimeRegistry()
    return _registry
