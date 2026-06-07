"""
Section 7 Threat Intelligence Loop — TR3-006
=============================================
Background asyncio task that periodically fetches CVE/OSV/CISA data,
runs the IntelligenceAgent cycle, and emits threat signals to the EventBus.

Wire-up:
    from src.section7.threat_intel_loop import start_threat_intel_loop
    await start_threat_intel_loop()          # call once in lifespan

The loop runs every THREAT_INTEL_INTERVAL_SECS (default 3600 s) using only
zero-cost public feeds — no API keys required.

EventBus events emitted:
  security.cve.ingested    — per CVE item processed
  security.threat.detected — per Cryptex signal raised from CVE data
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("section7.threat_intel_loop")

# How often to poll feeds.  Can be overridden via environment variable.
_DEFAULT_INTERVAL = int(os.environ.get("THREAT_INTEL_INTERVAL_SECS", "3600"))

# Cap the number of items processed per cycle to avoid memory pressure.
_MAX_ITEMS_PER_CYCLE = int(os.environ.get("THREAT_INTEL_MAX_ITEMS", "100"))

_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# EventBus emission helpers
# ---------------------------------------------------------------------------


def _emit_cve_ingested(cve_id: str, severity: str, source: str) -> None:
    try:
        from src.event_bus import get_event_bus  # noqa: PLC0415

        get_event_bus().emit_async(
            event_type="security.cve.ingested",
            data={"cve_id": cve_id, "severity": severity, "source": source},
            source="section7",
        )
    except Exception as exc:  # nosec B110
        logger.debug("threat_intel_loop: emit_cve_ingested: %s", exc)


def _emit_threat_detected(signal_id: str, category: str, severity: str, evidence: str) -> None:
    try:
        from src.event_bus import get_event_bus  # noqa: PLC0415

        get_event_bus().emit_async(
            event_type="security.threat.detected",
            data={
                "signal_id": signal_id,
                "category": category,
                "severity": severity,
                "evidence": evidence[:400],
            },
            source="section7-cryptex",
        )
    except Exception as exc:  # nosec B110
        logger.debug("threat_intel_loop: emit_threat_detected: %s", exc)


# ---------------------------------------------------------------------------
# Anomaly detector — compares incoming CVEs against platform dependencies
# ---------------------------------------------------------------------------


def _load_platform_packages() -> List[str]:
    """
    Return a best-effort list of installed Python package names for
    cross-referencing against incoming CVE data.
    """
    try:
        import importlib.metadata as _meta

        return [d.name.lower() for d in _meta.distributions()]
    except Exception:
        return []


def _detect_anomalies(items: List[Any], platform_packages: List[str]) -> List[Dict[str, Any]]:
    """
    Cross-reference incoming IntelligenceItems against known platform packages.

    Returns a list of anomaly dicts for items that reference installed packages,
    or that carry CRITICAL/HIGH severity.
    """
    anomalies = []
    for item in items:
        tags = [t.lower() for t in getattr(item, "tags", [])]
        meta = getattr(item, "metadata", {})
        severity = str(meta.get("severity", "UNKNOWN")).upper()
        cve_id = meta.get("cve_id", "")

        # Flag CRITICAL/HIGH CVEs unconditionally
        if severity in ("CRITICAL", "HIGH"):
            anomalies.append(
                {
                    "cve_id": cve_id,
                    "severity": severity,
                    "title": getattr(item, "title", ""),
                    "reason": f"severity={severity}",
                    "tags": tags,
                }
            )
            continue

        # Flag if any tag matches an installed package
        for pkg in platform_packages:
            if pkg and any(pkg in tag for tag in tags):
                anomalies.append(
                    {
                        "cve_id": cve_id,
                        "severity": severity,
                        "title": getattr(item, "title", ""),
                        "reason": f"affects_installed_package:{pkg}",
                        "tags": tags,
                    }
                )
                break

    return anomalies


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def _run_loop(interval_secs: int) -> None:
    """Inner async loop — runs cycles separated by interval_secs."""
    logger.info("section7.threat_intel_loop: starting (interval=%ds)", interval_secs)

    platform_packages = await asyncio.get_event_loop().run_in_executor(
        None, _load_platform_packages
    )
    logger.debug(
        "section7.threat_intel_loop: %d platform packages loaded for anomaly detection",
        len(platform_packages),
    )

    while True:
        try:
            await _run_cycle(platform_packages)
        except asyncio.CancelledError:
            logger.info("section7.threat_intel_loop: cancelled")
            return
        except Exception as exc:  # nosec B110
            logger.warning("section7.threat_intel_loop: cycle error: %s", exc)

        try:
            await asyncio.sleep(interval_secs)
        except asyncio.CancelledError:
            logger.info("section7.threat_intel_loop: cancelled during sleep")
            return


async def _run_cycle(platform_packages: List[str]) -> None:
    """Execute one threat intel cycle: fetch → classify → emit."""
    from src.section7.cve_ingester import get_default_ingestors  # noqa: PLC0415
    from src.section7.intelligence_agent import IntelligenceAgent  # noqa: PLC0415

    t0 = time.monotonic()
    agent = IntelligenceAgent()
    ingestors = get_default_ingestors()

    # Fetch all items across all ingestors in the thread pool (blocking I/O)
    all_items: List[Any] = []
    for ingestor in ingestors:
        try:
            items = await asyncio.get_event_loop().run_in_executor(None, ingestor.fetch)
            all_items.extend(items)
        except Exception as exc:  # nosec B110
            logger.warning(
                "section7.threat_intel_loop: ingestor %s fetch failed: %s",
                type(ingestor).__name__,
                exc,
            )

    # Cap total items per cycle
    all_items = all_items[:_MAX_ITEMS_PER_CYCLE]

    # Emit cve.ingested events for each item (fire-and-forget)
    for item in all_items:
        meta = getattr(item, "metadata", {})
        _emit_cve_ingested(
            cve_id=meta.get("cve_id", "UNKNOWN"),
            severity=str(meta.get("severity", "UNKNOWN")),
            source=str(meta.get("source", "unknown")),
        )

    # Run anomaly detection — flag items that affect the platform
    anomalies = _detect_anomalies(all_items, platform_packages)
    for anomaly in anomalies:
        logger.warning(
            "section7.threat_intel_loop: ANOMALY %s severity=%s reason=%s",
            anomaly["cve_id"],
            anomaly["severity"],
            anomaly["reason"],
        )

    # Ingest into the agent → router → Cryptex + Library
    routed_ids = await asyncio.get_event_loop().run_in_executor(None, agent.ingest_many, all_items)

    # Emit threat.detected events for anomalies
    for anomaly in anomalies:
        _emit_threat_detected(
            signal_id=anomaly["cve_id"],
            category="outdated_component"
            if "affects_installed_package" in anomaly["reason"]
            else "cve",
            severity=anomaly["severity"].lower(),
            evidence=anomaly["title"],
        )

    elapsed = time.monotonic() - t0
    logger.info(
        "section7.threat_intel_loop: cycle complete — fetched=%d routed=%d anomalies=%d elapsed=%.1fs",
        len(all_items),
        len(routed_ids),
        len(anomalies),
        elapsed,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def start_threat_intel_loop(interval_secs: int = _DEFAULT_INTERVAL) -> asyncio.Task:
    """
    Start the background threat intel polling loop.

    Safe to call multiple times — returns the existing task if already running.
    """
    global _task
    if _task is not None and not _task.done():
        logger.debug("section7.threat_intel_loop: already running")
        return _task

    _task = asyncio.ensure_future(_run_loop(interval_secs))
    logger.info("section7.threat_intel_loop: background task started")
    return _task


async def stop_threat_intel_loop() -> None:
    """Cancel the background threat intel loop."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("section7.threat_intel_loop: stopped")
