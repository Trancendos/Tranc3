"""
Tests for Section 7 — Background Intelligence & Investigation Service.

Covers:
  - IntelligenceClass classification enum
  - IntelligenceItem creation and fingerprinting
  - IntelligenceAgent classification logic (no network calls)
  - InformationRouter routing rules (observatory-first, hub dispatch)
  - CveScanner (mocked network)
  - vault-service AES-256-GCM encryption fix
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── IntelligenceClass ─────────────────────────────────────────────────────────


def test_intelligence_class_values():
    from src.section7.information_router import IntelligenceClass

    assert IntelligenceClass.THREAT.value == "threat"
    assert IntelligenceClass.CVE.value == "cve"
    assert IntelligenceClass.RESEARCH.value == "research"
    assert IntelligenceClass.ADVANCEMENT.value == "advancement"
    assert IntelligenceClass.KNOWLEDGE.value == "knowledge"
    assert IntelligenceClass.WEB_SCAN.value == "web_scan"
    assert IntelligenceClass.UNKNOWN.value == "unknown"


# ── IntelligenceItem ──────────────────────────────────────────────────────────


def test_intelligence_item_defaults():
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    item = IntelligenceItem(
        source_type=SourceType.CVE_FEED,
        raw_content="CVE-2024-12345 critical remote code execution",
        title="CVE-2024-12345",
    )
    assert item.item_id  # auto-generated UUID
    assert item.ingested_at > 0
    assert item.tags == []
    assert item.metadata == {}


def test_intelligence_item_fingerprint_stable():
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    item = IntelligenceItem(
        source_type=SourceType.CVE_FEED,
        raw_content="test content",
        title="test title",
        url="https://example.com",
    )
    fp1 = item.fingerprint()
    fp2 = item.fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 16


def test_intelligence_item_fingerprint_differs_by_content():
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    item_a = IntelligenceItem(source_type=SourceType.CVE_FEED, raw_content="content A")
    item_b = IntelligenceItem(source_type=SourceType.CVE_FEED, raw_content="content B")
    assert item_a.fingerprint() != item_b.fingerprint()


# ── IntelligenceAgent Classification ─────────────────────────────────────────


@pytest.fixture()
def agent_with_mock_router():
    """Agent with the router's sub-methods replaced by mocks to avoid external calls."""
    from src.section7.intelligence_agent import IntelligenceAgent

    agent = IntelligenceAgent.__new__(IntelligenceAgent)
    agent._seen = set()
    agent._stats = {"ingested": 0, "routed": 0, "duplicates": 0, "errors": 0}

    mock_router = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_router.route.return_value = mock_result
    mock_router.stats.return_value = {}
    agent._router = mock_router
    return agent, mock_router


@pytest.mark.parametrize(
    "title,raw,source_type,expected_class",
    [
        ("CVE-2024-12345", "critical remote code execution", "cve_feed", "cve"),
        ("CVE-2023-99999 patch", "arbitrary fix", "manual", "cve"),
        ("SQL injection attack detected", "malware found on system", "manual", "threat"),
        ("ransomware campaign", "encrypted files observed", "manual", "threat"),
        (
            "New neural network paper",
            "research into transformers and LLM benchmarks on arXiv",
            "research_paper",
            "research",
        ),
        (
            "State-of-the-art breakthrough",
            "open-source library released with improvements",
            "research_paper",
            "advancement",
        ),
        ("Web page scan result", "normal website content", "web_scan", "web_scan"),
        (
            "CVE found in web scan",
            "CVE-2024-9999 vulnerability detected",
            "web_scan",
            "cve",
        ),
        ("General knowledge entry", "background information about systems", "manual", "knowledge"),
        ("Internal signal", "platform health check", "internal_signal", "knowledge"),
    ],
)
def test_agent_classify(agent_with_mock_router, title, raw, source_type, expected_class):
    from src.section7.information_router import IntelligenceClass
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    agent, _ = agent_with_mock_router
    item = IntelligenceItem(
        source_type=SourceType(source_type),
        raw_content=raw,
        title=title,
    )
    result = agent._classify(item)
    assert result == IntelligenceClass(expected_class), (
        f"Expected {expected_class!r}, got {result!r} for title={title!r}"
    )


