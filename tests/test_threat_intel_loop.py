"""
TR3-006: Section 7 Threat Intelligence Loop — unit tests.

Tests:
- _detect_anomalies: correctly flags CRITICAL/HIGH CVEs
- _detect_anomalies: flags CVEs affecting installed packages
- _emit_cve_ingested: calls bus.emit_async with correct payload
- _emit_threat_detected: calls bus.emit_async with correct payload
- run_cycle: processes items from stubbed ingestors end-to-end
- start/stop: task lifecycle management
- EventBus SECURITY_CVE_INGESTED and SECURITY_THREAT_DETECTED enum values exist
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.section7.threat_intel_loop import (
    _detect_anomalies,
    _emit_cve_ingested,
    _emit_threat_detected,
    _run_cycle,
    start_threat_intel_loop,
    stop_threat_intel_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(cve_id="CVE-2025-0001", severity="HIGH", source="nvd", tags=None):
    """Build a minimal IntelligenceItem-like object."""
    obj = MagicMock()
    obj.tags = tags or ["python", "requests"]
    obj.metadata = {"cve_id": cve_id, "severity": severity, "source": source}
    obj.title = f"{cve_id}: test vuln"
    obj.raw_content = "test content"
    return obj


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


def test_detect_anomalies_flags_critical():
    items = [_make_item(severity="CRITICAL")]
    result = _detect_anomalies(items, [])
    assert len(result) == 1
    assert result[0]["severity"] == "CRITICAL"
    assert result[0]["reason"] == "severity=CRITICAL"


def test_detect_anomalies_flags_high():
    items = [_make_item(severity="HIGH")]
    result = _detect_anomalies(items, [])
    assert len(result) == 1
    assert result[0]["severity"] == "HIGH"


def test_detect_anomalies_skips_low():
    items = [_make_item(severity="LOW")]
    result = _detect_anomalies(items, [])
    assert result == []


def test_detect_anomalies_flags_installed_package():
    items = [_make_item(severity="MEDIUM", tags=["requests", "http"])]
    # "requests" is in platform_packages
    result = _detect_anomalies(items, ["requests", "flask"])
    assert len(result) == 1
    assert "requests" in result[0]["reason"]


def test_detect_anomalies_empty_items():
    assert _detect_anomalies([], ["requests"]) == []


def test_detect_anomalies_empty_packages():
    items = [_make_item(severity="MEDIUM", tags=["django"])]
    assert _detect_anomalies(items, []) == []


# ---------------------------------------------------------------------------
# EventBus emission helpers
# ---------------------------------------------------------------------------


def test_emit_cve_ingested_calls_bus():
    emitted = []
    fake_bus = MagicMock()
    fake_bus.emit_async = lambda event_type, data, source: emitted.append(
        {"event_type": event_type, "data": data}
    )
    with patch("src.event_bus.get_event_bus", return_value=fake_bus):
        _emit_cve_ingested("CVE-2025-1234", "CRITICAL", "nvd")

    assert len(emitted) == 1
    assert emitted[0]["event_type"] == "security.cve.ingested"
    assert emitted[0]["data"]["cve_id"] == "CVE-2025-1234"
    assert emitted[0]["data"]["severity"] == "CRITICAL"


def test_emit_threat_detected_calls_bus():
    emitted = []
    fake_bus = MagicMock()
    fake_bus.emit_async = lambda event_type, data, source: emitted.append(
        {"event_type": event_type, "data": data}
    )
    with patch("src.event_bus.get_event_bus", return_value=fake_bus):
        _emit_threat_detected("CVE-2025-5555", "outdated_component", "high", "Vuln in requests")

    assert len(emitted) == 1
    assert emitted[0]["event_type"] == "security.threat.detected"
    assert emitted[0]["data"]["category"] == "outdated_component"
    assert emitted[0]["data"]["severity"] == "high"


def test_emit_cve_ingested_survives_bus_error():
    """Errors from bus must be swallowed (fire-and-forget)."""
    fake_bus = MagicMock()
    fake_bus.emit_async = MagicMock(side_effect=RuntimeError("bus down"))
    with patch("src.event_bus.get_event_bus", return_value=fake_bus):
        _emit_cve_ingested("CVE-X", "LOW", "osv")  # must not raise


# ---------------------------------------------------------------------------
# Full cycle (stubbed ingestors)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_cycle_emits_cve_ingested_events():
    """
    _run_cycle should call _emit_cve_ingested for each item processed.
    Patch the lazy-imported symbols at their source modules.
    """
    items = [
        _make_item("CVE-2025-0001", "CRITICAL"),
        _make_item("CVE-2025-0002", "HIGH"),
        _make_item("CVE-2025-0003", "LOW"),
    ]

    class FakeIngestor:
        def fetch(self):
            return items

    cve_emits = []

    import src.section7.cve_ingester as _ci
    import src.section7.intelligence_agent as _ia

    orig_ingestors = getattr(_ci, "get_default_ingestors", None)
    orig_agent = _ia.IntelligenceAgent

    try:
        _ci.get_default_ingestors = lambda **kw: [FakeIngestor()]
        _ia.IntelligenceAgent = lambda: MagicMock(ingest_many=lambda b: [])
        with (
            patch(
                "src.section7.threat_intel_loop._emit_cve_ingested",
                side_effect=lambda cve_id, severity, source: cve_emits.append(cve_id),
            ),
            patch("src.section7.threat_intel_loop._emit_threat_detected"),
        ):
            await _run_cycle(platform_packages=[])
    finally:
        if orig_ingestors is not None:
            _ci.get_default_ingestors = orig_ingestors
        _ia.IntelligenceAgent = orig_agent

    assert len(cve_emits) == 3


@pytest.mark.asyncio
async def test_run_cycle_anomaly_detection_emits_threat():
    """CRITICAL items trigger _emit_threat_detected."""
    items = [_make_item("CVE-2025-9999", "CRITICAL")]

    class FakeIngestor:
        def fetch(self):
            return items

    threat_emits = []

    import src.section7.cve_ingester as _ci
    import src.section7.intelligence_agent as _ia

    orig_ingestors = getattr(_ci, "get_default_ingestors", None)
    orig_agent = _ia.IntelligenceAgent

    try:
        _ci.get_default_ingestors = lambda **kw: [FakeIngestor()]
        _ia.IntelligenceAgent = lambda: MagicMock(ingest_many=lambda b: [])
        with (
            patch("src.section7.threat_intel_loop._emit_cve_ingested"),
            patch(
                "src.section7.threat_intel_loop._emit_threat_detected",
                side_effect=lambda signal_id, category, severity, evidence: threat_emits.append(
                    {"signal_id": signal_id, "severity": severity}
                ),
            ),
        ):
            await _run_cycle(platform_packages=[])
    finally:
        if orig_ingestors is not None:
            _ci.get_default_ingestors = orig_ingestors
        _ia.IntelligenceAgent = orig_agent

    assert len(threat_emits) == 1
    assert threat_emits[0]["signal_id"] == "CVE-2025-9999"
    assert threat_emits[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_run_cycle_ingestor_error_does_not_crash():
    """A failing ingestor must not stop the cycle."""

    class BrokenIngestor:
        def fetch(self):
            raise RuntimeError("network timeout")

    good_items = [_make_item()]

    class GoodIngestor:
        def fetch(self):
            return good_items

    ingested = []

    import src.section7.cve_ingester as _ci
    import src.section7.intelligence_agent as _ia

    orig_ingestors = getattr(_ci, "get_default_ingestors", None)
    orig_agent = _ia.IntelligenceAgent

    try:
        _ci.get_default_ingestors = lambda **kw: [BrokenIngestor(), GoodIngestor()]
        _ia.IntelligenceAgent = lambda: MagicMock(
            ingest_many=lambda b: [ingested.append(x) or "id" for x in b]
        )
        with (
            patch("src.section7.threat_intel_loop._emit_cve_ingested"),
            patch("src.section7.threat_intel_loop._emit_threat_detected"),
        ):
            await _run_cycle(platform_packages=[])
    finally:
        if orig_ingestors is not None:
            _ci.get_default_ingestors = orig_ingestors
        _ia.IntelligenceAgent = orig_agent

    assert len(ingested) == 1


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_stop_creates_and_cancels_task():
    with patch("src.section7.threat_intel_loop._run_loop", new_callable=AsyncMock):
        task = await start_threat_intel_loop(interval_secs=9999)
        assert task is not None
        assert not task.done()
        await stop_threat_intel_loop()


@pytest.mark.asyncio
async def test_start_twice_returns_same_task():
    with patch("src.section7.threat_intel_loop._run_loop", new_callable=AsyncMock):
        t1 = await start_threat_intel_loop(interval_secs=9999)
        t2 = await start_threat_intel_loop(interval_secs=9999)
        assert t1 is t2
        await stop_threat_intel_loop()


# ---------------------------------------------------------------------------
# EventBus new event type enums
# ---------------------------------------------------------------------------


def test_security_event_types_in_enum():
    from src.event_bus.types import PlatformEventType

    assert PlatformEventType.SECURITY_CVE_INGESTED == "security.cve.ingested"
    assert PlatformEventType.SECURITY_THREAT_DETECTED == "security.threat.detected"
    assert PlatformEventType.SECURITY_ANOMALY_FLAGGED == "security.anomaly.flagged"
