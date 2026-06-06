"""
Domain Authority — T2ance Prime Level
=======================================
Each DomainPrime governs one or more Pillars of the platform and acts as
the executive authority between Trance-One (Tier 1) and the Tier 3 Lead AIs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("t2ance.domain_authority")


class PrimeDomain(str, Enum):
    ARCHITECTURAL = "ArchPrime"
    COMMERCIAL = "CommPrime"
    CREATIVE = "CreatePrime"
    DEVELOPMENT = "DevPrime"
    KNOWLEDGE = "KnowPrime"
    SECURITY = "SecPrime"
    WELLBEING = "WellPrime"
    GOVERNANCE = "GovPrime"
    OPERATIONS = "OpsPrime"


# Mapping: domain → entity IDs it governs
DOMAIN_ENTITY_MAP: Dict[PrimeDomain, List[str]] = {
    PrimeDomain.ARCHITECTURAL: [
        "the-spark", "the-digital-grid", "the-hive", "the-nexus",
        "infinity", "luminous",
    ],
    PrimeDomain.COMMERCIAL: [
        "royal-bank-of-arcadia", "arcadian-exchange", "chronossphere",
    ],
    PrimeDomain.CREATIVE: [
        "the-studio", "sashas-photo-studio", "tranceflow", "tateking",
        "fabulousa", "imaginarium", "warp-radio", "vrar3d",
    ],
    PrimeDomain.DEVELOPMENT: [
        "the-workshop", "the-lab", "think-tank", "the-artifactory",
        "api-marketplace", "devocity", "the-chaos-party",
    ],
    PrimeDomain.KNOWLEDGE: [
        "the-library", "the-academy", "docutari", "the-basement",
        "turings-hub", "section-7",
    ],
    PrimeDomain.SECURITY: [
        "cryptex", "the-void", "the-lighthouse", "the-ice-box",
        "the-warp-tunnel",
    ],
    PrimeDomain.WELLBEING: [
        "tranquility", "imind", "resonate", "taimra",
    ],
    PrimeDomain.GOVERNANCE: [
        "the-town-hall", "arcadia",
    ],
    PrimeDomain.OPERATIONS: [
        "the-citadel", "the-observatory",
    ],
}


@dataclass
class PrimeDecision:
    domain: PrimeDomain
    decision_type: str
    target_entity: Optional[str]
    rationale: str
    approved: bool
    decided_at: float = field(default_factory=time.time)


class DomainPrime:
    """
    Executive authority for one platform domain.
    Escalates to Trance-One when cross-domain resolution is needed.
    """

    def __init__(self, domain: PrimeDomain) -> None:
        self.domain = domain
        self.entities: List[str] = DOMAIN_ENTITY_MAP.get(domain, [])
        self._decisions: List[PrimeDecision] = []
        logger.info("T2ance Prime initialised: %s (%d entities)", domain.value, len(self.entities))

    def authorise_rotation(self, entity_id: str, reason: str) -> PrimeDecision:
        """Approve or deny an entity rotation request from Tier 3."""
        approved = entity_id in self.entities
        decision = PrimeDecision(
            domain=self.domain,
            decision_type="ROTATION",
            target_entity=entity_id,
            rationale=reason if approved else f"Entity {entity_id} not under {self.domain.value} authority",
            approved=approved,
        )
        self._decisions.append(decision)
        if approved:
            logger.info("%s approved rotation for %s: %s", self.domain.value, entity_id, reason)
        else:
            logger.warning("%s denied rotation for %s (out of domain)", self.domain.value, entity_id)
        return decision

    def escalate_to_sovereign(self, entity_id: str, issue: str) -> None:
        """Escalate unresolvable issue to Trance-One."""
        logger.warning(
            "%s escalating %s to Trance-One: %s",
            self.domain.value, entity_id, issue,
        )
        try:
            from trance_one.tier_bridge import TierEvent, get_tier_bridge
            get_tier_bridge().surface_event(TierEvent(
                source_tier=2,
                source_entity=entity_id,
                event_type="PRIME_ESCALATION",
                payload={"domain": self.domain.value, "issue": issue},
            ))
        except ImportError:
            pass

    def status(self) -> dict:
        return {
            "domain": self.domain.value,
            "entities_governed": self.entities,
            "decisions_made": len(self._decisions),
            "recent_decisions": [
                {
                    "type": d.decision_type,
                    "entity": d.target_entity,
                    "approved": d.approved,
                    "at": d.decided_at,
                }
                for d in self._decisions[-10:]
            ],
        }
