# tests/test_cryptex.py — Tests for src/cryptex/threat_detector.py
"""Comprehensive tests for the Cryptex threat detection engine."""

from __future__ import annotations

import re

from src.cryptex.threat_detector import (
    Cryptex,
    MitigationAction,
    ThreatCategory,
    ThreatRule,
    ThreatSeverity,
    ThreatSignal,
)


# ── Enum tests ──────────────────────────────────────────────────────────────


class TestThreatCategory:
    def test_values(self):
        assert ThreatCategory.INJECTION == "injection"
        assert ThreatCategory.XSS == "xss"
        assert ThreatCategory.BROKEN_AUTH == "broken_auth"
        assert ThreatCategory.SENSITIVE_DATA == "sensitive_data"
        assert ThreatCategory.BROKEN_ACCESS == "broken_access"
        assert ThreatCategory.SSRF == "ssrf"
        assert ThreatCategory.MISCONFIG == "misconfig"
        assert ThreatCategory.OUTDATED_COMPONENT == "outdated_component"
        assert ThreatCategory.LOGGING_FAILURE == "logging_failure"
        assert ThreatCategory.UNKNOWN == "unknown"


class TestThreatSeverity:
    def test_values(self):
        assert ThreatSeverity.INFO == "info"
        assert ThreatSeverity.LOW == "low"
        assert ThreatSeverity.MEDIUM == "medium"
        assert ThreatSeverity.HIGH == "high"
        assert ThreatSeverity.CRITICAL == "critical"


class TestMitigationAction:
    def test_values(self):
        assert MitigationAction.LOG == "log"
        assert MitigationAction.ALERT == "alert"
        assert MitigationAction.RATE_LIMIT == "rate_limit"
        assert MitigationAction.BLOCK == "block"
        assert MitigationAction.ISOLATE == "isolate"


# ── ThreatSignal tests ──────────────────────────────────────────────────────


class TestThreatSignal:
    def test_defaults(self):
        sig = ThreatSignal()
        assert sig.id != ""
        assert sig.timestamp > 0
        assert sig.category == ThreatCategory.UNKNOWN
        assert sig.severity == ThreatSeverity.LOW
        assert sig.source_ip is None
        assert sig.actor is None
        assert sig.target is None
        assert sig.evidence == ""
        assert sig.mitigations == []
        assert sig.resolved is False
        assert sig.metadata == {}

    def test_custom_values(self):
        sig = ThreatSignal(
            category=ThreatCategory.INJECTION,
            severity=ThreatSeverity.HIGH,
            source_ip="1.2.3.4",
            actor="attacker",
            target="/login",
            evidence="UNION SELECT",
            mitigations=[MitigationAction.BLOCK],
        )
        assert sig.category == ThreatCategory.INJECTION
        assert sig.severity == ThreatSeverity.HIGH
        assert sig.source_ip == "1.2.3.4"
        assert sig.mitigations == [MitigationAction.BLOCK]

    def test_to_dict(self):
        sig = ThreatSignal(
            category=ThreatCategory.XSS,
            severity=ThreatSeverity.MEDIUM,
            mitigations=[MitigationAction.LOG],
        )
        d = sig.to_dict()
        assert d["category"] == "xss"
        assert d["severity"] == "medium"
        assert d["mitigations"] == ["log"]
        assert d["resolved"] is False

    def test_evidence_truncation_in_to_dict(self):
        sig = ThreatSignal(evidence="A" * 500)
        d = sig.to_dict()
        assert len(d["evidence_preview"]) == 200


# ── ThreatRule tests ────────────────────────────────────────────────────────


class TestThreatRule:
    def test_pattern_match(self):
        rule = ThreatRule(
            id="test-01",
            name="Test Rule",
            category=ThreatCategory.INJECTION,
            severity=ThreatSeverity.HIGH,
            pattern=re.compile(r"union\s+select", re.IGNORECASE),
        )
        assert rule.matches({"input": "UNION SELECT * FROM users"})

    def test_pattern_no_match(self):
        rule = ThreatRule(
            id="test-02",
            name="Test Rule",
            category=ThreatCategory.INJECTION,
            severity=ThreatSeverity.HIGH,
            pattern=re.compile(r"union\s+select", re.IGNORECASE),
        )
        assert not rule.matches({"input": "hello world"})

    def test_check_function(self):
        rule = ThreatRule(
            id="test-03",
            name="Custom Check",
            category=ThreatCategory.BROKEN_AUTH,
            severity=ThreatSeverity.MEDIUM,
            check=lambda ctx: ctx.get("failed_attempts", 0) > 5,
        )
        assert rule.matches({"failed_attempts": 10})
        assert not rule.matches({"failed_attempts": 3})

    def test_check_exception_returns_false(self):
        rule = ThreatRule(
            id="test-04",
            name="Failing Check",
            category=ThreatCategory.UNKNOWN,
            severity=ThreatSeverity.LOW,
            check=lambda ctx: ctx["missing_key"],  # noqa: B023
        )
        assert not rule.matches({})

    def test_no_matcher_returns_false(self):
        rule = ThreatRule(
            id="test-05",
            name="No Matcher",
            category=ThreatCategory.UNKNOWN,
            severity=ThreatSeverity.INFO,
        )
        assert not rule.matches({"input": "anything"})

    def test_matches_payload_field(self):
        rule = ThreatRule(
            id="test-06",
            name="Payload Check",
            category=ThreatCategory.INJECTION,
            severity=ThreatSeverity.HIGH,
            pattern=re.compile(r"drop\s+table", re.IGNORECASE),
        )
        assert rule.matches({"payload": "DROP TABLE users"})