def test_agent_ingest_deduplicates(agent_with_mock_router):
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    agent, mock_router = agent_with_mock_router
    item = IntelligenceItem(
        source_type=SourceType.CVE_FEED,
        raw_content="CVE-2024-99999 duplicate test",
        title="CVE-2024-99999",
    )
    first = agent.ingest(item)
    second = agent.ingest(item)

    assert first is not None
    assert second is None
    assert mock_router.route.call_count == 1
    assert agent._stats["duplicates"] == 1


def test_agent_ingest_many(agent_with_mock_router):
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    agent, mock_router = agent_with_mock_router
    items = [
        IntelligenceItem(
            source_type=SourceType.CVE_FEED,
            raw_content=f"CVE-2024-{i} content",
            title=f"CVE-2024-{i}",
        )
        for i in range(5)
    ]
    routed = agent.ingest_many(items)
    assert len(routed) == 5
    assert mock_router.route.call_count == 5


def test_agent_stats(agent_with_mock_router):
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    agent, _ = agent_with_mock_router
    item = IntelligenceItem(source_type=SourceType.MANUAL, raw_content="test", title="T")
    agent.ingest(item)
    stats = agent.stats()
    assert stats["ingested"] == 1
    assert stats["routed"] == 1


# ── InformationRouter ─────────────────────────────────────────────────────────


@pytest.fixture()
def isolated_router():
    """InformationRouter with all destination adapters mocked."""
    from src.section7.information_router import InformationRouter

    router = InformationRouter()
    router._record_in_observatory = MagicMock(return_value=True)
    router._dispatch_to_cryptex = MagicMock(return_value=True)
    router._catalogue_in_library = MagicMock(return_value=True)
    router._dispatch_to_think_tank = MagicMock(return_value=True)
    return router


@pytest.mark.parametrize(
    "cls_value,expect_obs,expect_cryptex,expect_library,expect_think_tank",
    [
        ("threat", True, True, False, False),
        ("cve", True, True, True, False),  # CVEs go to Cryptex + Library
        ("research", True, False, True, True),
        ("advancement", True, False, True, True),
        ("knowledge", True, False, True, False),
        ("web_scan", True, False, True, False),
        ("unknown", True, False, False, False),
    ],
)
def test_router_routing_rules(
    isolated_router,
    cls_value,
    expect_obs,
    expect_cryptex,
    expect_library,
    expect_think_tank,
):
    from src.section7.information_router import IntelligenceClass

    cls = IntelligenceClass(cls_value)
    result = isolated_router.route(
        item_id="test-123",
        classification=cls,
        summary="test summary",
        payload={"data": "test"},
    )

    assert result.observatory_recorded == expect_obs
    assert result.cryptex_dispatched == expect_cryptex
    assert result.library_catalogued == expect_library
    assert result.think_tank_dispatched == expect_think_tank


def test_router_observatory_always_first(isolated_router):
    """Observatory must be called even when downstream hubs return failure."""
    call_order = []

    def track_obs(*a, **kw):
        call_order.append("observatory")
        return True

    def track_cryptex(*a, **kw):
        call_order.append("cryptex")
        return False  # failure, but no exception — that's the adapter's responsibility

    isolated_router._record_in_observatory = track_obs
    isolated_router._dispatch_to_cryptex = track_cryptex

    from src.section7.information_router import IntelligenceClass

    result = isolated_router.route(
        item_id="fail-123",
        classification=IntelligenceClass.THREAT,
        summary="test",
        payload={},
    )
    assert call_order[0] == "observatory", "Observatory must be called first"
    assert call_order[1] == "cryptex"
    assert result.observatory_recorded is True
    assert result.cryptex_dispatched is False


