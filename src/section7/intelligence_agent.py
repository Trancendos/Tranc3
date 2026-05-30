"""
Section 7 — Intelligence Agent
================================
Background daemon that ingests intelligence from multiple sources,
classifies each item, and dispatches it through the InformationRouter.

Sources:
  - CVE feeds (NVD JSON, opencve.io-compatible API)
  - Security advisory RSS feeds
  - Research paper metadata (arXiv, NIST, CISA)
  - Web scans (user-configured URLs)
  - Internal platform signals

All items flow: Agent → InformationRouter → Observatory → {Cryptex, Think Tank, Library}
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("section7.agent")


class SourceType(str, Enum):
    CVE_FEED = "cve_feed"
    ADVISORY_RSS = "advisory_rss"
    RESEARCH_PAPER = "research_paper"
    WEB_SCAN = "web_scan"
    INTERNAL_SIGNAL = "internal_signal"
    MANUAL = "manual"


@dataclass
class IntelligenceItem:
    """A single unit of intelligence ingested by Section 7."""

    source_type: SourceType
    raw_content: str
    title: str = ""
    url: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Populated after ingestion
    item_id: str = field(default_factory=lambda: str(uuid4()))
    ingested_at: float = field(default_factory=time.time)

    def fingerprint(self) -> str:
        """Stable content hash — prevents duplicate ingestion."""
        payload = f"{self.source_type}:{self.title}:{self.url}:{self.raw_content[:256]}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class IntelligenceAgent:
    """
    Section 7 background intelligence agent.

    Consumes items from registered ingestors, classifies them,
    and hands them to InformationRouter for distribution.

    Design: pull-based (no background threads required for tests).
    Production use: call run_cycle() on a scheduler (e.g. APScheduler / cron).
    """

    # Keyword patterns for zero-dependency classification
    _THREAT_PATTERNS = re.compile(
        r"\b(exploit|malware|ransomware|backdoor|rootkit|trojan|spyware|"
        r"zero.?day|0day|rce|remote.code|privilege.escal|buffer.overflow|"
        r"sql.inject|xss|csrf|ssrf|path.traversal|command.inject|"
        r"denial.of.service|dos|ddos|brute.force|phishing|credential|breach)\b",
        re.IGNORECASE,
    )
    _CVE_PATTERNS = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
    _RESEARCH_PATTERNS = re.compile(
        r"\b(research|paper|study|analysis|framework|methodology|benchmark|"
        r"neural|transformer|large.language|llm|machine.learning|deep.learning|"
        r"quantum|algorithm|optimis|arxiv|ieee|acm|nist|whitepaper)\b",
        re.IGNORECASE,
    )
    _ADVANCEMENT_PATTERNS = re.compile(
        r"\b(advancement|breakthrough|innovation|state.of.the.art|sota|"
        r"new.model|new.technique|improve|enhance|upgrade|feature|release|"
        r"open.source|library|sdk|api|framework|tool)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        from src.section7.information_router import get_router

        self._router = get_router()
        self._seen: set[str] = set()  # dedup fingerprints
        self._stats = {
            "ingested": 0,
            "routed": 0,
            "duplicates": 0,
            "errors": 0,
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest(self, item: IntelligenceItem) -> Optional[str]:
        """
        Classify and route a single IntelligenceItem.

        Returns the item_id on success, None if duplicate or error.
        """
        fp = item.fingerprint()
        if fp in self._seen:
            self._stats["duplicates"] += 1
            logger.debug("section7: duplicate item skipped (fp=%s)", fp)
            return None

        self._seen.add(fp)
        self._stats["ingested"] += 1

        try:
            cls = self._classify(item)
            summary = item.title or item.raw_content[:200]
            payload: Dict[str, Any] = {
                "source_type": item.source_type.value,
                "url": item.url,
                "tags": item.tags,
                **item.metadata,
            }
            if item.raw_content:
                payload["excerpt"] = item.raw_content[:500]

            result = self._router.route(
                item_id=item.item_id,
                classification=cls,
                summary=summary,
                payload=payload,
                source="section7",
            )
            self._stats["routed"] += 1
            logger.info(
                "section7: ingested %s as %s (id=%s, success=%s)",
                item.source_type.value,
                cls.value,
                item.item_id,
                result.success,
            )
            return item.item_id

        except Exception as exc:
            self._stats["errors"] += 1
            logger.warning("section7: ingest error for %s: %s", item.item_id, exc)
            return None

    def ingest_many(self, items: List[IntelligenceItem]) -> List[str]:
        """Ingest a batch of items; returns list of successfully routed item_ids."""
        routed = []
        for item in items:
            item_id = self.ingest(item)
            if item_id:
                routed.append(item_id)
        return routed

    def run_cycle(self, ingestors: Optional[List[Any]] = None) -> Dict[str, int]:
        """
        Execute one ingestion cycle across all registered ingestors.

        Each ingestor must implement `.fetch() -> List[IntelligenceItem]`.
        Returns per-cycle stats.
        """
        if ingestors is None:
            ingestors = []

        cycle_stats = {"fetched": 0, "routed": 0, "errors": 0}
        for ingestor in ingestors:
            try:
                items = ingestor.fetch()
                cycle_stats["fetched"] += len(items)
                routed = self.ingest_many(items)
                cycle_stats["routed"] += len(routed)
            except Exception as exc:
                cycle_stats["errors"] += 1
                logger.warning("section7: ingestor %s failed: %s", type(ingestor).__name__, exc)

        logger.info("section7: cycle complete — %s", cycle_stats)
        return cycle_stats

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "router": self._router.stats()}

    # ── Classification ────────────────────────────────────────────────────────

    def _classify(self, item: IntelligenceItem) -> Any:
        """Classify an IntelligenceItem into an IntelligenceClass."""
        from src.section7.information_router import IntelligenceClass

        # Source-type shortcuts
        if item.source_type == SourceType.WEB_SCAN:
            # Web scans may still contain CVEs — check first
            text = f"{item.title} {item.raw_content}"
            if self._CVE_PATTERNS.search(text):
                return IntelligenceClass.CVE
            return IntelligenceClass.WEB_SCAN

        if item.source_type == SourceType.INTERNAL_SIGNAL:
            return IntelligenceClass.KNOWLEDGE

        # Content-based classification
        text = f"{item.title} {item.raw_content}"

        if self._CVE_PATTERNS.search(text):
            return IntelligenceClass.CVE

        if self._THREAT_PATTERNS.search(text):
            return IntelligenceClass.THREAT

        if item.source_type == SourceType.RESEARCH_PAPER:
            # Check advancement vs research
            if self._ADVANCEMENT_PATTERNS.search(text):
                return IntelligenceClass.ADVANCEMENT
            return IntelligenceClass.RESEARCH

        if self._ADVANCEMENT_PATTERNS.search(text):
            return IntelligenceClass.ADVANCEMENT

        if self._RESEARCH_PATTERNS.search(text):
            return IntelligenceClass.RESEARCH

        return IntelligenceClass.KNOWLEDGE