# ── Cryptex engine tests ────────────────────────────────────────────────────


class TestCryptex:
    def setup_method(self):
        self.engine = Cryptex()

    def test_default_rules_registered(self):
        assert len(self.engine._rules) >= 6

    def test_sqli_detection(self):
        signals = self.engine.analyse({"input": "' UNION SELECT * FROM users --"})
        assert len(signals) >= 1
        assert any(s.category == ThreatCategory.INJECTION for s in signals)

    def test_xss_detection(self):
        signals = self.engine.analyse({"input": "<script>alert('xss')</script>"})
        assert len(signals) >= 1
        assert any(s.category == ThreatCategory.XSS for s in signals)

    def test_command_injection_detection(self):
        signals = self.engine.analyse({"input": "; cat /etc/passwd"})
        assert len(signals) >= 1
        assert any(s.category == ThreatCategory.INJECTION for s in signals)
        assert any(s.severity == ThreatSeverity.CRITICAL for s in signals)

    def test_ssrf_detection(self):
        signals = self.engine.analyse({"input": "http://127.0.0.1/admin"})
        assert len(signals) >= 1
        assert any(s.category == ThreatCategory.SSRF for s in signals)

    def test_path_traversal_detection(self):
        signals = self.engine.analyse({"input": "../../etc/passwd"})
        assert len(signals) >= 1
        assert any(s.category == ThreatCategory.BROKEN_ACCESS for s in signals)

    def test_secret_exposure_detection(self):
        signals = self.engine.analyse({"input": "password=supersecret123"})
        assert len(signals) >= 1
        assert any(s.category == ThreatCategory.SENSITIVE_DATA for s in signals)

    def test_clean_input_no_signals(self):
        signals = self.engine.analyse({"input": "hello world"})
        assert len(signals) == 0

    def test_analyse_request(self):
        signals = self.engine.analyse_request(
            path="/login",
            body="UNION SELECT * FROM users",
            actor="attacker",
            ip="1.2.3.4",
        )
        assert len(signals) >= 1

    def test_block_ip(self):
        self.engine.block_ip("10.0.0.1")
        assert self.engine.is_blocked(ip="10.0.0.1")

    def test_unblock_ip(self):
        self.engine.block_ip("10.0.0.1")
        self.engine.unblock_ip("10.0.0.1")
        assert not self.engine.is_blocked(ip="10.0.0.1")

    def test_is_blocked_actor(self):
        # Manually add a blocked actor via mitigation
        rule = ThreatRule(
            id="test-block",
            name="Block Test",
            category=ThreatCategory.BROKEN_AUTH,
            severity=ThreatSeverity.CRITICAL,
            check=lambda ctx: True,
            mitigations=[MitigationAction.BLOCK],
        )
        engine = Cryptex()
        engine._rules = [rule]  # replace with single rule
        engine.analyse({"input": "test"}, actor="bad-actor", source_ip=None)
        assert engine.is_blocked(actor="bad-actor")

    def test_is_blocked_false(self):
        assert not self.engine.is_blocked(ip="1.1.1.1")
        assert not self.engine.is_blocked(actor="nobody")

    def test_auto_block_via_mitigation(self):
        rule = ThreatRule(
            id="auto-block-test",
            name="Auto Block",
            category=ThreatCategory.INJECTION,
            severity=ThreatSeverity.CRITICAL,
            check=lambda ctx: True,
            mitigations=[MitigationAction.BLOCK],
        )
        engine = Cryptex()
        engine._rules = [rule]
        engine.analyse({"input": "trigger"}, source_ip="9.9.9.9")
        assert engine.is_blocked(ip="9.9.9.9")

    def test_recent_signals(self):
        self.engine.analyse({"input": "UNION SELECT * FROM users"})
        signals = self.engine.recent_signals(limit=10)
        assert len(signals) >= 1

    def test_recent_signals_with_severity_filter(self):
        self.engine.analyse({"input": "hello world"})
        self.engine.analyse({"input": "UNION SELECT * FROM users"})
        high_signals = self.engine.recent_signals(min_severity=ThreatSeverity.HIGH)
        assert all(
            s.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL) for s in high_signals
        )

    def test_stats_empty(self):
        engine = Cryptex()
        # Default rules exist but no signals yet
        stats = engine.stats()
        assert stats["total_signals"] == 0
        assert stats["blocked_ips"] == 0
        assert stats["blocked_actors"] == 0
        assert stats["rules_active"] >= 6

    def test_stats_populated(self):
        self.engine.analyse({"input": "UNION SELECT * FROM users"})
        stats = self.engine.stats()
        assert stats["total_signals"] >= 1
        assert "by_category" in stats
        assert "by_severity" in stats