def test_router_success_requires_observatory(isolated_router):
    """RoutingResult.success = False if Observatory fails."""
    isolated_router._record_in_observatory = MagicMock(return_value=False)

    from src.section7.information_router import IntelligenceClass

    result = isolated_router.route(
        item_id="no-obs",
        classification=IntelligenceClass.KNOWLEDGE,
        summary="test",
        payload={},
    )
    assert result.success is False


def test_router_stats(isolated_router):
    from src.section7.information_router import IntelligenceClass

    for i in range(3):
        isolated_router.route(
            item_id=f"stat-{i}",
            classification=IntelligenceClass.KNOWLEDGE,
            summary="stats test",
            payload={},
        )
    stats = isolated_router.stats()
    assert stats["total_routed"] == 3
    assert stats["successes"] == 3


def test_router_route_many(isolated_router):

    items = [
        {
            "id": f"item-{i}",
            "classification": "knowledge",
            "summary": f"item {i}",
            "payload": {},
        }
        for i in range(4)
    ]
    results = isolated_router.route_many(items)
    assert len(results) == 4
    assert all(r.success for r in results)


# ── CveScanner (mocked network) ───────────────────────────────────────────────


def test_cve_scanner_instantiates():
    from src.cryptex.cve_scanner import CveScanner

    scanner = CveScanner()
    assert scanner is not None


def test_cve_scanner_handles_network_failure():
    """CveScanner.fetch_cves() must return empty list, not raise, on network failure."""
    from src.cryptex.cve_scanner import CveScanner

    scanner = CveScanner(opencve_base_url="http://127.0.0.1:19999")  # unreachable
    items = scanner.fetch_cves(max_cves=5)
    assert isinstance(items, list)  # graceful degradation


def test_cve_risk_profile_fields():
    from src.cryptex.cve_scanner import CveRiskProfile

    p = CveRiskProfile(
        cve_id="CVE-2024-1234",
        severity="HIGH",
        cvss_score=8.5,
        cryptex_signals=2,
        mitigation_actions=["ALERT", "BLOCK"],
        summary="critical RCE",
    )
    assert p.cve_id == "CVE-2024-1234"
    assert p.cvss_score == 8.5
    assert "ALERT" in p.mitigation_actions
    assert p.routed is False
    assert p.error is None


def test_cve_scanner_analyse_items_with_mock_cryptex():
    """analyse_items should produce risk profiles using Cryptex signals."""
    from src.cryptex.cve_scanner import CveScanner
    from src.section7.intelligence_agent import IntelligenceItem, SourceType

    items = [
        IntelligenceItem(
            source_type=SourceType.CVE_FEED,
            raw_content="CVE-2024-9999 remote code execution exploit",
            title="CVE-2024-9999",
            metadata={"cve_id": "CVE-2024-9999", "severity": "CRITICAL", "cvss_score": 9.8},
        ),
    ]

    mock_signal = MagicMock()
    mock_signal.action = MagicMock()
    mock_signal.action.value = "BLOCK"
    mock_cryptex = MagicMock()
    mock_cryptex.analyse.return_value = [mock_signal]

    with patch("src.cryptex.threat_detector.get_cryptex", return_value=mock_cryptex):
        scanner = CveScanner()
        profiles = scanner.analyse_items(items)

    assert len(profiles) == 1
    assert profiles[0].cve_id == "CVE-2024-9999"
    assert profiles[0].severity == "CRITICAL"
    assert profiles[0].cryptex_signals == 1
    assert "BLOCK" in profiles[0].mitigation_actions


# ── NVD / CISA Ingestor Unit Tests (no network) ───────────────────────────────


def test_nvd_ingestor_parse_empty():
    """NvdFeedIngestor._fetch_records() returns [] when network fails."""
    from src.section7.cve_ingester import NvdFeedIngestor

    ingestor = NvdFeedIngestor(feed_url="http://127.0.0.1:19999/nonexistent.json.gz")
    records = ingestor._fetch_records()
    assert records == []


