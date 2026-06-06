"""
Section 7 — Information Router
================================
Classifies and routes intelligence items to the appropriate platform services.

Every item flows through The Observatory FIRST for audit logging.
After Observatory records the event, the item is dispatched to its target hub.

Classification → Destination mapping:
  THREAT        → Cryptex (cyber defence analysis)
  RESEARCH      → Think Tank (R&D, advancement study)
  ADVANCEMENT   → Think Tank (technology advances)
  KNOWLEDGE     → The Library (knowledge base catalogue)
  WEB_SCAN      → The Library (web content catalogue)
  CVE           → Cryptex + The Library (threat record + CVE catalogue)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("section7.router")


class IntelligenceClass(str, Enum):
    """Classification of an intelligence item."""

    THREAT = "threat"
    CVE = "cve"
    RESEARCH = "research"
    ADVANCEMENT = "advancement"
    KNOWLEDGE = "knowledge"
    WEB_SCAN = "web_scan"
    UNKNOWN = "unknown"


@dataclass
class RoutingResult:
    """Outcome of routing one intelligence item."""

    item_id: str
    classification: IntelligenceClass
    observatory_recorded: bool = False
    cryptex_dispatched: bool = False
    library_catalogued: bool = False
    think_tank_dispatched: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.observatory_recorded and not self.errors


class InformationRouter:
    """
    Routes intelligence items from Section 7 to their platform destinations.

    The Observatory is ALWAYS the first destination — every item is logged
    before any further distribution. This guarantees a complete audit trail.
    """

    def __init__(self) -> None:
        self._routed: List[RoutingResult] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def route(
        self,
        item_id: str,
        classification: IntelligenceClass,
        summary: str,
        payload: Dict[str, Any],
        source: str = "section7",
    ) -> RoutingResult:
        """Route a single intelligence item through the platform."""
        result = RoutingResult(item_id=item_id, classification=classification)

        # Step 1: Observatory — audit log (unconditional)
        result.observatory_recorded = self._record_in_observatory(
            item_id=item_id,
            classification=classification,
            summary=summary,
            payload=payload,
            source=source,
        )

        # Step 2: Dispatch to domain-specific hub
        if classification in (IntelligenceClass.THREAT, IntelligenceClass.CVE):
            result.cryptex_dispatched = self._dispatch_to_cryptex(
                item_id=item_id,
                classification=classification,
                summary=summary,
                payload=payload,
            )
            # CVEs are also catalogued in The Library
            if classification == IntelligenceClass.CVE:
                result.library_catalogued = self._catalogue_in_library(
                    item_id=item_id,
                    classification=classification,
                    summary=summary,
                    payload=payload,
                    source=source,
                )

        elif classification in (IntelligenceClass.RESEARCH, IntelligenceClass.ADVANCEMENT):
            result.think_tank_dispatched = self._dispatch_to_think_tank(
                item_id=item_id,
                classification=classification,
                summary=summary,
                payload=payload,
            )
            # Advancements are also catalogued
            result.library_catalogued = self._catalogue_in_library(
                item_id=item_id,
                classification=classification,
                summary=summary,
                payload=payload,
                source=source,
            )

        elif classification in (IntelligenceClass.KNOWLEDGE, IntelligenceClass.WEB_SCAN):
            result.library_catalogued = self._catalogue_in_library(
                item_id=item_id,
                classification=classification,
                summary=summary,
                payload=payload,
                source=source,
            )

        self._routed.append(result)
        return result

    def route_many(
        self,
        items: List[Dict[str, Any]],
    ) -> List[RoutingResult]:
        """Route multiple intelligence items."""
        return [
            self.route(
                item_id=item["id"],
                classification=IntelligenceClass(item.get("classification", "unknown")),
                summary=item.get("summary", ""),
                payload=item.get("payload", {}),
                source=item.get("source", "section7"),
            )
            for item in items
        ]

    def stats(self) -> Dict[str, Any]:
        total = len(self._routed)
        by_class: Dict[str, int] = {}
        successes = 0
        for r in self._routed:
            by_class[r.classification.value] = by_class.get(r.classification.value, 0) + 1
            if r.success:
                successes += 1
        return {
            "total_routed": total,
            "successes": successes,
            "failures": total - successes,
            "by_classification": by_class,
        }

    # ── Destination adapters ──────────────────────────────────────────────────

    def _record_in_observatory(
        self,
        item_id: str,
        classification: IntelligenceClass,
        summary: str,
        payload: Dict[str, Any],
        source: str,
    ) -> bool:
        """Always log to The Observatory first."""
        try:
            from src.observability.observatory import EventCategory, EventSeverity, observe

            severity = (
                EventSeverity.WARNING
                if classification in (IntelligenceClass.THREAT, IntelligenceClass.CVE)
                else EventSeverity.INFO
            )
            observe(
                f"section7.intelligence.{classification.value}",
                actor=source,
                target="observatory",
                category=EventCategory.SYSTEM,
                severity=severity,
                service="section7",
                outcome="received",
                metadata={
                    "item_id": item_id,
                    "classification": classification.value,
                    "summary": summary[:500],
                    "payload_keys": list(payload.keys()),
                },
            )
            logger.info(
                "section7: recorded %s item %s in observatory",
                classification.value,
                item_id,
            )
            return True
        except Exception as exc:
            logger.warning("section7: observatory record failed for %s: %s", item_id, exc)
            return False

    def _dispatch_to_cryptex(
        self,
        item_id: str,
        classification: IntelligenceClass,
        summary: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Send threat/CVE to Cryptex for analysis and risk profiling."""
        try:
            from src.cryptex.threat_detector import get_cryptex

            cryptex = get_cryptex()
            signals = cryptex.analyse(
                context={"input": summary, "payload": str(payload), "target": "section7"},
                actor="section7",
            )
            logger.info(
                "section7: dispatched %s item %s to cryptex, %d signals emitted",
                classification.value,
                item_id,
                len(signals),
            )
            return True
        except Exception as exc:
            logger.warning("section7: cryptex dispatch failed for %s: %s", item_id, exc)
            return False

    def _catalogue_in_library(
        self,
        item_id: str,
        classification: IntelligenceClass,
        summary: str,
        payload: Dict[str, Any],
        source: str,
    ) -> bool:
        """Catalogue the item in The Library (permanent record)."""
        try:
            from src.library.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
            kb.store(
                doc_id=item_id,
                title=summary[:200],
                content=str(payload),
                tags=[classification.value, source, "section7"],
                metadata={"classification": classification.value, "source": source},
            )
            logger.info("section7: catalogued %s item %s in library", classification.value, item_id)
            return True
        except Exception as exc:
            logger.warning("section7: library catalogue failed for %s: %s", item_id, exc)
            return False

    def _dispatch_to_think_tank(
        self,
        item_id: str,
        classification: IntelligenceClass,
        summary: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Send research/advancement to Think Tank."""
        try:
            from src.nexus.hub import get_nexus

            get_nexus().publish(
                "section7.research.new",
                {
                    "item_id": item_id,
                    "classification": classification.value,
                    "summary": summary,
                    "payload": payload,
                },
                sender="section7",
            )
            logger.info(
                "section7: dispatched %s item %s to think tank via nexus",
                classification.value,
                item_id,
            )
            return True
        except Exception as exc:
            logger.warning("section7: think tank dispatch failed for %s: %s", item_id, exc)
            return False


# ── Module-level singleton ────────────────────────────────────────────────────
_router: Optional[InformationRouter] = None


def get_router() -> InformationRouter:
    global _router
    if _router is None:
        _router = InformationRouter()
    return _router
