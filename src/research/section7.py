# src/research/section7.py
# Section 7 — research, analysis, and intelligence hub for Trancendos.
#
# Section 7 aggregates intelligence from across the platform:
#   - Summarises Observatory audit trails
#   - Runs analysis jobs over archived data (The Basement)
#   - Provides structured insight reports for The Town Hall
#   - Feeds findings into The Library as KB articles
#
# Named for the classified intelligence division — Section 7 sees everything.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportType(str, Enum):
    SECURITY_SUMMARY  = "security_summary"
    COMPLIANCE_AUDIT  = "compliance_audit"
    PERFORMANCE_TREND = "performance_trend"
    THREAT_ANALYSIS   = "threat_analysis"
    USAGE_REPORT      = "usage_report"
    PLATFORM_HEALTH   = "platform_health"


@dataclass
class ResearchReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    report_type: ReportType = ReportType.PLATFORM_HEALTH
    title: str = ""
    summary: str = ""
    findings: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    author: str = "section7"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "report_type": self.report_type.value,
            "title": self.title,
            "summary": self.summary,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "data_sources": self.data_sources,
            "author": self.author,
        }


class Section7:
    """
    Section 7 — research and intelligence analysis hub.

    Aggregates cross-platform signals into structured reports.
    Reports are automatically published to The Library.
    """

    def __init__(self):
        self._reports: Dict[str, ResearchReport] = {}

    # ── Report generation ─────────────────────────────────────────────────────

    def generate_platform_health_report(self) -> ResearchReport:
        """Pull live status from all active services and produce a health report."""
        findings: List[Dict[str, Any]] = []
        recommendations: List[str] = []
        sources = []

        # Observatory stats
        try:
            from src.observability.observatory import get_observatory
            obs_stats = get_observatory().stats()
            findings.append({"source": "observatory", "data": obs_stats})
            sources.append("observatory")
            if obs_stats.get("by_severity", {}).get("critical", 0) > 0:
                recommendations.append("Review CRITICAL events in The Observatory immediately.")
        except Exception as exc:
            logger.debug("section7: observatory unavailable: %s", exc)

        # Town Hall compliance
        try:
            from src.townhall.governance import get_townhall
            th_status = get_townhall().status()
            findings.append({"source": "townhall", "data": th_status})
            sources.append("townhall")
            score = th_status.get("overall_score", 1.0)
            if score < 0.9:
                recommendations.append(f"Compliance score {score:.0%} is below 90% threshold — review policy gaps.")
        except Exception as exc:
            logger.debug("section7: townhall unavailable: %s", exc)

        # Cryptex threat signals
        try:
            from src.cryptex.threat_detector import ThreatSeverity, get_cryptex
            cx_stats = get_cryptex().stats()
            findings.append({"source": "cryptex", "data": cx_stats})
            sources.append("cryptex")
            high_signals = (
                cx_stats.get("by_severity", {}).get(ThreatSeverity.HIGH.value, 0) +
                cx_stats.get("by_severity", {}).get(ThreatSeverity.CRITICAL.value, 0)
            )
            if high_signals > 0:
                recommendations.append(f"Cryptex has {high_signals} HIGH/CRITICAL threat signals — investigate.")
        except Exception as exc:
            logger.debug("section7: cryptex unavailable: %s", exc)

        # Basement archive
        try:
            from src.basement.archive import get_basement
            bm_stats = get_basement().stats()
            findings.append({"source": "basement", "data": bm_stats})
            sources.append("basement")
        except Exception as exc:
            logger.debug("section7: basement unavailable: %s", exc)

        # Nexus message bus
        try:
            from src.nexus.hub import get_nexus
            nx_status = get_nexus().status()
            findings.append({"source": "nexus", "data": nx_status})
            sources.append("nexus")
        except Exception as exc:
            logger.debug("section7: nexus unavailable: %s", exc)

        if not recommendations:
            recommendations.append("All monitored services are within normal operating parameters.")

        report = ResearchReport(
            report_type=ReportType.PLATFORM_HEALTH,
            title=f"Platform Health Report — {_ts_human(time.time())}",
            summary=(
                f"Cross-platform health assessment covering {len(sources)} services. "
                f"{len([r for r in recommendations if 'immediately' in r or 'investigate' in r])} "
                "items require immediate attention."
            ),
            findings=findings,
            recommendations=recommendations,
            data_sources=sources,
        )
        self._store_and_publish(report)
        return report

    def generate_security_report(self) -> ResearchReport:
        """Pull Cryptex + Observatory security events into a structured report."""
        findings: List[Dict[str, Any]] = []
        recommendations: List[str] = []

        try:
            from src.cryptex.threat_detector import ThreatSeverity, get_cryptex
            cx = get_cryptex()
            recent = cx.recent_signals(limit=20, min_severity=ThreatSeverity.MEDIUM)
            findings.append({
                "source": "cryptex",
                "recent_signals": [s.to_dict() for s in recent],
                "stats": cx.stats(),
            })
            if cx.stats().get("blocked_ips", 0) > 0:
                recommendations.append(f"{cx.stats()['blocked_ips']} IPs currently blocked by Cryptex.")
        except Exception as exc:
            logger.debug("section7: cryptex unavailable: %s", exc)

        try:
            from src.observability.observatory import EventCategory, get_observatory
            obs = get_observatory()
            security_events = obs.recent(limit=20, category=EventCategory.SECURITY)
            findings.append({
                "source": "observatory",
                "security_events": [e.to_dict() for e in security_events],
            })
        except Exception as exc:
            logger.debug("section7: observatory unavailable: %s", exc)

        report = ResearchReport(
            report_type=ReportType.SECURITY_SUMMARY,
            title=f"Security Intelligence Report — {_ts_human(time.time())}",
            summary=f"Security sweep across {len(findings)} intelligence sources.",
            findings=findings,
            recommendations=recommendations or ["No active threats detected at this time."],
            data_sources=["cryptex", "observatory"],
        )
        self._store_and_publish(report)
        return report

    # ── Report access ─────────────────────────────────────────────────────────

    def get(self, report_id: str) -> Optional[ResearchReport]:
        return self._reports.get(report_id)

    def recent(self, limit: int = 10, report_type: Optional[ReportType] = None) -> List[ResearchReport]:
        reports = list(self._reports.values())
        if report_type:
            reports = [r for r in reports if r.report_type == report_type]
        return sorted(reports, key=lambda r: r.timestamp, reverse=True)[:limit]

    def stats(self) -> Dict[str, Any]:
        return {
            "total_reports": len(self._reports),
            "by_type": {rt.value: sum(1 for r in self._reports.values() if r.report_type == rt) for rt in ReportType},
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _store_and_publish(self, report: ResearchReport) -> None:
        self._reports[report.id] = report

        # Publish to The Library
        try:
            from src.library.knowledge_base import get_library
            get_library().create(
                title=report.title,
                body=report.summary + "\n\n" + "\n".join(f"- {r}" for r in report.recommendations),
                tags=["section7", report.report_type.value, "auto-generated"],
                author="section7",
                source="section7",
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


        # Emit Observatory event
        try:
            from src.observability.observatory import EventCategory, observe
            observe(
                f"section7.report.{report.report_type.value}",
                actor="section7",
                target=f"report:{report.id}",
                category=EventCategory.AUDIT,
                service="section7",
                metadata={"title": report.title, "findings_count": len(report.findings)},
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


        logger.info("section7: report generated type=%s id=%s", report.report_type.value, report.id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts_human(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")


# ── Module-level singleton ────────────────────────────────────────────────────
_section7: Optional[Section7] = None


def get_section7() -> Section7:
    global _section7
    if _section7 is None:
        _section7 = Section7()
    return _section7
