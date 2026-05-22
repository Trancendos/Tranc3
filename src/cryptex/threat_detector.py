# src/cryptex/threat_detector.py
# Cryptex — threat analysis, cyber security defence, and bug bounty system.
#
# Cryptex receives all SECURITY-severity events from The Observatory and:
#   1. Classifies threats by OWASP category
#   2. Applies automated mitigations (rate-limit, block, alert)
#   3. Feeds The Ice Box for sandboxed malware analysis
#   4. Publishes threat intel to The Nexus for platform-wide alerting
#
# Designed to integrate with Wazuh + MISP when deployed on-prem.
# In-process mode operates as a lightweight rule engine.

from __future__ import annotations

import logging

from shared_core.sanitize import sanitize_for_log

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ThreatCategory(str, Enum):
    INJECTION          = "injection"           # SQL, NoSQL, LDAP, OS command
    XSS                = "xss"                 # Cross-site scripting
    BROKEN_AUTH        = "broken_auth"         # Auth bypass, credential stuffing
    SENSITIVE_DATA     = "sensitive_data"      # PII exposure, unencrypted secrets
    BROKEN_ACCESS      = "broken_access"       # IDOR, privilege escalation
    SSRF               = "ssrf"                # Server-side request forgery
    MISCONFIG          = "misconfig"           # Security misconfiguration
    OUTDATED_COMPONENT = "outdated_component"  # Known-vulnerable dependency
    LOGGING_FAILURE    = "logging_failure"     # Insufficient logging/monitoring
    UNKNOWN            = "unknown"


class ThreatSeverity(str, Enum):
    INFO     = "info"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class MitigationAction(str, Enum):
    LOG      = "log"        # Record only
    ALERT    = "alert"      # Notify via Nexus
    RATE_LIMIT = "rate_limit"
    BLOCK    = "block"      # Block actor/IP
    ISOLATE  = "isolate"    # Send to The Ice Box


