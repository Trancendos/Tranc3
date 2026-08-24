"""
Cryptex — CVE Scanner
======================
Pulls CVE feeds via Section 7's ingestors and drives them through
the Cryptex threat analysis pipeline to produce risk profiles.

User requirement (verbatim): "The Cryptex which i think you know what
this is by now but this has the ability to scan the CVE hosting
locations some examples could be: https://app.opencve.io/cve/"

Architecture:
  Section 7 CVEIngestors → CveScanner → IntelligenceAgent → InformationRouter
                                       ↓
                              Cryptex.analyse() per CVE
                                       ↓
                            risk profile + severity signal

This module is the bridge between Section 7's intelligence pipeline
and Cryptex's threat analysis engine.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cryptex.cve_scanner")


@dataclass
class CveRiskProfile:
    """Risk assessment produced by Cryptex for a single CVE."""

    cve_id: str
    severity: str
    cvss_score: float
    cryptex_signals: int = 0
    mitigation_actions: List[str] = field(default_factory=list)
    summary: str = ""
    routed: bool = False
    error: Optional[str] = None


class CveScanner:
    """
    Orchestrates CVE feed ingestion → Cryptex threat analysis → routing.

    Typical call pattern:
        scanner = CveScanner()
        profiles = scanner.scan_cycle()   # full pipeline: fetch + analyse + route

    Or fine-grained:
        items = scanner.fetch_cves()      # just the raw IntelligenceItems
        profiles = scanner.analyse_items(items)   # CVE → risk profile
    """

    def __init__(
        self,
        opencve_base_url: Optional[str] = None,
        opencve_api_key: Optional[str] = None,
    ) -> None:
        self._opencve_base_url = opencve_base_url or os.environ.get(
            "OPENCVE_URL", "https://www.opencve.io"
        )
        self._opencve_api_key = opencve_api_key or os.environ.get("OPENCVE_API_KEY")

    # ── Public API ────────────────────────────────────────────────────────────

    def scan_cycle(
        self,
        max_cves: int = 100,
    ) -> List[CveRiskProfile]:
        """
        Full pipeline:
          1. Fetch CVEs from all configured sources (NVD, CISA KEV, opencve)
          2. Analyse each through Cryptex
          3. Route items through Section 7 InformationRouter (Observatory → Cryptex hub)

        Returns list of risk profiles.
        """
        items = self.fetch_cves(max_cves=max_cves)
        profiles = self.analyse_items(items)
        self._route_items(items)
        return profiles

    def fetch_cves(self, max_cves: int = 100) -> List[Any]:
        """
        Fetch CVE IntelligenceItems from all zero-cost sources.
        Returns a flat list of IntelligenceItem objects.
        """
        from src.section7.cve_ingester import get_default_ingestors

        ingestors = get_default_ingestors(
            opencve_base_url=self._opencve_base_url,
            opencve_api_key=self._opencve_api_key,
        )

        all_items: List[Any] = []
        for ingestor in ingestors:
            try:
                items = ingestor.fetch()
                all_items.extend(items)
                logger.debug(
                    "cryptex.cve_scanner: %s returned %d items",
                    type(ingestor).__name__,
                    len(items),
                )
            except Exception as exc:
                logger.warning(
                    "cryptex.cve_scanner: ingestor %s failed: %s",
                    type(ingestor).__name__,
                    exc,
                )

        # Deduplicate by CVE-ID (keep first seen)
        seen_ids: set[str] = set()
        unique: List[Any] = []
        for item in all_items:
            cve_id = item.metadata.get("cve_id", "")
            if cve_id and cve_id in seen_ids:
                continue
            if cve_id:
                seen_ids.add(cve_id)
            unique.append(item)

        logger.info(
            "cryptex.cve_scanner: fetched %d unique CVE items (from %d total)",
            len(unique),
            len(all_items),
        )
        return unique[:max_cves]

    def analyse_items(self, items: List[Any]) -> List[CveRiskProfile]:
        """
        Drive each IntelligenceItem through Cryptex.analyse() to produce risk profiles.
        Items without CVE IDs are still analysed but flagged as non-CVE signals.
        """
        try:
            from src.cryptex.threat_detector import get_cryptex

            cryptex = get_cryptex()
        except Exception as exc:
            logger.warning("cryptex.cve_scanner: cannot load Cryptex: %s", exc)
            return []

        profiles = []
        for item in items:
            cve_id = item.metadata.get("cve_id", "UNKNOWN")
            severity = item.metadata.get("severity", "UNKNOWN")
            cvss_score = float(item.metadata.get("cvss_score", 0.0))

            try:
                signals = cryptex.analyse(
                    context={
                        "input": item.raw_content,
                        "payload": str(item.metadata),
                        "target": "cve_scanner",
                        "cve_id": cve_id,
                    },
                    actor="section7.cve_scanner",
                )

                mitigation_actions = list({s.action.value for s in signals if hasattr(s, "action")})

                profile = CveRiskProfile(
                    cve_id=cve_id,
                    severity=severity,
                    cvss_score=cvss_score,
                    cryptex_signals=len(signals),
                    mitigation_actions=mitigation_actions,
                    summary=item.title or item.raw_content[:200],
                    routed=False,
                )
                profiles.append(profile)

                logger.debug(
                    "cryptex.cve_scanner: %s analysed → %d signals, actions=%s",
                    cve_id,
                    len(signals),
                    mitigation_actions,
                )

            except Exception as exc:
                logger.warning("cryptex.cve_scanner: analysis failed for %s: %s", cve_id, exc)
                profiles.append(
                    CveRiskProfile(
                        cve_id=cve_id,
                        severity=severity,
                        cvss_score=cvss_score,
                        error=str(exc),
                    )
                )

        high_severity = sum(
            1 for p in profiles if p.severity in ("HIGH", "CRITICAL") and not p.error
        )
        logger.info(
            "cryptex.cve_scanner: analysed %d CVEs — %d HIGH/CRITICAL",
            len(profiles),
            high_severity,
        )
        return profiles

    def stats(self) -> Dict[str, Any]:
        """Return scanner stats including Cryptex state."""
        result: Dict[str, Any] = {"scanner": "cve_scanner"}
        try:
            from src.cryptex.threat_detector import get_cryptex

            result["cryptex"] = get_cryptex().stats()
        except Exception:
            result["cryptex"] = "unavailable"
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    def _route_items(self, items: List[Any]) -> None:
        """Route all items through Section 7 InformationRouter."""
        try:
            from src.section7.intelligence_agent import IntelligenceAgent

            agent = IntelligenceAgent()
            routed = agent.ingest_many(items)
            logger.info(
                "cryptex.cve_scanner: routed %d/%d CVE items through Section 7",
                len(routed),
                len(items),
            )
        except Exception as exc:
            logger.warning("cryptex.cve_scanner: routing failed: %s", exc)


# Module-level singleton
_scanner: Optional[CveScanner] = None


def get_cve_scanner(
    opencve_base_url: Optional[str] = None,
    opencve_api_key: Optional[str] = None,
) -> CveScanner:
    global _scanner
    if _scanner is None:
        _scanner = CveScanner(
            opencve_base_url=opencve_base_url,
            opencve_api_key=opencve_api_key,
        )
    return _scanner