def test_cisa_kev_ingestor_parse_empty():
    from src.section7.cve_ingester import CisaKevIngestor

    ingestor = CisaKevIngestor(url="http://127.0.0.1:19999/kev.json")
    records = ingestor._fetch_records()
    assert records == []


def test_opencve_ingestor_parse_empty():
    from src.section7.cve_ingester import OpenCveCompatIngestor

    ingestor = OpenCveCompatIngestor(base_url="http://127.0.0.1:19999")
    records = ingestor._fetch_records()
    assert records == []


def test_nvd_parse_item():
    """Verify NVD JSON item parsing produces a correctly structured CveRecord."""
    from src.section7.cve_ingester import NvdFeedIngestor

    sample = {
        "cve": {
            "CVE_data_meta": {"ID": "CVE-2024-12345"},
            "description": {
                "description_data": [{"lang": "en", "value": "A critical RCE vulnerability."}],
            },
            "references": {"reference_data": [{"url": "https://example.com/advisory"}]},
        },
        "impact": {"baseMetricV3": {"cvssV3": {"baseSeverity": "CRITICAL", "baseScore": 9.8}}},
        "publishedDate": "2024-01-15T00:00Z",
        "configurations": {"nodes": []},
    }
    record = NvdFeedIngestor._parse_nvd_item(sample)
    assert record.cve_id == "CVE-2024-12345"
    assert record.severity == "CRITICAL"
    assert record.cvss_score == 9.8
    assert "A critical RCE" in record.description
    assert record.references == ["https://example.com/advisory"]


# ── vault-service AES-256-GCM fix ────────────────────────────────────────────


@pytest.fixture()
def vault_worker(monkeypatch):
    """Import vault-service worker with AES key set, isolated from real DB."""
    import importlib
    import tempfile

    monkeypatch.setenv("VAULT_MASTER_KEY", "test-master-key-section7-fix-xyz")
    monkeypatch.setenv("VAULT_DB_PATH", tempfile.mktemp(suffix=".db"))

    mod = importlib.import_module("workers.vault-service.worker")
    return mod


def test_vault_service_encrypt_decrypt_roundtrip(vault_worker):
    """AES-256-GCM encrypt then decrypt must recover plaintext."""
    vs = vault_worker
    plaintext = "super-secret-api-key-12345"
    ciphertext = vs._encrypt_secret(plaintext)

    assert ciphertext != plaintext
    assert len(ciphertext) > 60 * 2  # hex of at least 60 bytes

    recovered = vs._decrypt_secret(ciphertext)
    assert recovered == plaintext


def test_vault_service_encrypt_is_nondeterministic(vault_worker):
    """Each encryption call must produce a different ciphertext (random IV + salt)."""
    vs = vault_worker
    c1 = vs._encrypt_secret("same-plaintext")
    c2 = vs._encrypt_secret("same-plaintext")
    assert c1 != c2  # different random salt + IV each time


def test_vault_service_tamper_detection(vault_worker):
    """Modified ciphertext must raise an exception (GCM authentication tag check)."""
    vs = vault_worker
    ciphertext = vs._encrypt_secret("secret value")
    # Flip a byte in the ciphertext portion
    raw = bytearray(bytes.fromhex(ciphertext))
    raw[-1] ^= 0xFF
    tampered = raw.hex()

    with pytest.raises(Exception):
        vs._decrypt_secret(tampered)


def test_vault_service_no_xor_in_crypto_path(vault_worker):
    """Verify the deprecated _xor_encrypt is no longer present."""
    vs = vault_worker
    assert not hasattr(vs, "_xor_encrypt"), (
        "_xor_encrypt still present — XOR cipher not fully removed"
    )


def test_vault_service_short_ciphertext_raises(vault_worker):
    """Ciphertext shorter than minimum (60 bytes) must raise ValueError."""
    vs = vault_worker
    with pytest.raises(ValueError, match="ciphertext too short"):
        vs._decrypt_secret("deadbeef")  # way too short
