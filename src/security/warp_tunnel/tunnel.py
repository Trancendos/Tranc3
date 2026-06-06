"""
The Warp Tunnel — Isolation Routing Layer
==========================================
Intercepts inbound content before it enters the main execution path.
Suspicious/malicious content is diverted to The Ice Box quarantine rather
than being processed by downstream services.

Usage
-----
    tunnel = WarpTunnel()
    result = tunnel.scan(user_input, source="api/chat")
    if not result.allow:
        raise HTTPException(status_code=400, detail=result.block_reason)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.security.ice_box.analyser import ThreatAnalyser, ThreatVerdict
from src.security.ice_box.quarantine import QuarantineStore

logger = logging.getLogger("tranc3.warp_tunnel")


@dataclass
class TunnelConfig:
    # Verdicts that trigger a quarantine + block
    block_verdicts: tuple[ThreatVerdict, ...] = (
        ThreatVerdict.MALICIOUS,
        ThreatVerdict.QUARANTINED,
    )
    # Verdicts that quarantine but still allow through (monitor mode)
    warn_verdicts: tuple[ThreatVerdict, ...] = (ThreatVerdict.SUSPICIOUS,)
    # Maximum content length accepted (bytes); 0 = unlimited
    max_content_bytes: int = 1_000_000
    # Path to quarantine DB
    quarantine_db: str = "data/ice_box_quarantine.db"
    # If True, block on SUSPICIOUS in addition to MALICIOUS
    strict_mode: bool = False


@dataclass
class TunnelResult:
    allow: bool
    verdict: ThreatVerdict
    quarantine_id: Optional[str] = None
    block_reason: Optional[str] = None
    findings_count: int = 0
    analysis_ms: float = 0.0

    @property
    def was_quarantined(self) -> bool:
        return self.quarantine_id is not None


class WarpTunnel:
    """
    Thread-safe content interception and routing layer.

    All content entering the platform should pass through `scan()` before
    being processed. Clean content flows through unmodified; malicious
    content is quarantined and a block result is returned.
    """

    def __init__(self, config: Optional[TunnelConfig] = None) -> None:
        self.config = config or TunnelConfig()
        self._analyser = ThreatAnalyser()
        self._quarantine = QuarantineStore(self.config.quarantine_db)

    def scan(self, content: str | bytes, *, source: str = "") -> TunnelResult:
        """
        Scan *content*, quarantine if necessary, and return a routing decision.

        Parameters
        ----------
        content : str | bytes
            The content to inspect (user input, uploaded file, API payload, etc.)
        source : str
            Label for the origin (e.g. "api/chat", "upload/image").

        Returns
        -------
        TunnelResult
            .allow=True → route to downstream handler
            .allow=False → reject and surface block_reason to caller
        """
        raw: bytes = content.encode("utf-8", errors="replace") if isinstance(content, str) else content

        # Size gate — avoids scanning multi-GB payloads
        if self.config.max_content_bytes and len(raw) > self.config.max_content_bytes:
            logger.warning("warp_tunnel: oversized payload (%d bytes) from %s", len(raw), source)
            return TunnelResult(
                allow=False,
                verdict=ThreatVerdict.MALICIOUS,
                block_reason=f"Payload exceeds maximum size ({self.config.max_content_bytes} bytes)",
                findings_count=1,
            )

        report = self._analyser.analyse(raw, source=source)

        qid: Optional[str] = None
        should_block = (
            report.verdict in self.config.block_verdicts
            or (self.config.strict_mode and report.verdict in self.config.warn_verdicts)
        )
        should_quarantine = should_block or report.verdict in self.config.warn_verdicts

        if should_quarantine:
            try:
                qid = self._quarantine.quarantine(report, source=source)
            except Exception as exc:  # noqa: BLE001
                logger.error("warp_tunnel: quarantine store failure: %s", exc)

        if should_block:
            critical = report.critical_count
            high = report.high_count
            reason = (
                f"Content blocked by Warp Tunnel: {len(report.findings)} finding(s)"
                f" — {critical} critical, {high} high severity"
            )
            if qid:
                reason += f" [quarantine_id={qid}]"
            logger.warning(
                "warp_tunnel: BLOCKED content from %s — %s — qid=%s",
                source, report.verdict.value, qid,
            )
            return TunnelResult(
                allow=False,
                verdict=report.verdict,
                quarantine_id=qid,
                block_reason=reason,
                findings_count=len(report.findings),
                analysis_ms=report.analysis_ms,
            )

        if report.verdict in self.config.warn_verdicts:
            logger.info(
                "warp_tunnel: WARN content from %s — %s — qid=%s",
                source, report.verdict.value, qid,
            )

        return TunnelResult(
            allow=True,
            verdict=report.verdict,
            quarantine_id=qid,
            findings_count=len(report.findings),
            analysis_ms=report.analysis_ms,
        )

    def quarantine_stats(self) -> dict:
        return self._quarantine.stats()