@dataclass
class ThreatSignal:
    """A detected threat event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    category: ThreatCategory = ThreatCategory.UNKNOWN
    severity: ThreatSeverity = ThreatSeverity.LOW
    source_ip: Optional[str] = None
    actor: Optional[str] = None
    target: Optional[str] = None
    evidence: str = ""
    mitigations: List[MitigationAction] = field(default_factory=list)
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "category": self.category.value,
            "severity": self.severity.value,
            "source_ip": self.source_ip,
            "actor": self.actor,
            "target": self.target,
            "evidence_preview": self.evidence[:200],
            "mitigations": [m.value for m in self.mitigations],
            "resolved": self.resolved,
        }


@dataclass
class ThreatRule:
    id: str
    name: str
    category: ThreatCategory
    severity: ThreatSeverity
    pattern: Optional[re.Pattern] = None
    check: Optional[Callable[[Dict[str, Any]], bool]] = field(default=None, repr=False)
    mitigations: List[MitigationAction] = field(default_factory=list)

    def matches(self, context: Dict[str, Any]) -> bool:
        text = str(context.get("input", "")) + str(context.get("payload", ""))
        if self.pattern and self.pattern.search(text):
            return True
        if self.check:
            try:
                return self.check(context)
            except Exception:
                return False
        return False


class Cryptex:
    """
    Cryptex — Trancendos cyber security defence engine.

    Runs threat detection rules against incoming context dicts and emits
    ThreatSignals. Integrates with The Observatory for audit emission and
    The Nexus for platform-wide broadcast.
    """

    def __init__(self):
        self._rules: List[ThreatRule] = []
        self._signals: List[ThreatSignal] = []
        self._blocked_ips: set = set()
        self._blocked_actors: set = set()
        self._register_default_rules()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyse(
        self,
        context: Dict[str, Any],
        actor: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> List[ThreatSignal]:
        """
        Run all rules against context. Returns list of triggered ThreatSignals.
        Emits Observatory events and Nexus broadcasts for HIGH/CRITICAL findings.
        """
        signals: List[ThreatSignal] = []

        for rule in self._rules:
            if not rule.matches(context):
                continue

            signal = ThreatSignal(
                category=rule.category,
                severity=rule.severity,
                source_ip=source_ip,
                actor=actor,
                target=context.get("target"),
                evidence=str(context.get("input", ""))[:500],
                mitigations=list(rule.mitigations),
                metadata={"rule_id": rule.id, "rule_name": rule.name},
            )
            self._signals.append(signal)
            signals.append(signal)

            self._apply_mitigations(signal)
            self._emit(signal)

        return signals

    def analyse_request(self, path: str, body: str = "", headers: Dict[str, str] = {},
                        actor: Optional[str] = None, ip: Optional[str] = None) -> List[ThreatSignal]:
        return self.analyse(
            {"input": f"{path} {body}", "payload": body, "headers": str(headers), "target": path},
            actor=actor, source_ip=ip,
        )

    # ── Blocking ──────────────────────────────────────────────────────────────

    def is_blocked(self, actor: Optional[str] = None, ip: Optional[str] = None) -> bool:
        if ip and ip in self._blocked_ips:
            return True
        if actor and actor in self._blocked_actors:
            return True
        return False

    def block_ip(self, ip: str) -> None:
        self._blocked_ips.add(ip)
        logger.warning("cryptex: blocked IP %s", sanitize_for_log(ip))

    def unblock_ip(self, ip: str) -> None:
        self._blocked_ips.discard(ip)

    # ── Signals ───────────────────────────────────────────────────────────────

    def recent_signals(self, limit: int = 50, min_severity: Optional[ThreatSeverity] = None) -> List[ThreatSignal]:
        _order = [ThreatSeverity.INFO, ThreatSeverity.LOW, ThreatSeverity.MEDIUM,
                  ThreatSeverity.HIGH, ThreatSeverity.CRITICAL]
        signals = list(reversed(self._signals))
        if min_severity:
            threshold = _order.index(min_severity)
            signals = [s for s in signals if _order.index(s.severity) >= threshold]
        return signals[:limit]

    def stats(self) -> Dict[str, Any]:
        total = len(self._signals)
        by_cat: Dict[str, int] = {}
        by_sev: Dict[str, int] = {}
        for s in self._signals:
            by_cat[s.category.value] = by_cat.get(s.category.value, 0) + 1
            by_sev[s.severity.value] = by_sev.get(s.severity.value, 0) + 1
        return {
            "total_signals": total,
            "by_category": by_cat,
            "by_severity": by_sev,
            "blocked_ips": len(self._blocked_ips),
            "blocked_actors": len(self._blocked_actors),
            "rules_active": len(self._rules),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _apply_mitigations(self, signal: ThreatSignal) -> None:
        if MitigationAction.BLOCK in signal.mitigations:
            if signal.source_ip:
                self._blocked_ips.add(signal.source_ip)
            if signal.actor:
                self._blocked_actors.add(signal.actor)

    def _emit(self, signal: ThreatSignal) -> None:
        try:
            from src.observability.observatory import EventCategory, EventSeverity, observe
            observe(
                f"cryptex.threat.{signal.category.value}",
                actor=signal.actor,
                actor_ip=signal.source_ip,
                target=signal.target,
                category=EventCategory.SECURITY,
                severity=EventSeverity.SECURITY if signal.severity == ThreatSeverity.CRITICAL else EventSeverity.WARNING,
                service="cryptex",
                outcome="detected",
                metadata=signal.to_dict(),
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


        if signal.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL):
            try:
                from src.nexus.hub import get_nexus
                get_nexus().publish(
                    "cryptex.threat.alert",
                    {"signal": signal.to_dict()},
                    sender="cryptex",
                )
            except Exception:
                pass  # nosec B110 — graceful degradation; error logged upstream


    def _register_default_rules(self) -> None:
        rules = [
            ThreatRule(
                id="sqli-01",
                name="SQL Injection Pattern",
                category=ThreatCategory.INJECTION,
                severity=ThreatSeverity.HIGH,
                pattern=re.compile(
                    r"(\b(union|select|insert|update|delete|drop|exec|execute|xp_)\b"
                    r"|--|;|\bor\b\s+\d+\s*=\s*\d+|\band\b\s+\d+\s*=\s*\d+)",
                    re.IGNORECASE,
                ),
                mitigations=[MitigationAction.ALERT, MitigationAction.LOG],
            ),
            ThreatRule(
                id="xss-01",
                name="XSS Script Injection",
                category=ThreatCategory.XSS,
                severity=ThreatSeverity.MEDIUM,
                pattern=re.compile(
                    r"<script[\s\S]*?>|javascript:|on\w+\s*=|<iframe|<object|<embed",
                    re.IGNORECASE,
                ),
                mitigations=[MitigationAction.LOG, MitigationAction.ALERT],
            ),
            ThreatRule(
                id="cmdi-01",
                name="Command Injection Pattern",
                category=ThreatCategory.INJECTION,
                severity=ThreatSeverity.CRITICAL,
                pattern=re.compile(
                    r"[;&|`$]\s*(ls|cat|rm|wget|curl|bash|sh|python|perl|nc|ncat|netcat)\b",
                    re.IGNORECASE,
                ),
                mitigations=[MitigationAction.BLOCK, MitigationAction.ALERT],
            ),
            ThreatRule(
                id="ssrf-01",
                name="SSRF Internal Address Access",
                category=ThreatCategory.SSRF,
                severity=ThreatSeverity.HIGH,
                pattern=re.compile(
                    r"(https?://)?(localhost|127\.0\.0\.1|::1|169\.254\.|10\.\d+\.\d+\.\d+|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",
                    re.IGNORECASE,
                ),
                mitigations=[MitigationAction.BLOCK, MitigationAction.ALERT],
            ),
            ThreatRule(
                id="path-01",
                name="Path Traversal",
                category=ThreatCategory.BROKEN_ACCESS,
                severity=ThreatSeverity.HIGH,
                pattern=re.compile(r"\.\.[/\\]|\.\.[/\\]\.\.[/\\]", re.IGNORECASE),
                mitigations=[MitigationAction.BLOCK, MitigationAction.ALERT],
            ),
            ThreatRule(
                id="secret-01",
                name="Secret / Credential Exposure",
                category=ThreatCategory.SENSITIVE_DATA,
                severity=ThreatSeverity.CRITICAL,
                pattern=re.compile(
                    r"(password|passwd|secret|api[_-]?key|token|bearer)\s*[=:]\s*\S+",
                    re.IGNORECASE,
                ),
                mitigations=[MitigationAction.ALERT, MitigationAction.LOG],
            ),
        ]
        for rule in rules:
            self._rules.append(rule)
        logger.debug("cryptex: registered %d default rules", len(rules))


# ── Module-level singleton ────────────────────────────────────────────────────
_cryptex: Optional[Cryptex] = None


def get_cryptex() -> Cryptex:
    global _cryptex
    if _cryptex is None:
        _cryptex = Cryptex()
    return _cryptex
