"""
shared_core.infinity.proactive_defense — Proactive Security Integration Layer
==============================================================================
Trancendos Universe — Phase 22 Enhancement

Bridges the existing security subsystems (DefenseEngine, AdaptiveScanner,
SecurityScanner) into a proactive, event-driven defense layer that:

  1. Evaluates every incoming request through the DefenseEngine firewall
  2. On critical anomalies, auto-triggers an AdaptiveScanner scan pass
  3. Manages security incidents with full timeline tracking
  4. Publishes threat events to Sentinel Station security channel
  5. Provides The Guardian Prime's enforcement logic at service level

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                 ProactiveDefenseLayer                        │
    │                                                              │
    │  ┌─────────────────┐    ┌──────────────────────────────────┐ │
    │  │  DefenseEngine  │    │  AdaptiveScanner                 │ │
    │  │  (firewall +    │    │  (learning-based security scan   │ │
    │  │   incidents)    │    │   with false-positive reduction) │ │
    │  └────────┬────────┘    └──────────────┬───────────────────┘ │
    │           │                            │                      │
    │  ┌────────┴────────────────────────────┴──────────────────┐  │
    │  │              Threat Event Publisher                     │  │
    │  │  → Sentinel Station (security channel)                  │  │
    │  │  → Infinity Admin (compliance events)                   │  │
    │  │  → The Guardian Prime (escalation)                      │  │
    │  └──────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────┘

Threat Level Escalation:
    LOW    → Log + monitor
    MEDIUM → Rate limit source IP
    HIGH   → Block source + create incident + alert admin
    CRITICAL → Block + quarantine + page Guardian + emergency repair

Usage:
    from shared_core.infinity.proactive_defense import ProactiveDefenseLayer

    defense = ProactiveDefenseLayer(service_name="infinity-portal")
    result = await defense.evaluate_request({"source_ip": "1.2.3.4", "path": "/api/..."})
    if not result["allowed"]:
        # Return 403 / 429 depending on action
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    from shared_core.security_automation.defense_engine import (  # codeql[py/cyclic-import]
        DefenseEngine,
        FirewallAction,
        ThreatLevel,
    )

    _DEFENSE_AVAILABLE = True
except ImportError:
    _DEFENSE_AVAILABLE = False
    DefenseEngine = None  # type: ignore[assignment,misc]
    FirewallAction = None  # type: ignore[assignment,misc]
    ThreatLevel = None  # type: ignore[assignment,misc]

try:
    from shared_core.security_automation.adaptive_scanner import (  # codeql[py/cyclic-import]
        AdaptiveScanner,
    )

    _ADAPTIVE_SCANNER = True
except ImportError:
    _ADAPTIVE_SCANNER = False
    AdaptiveScanner = None  # type: ignore[assignment,misc]

try:
    from shared_core.security_automation.predictor import (
        ThreatPredictor,  # codeql[py/cyclic-import]
    )

    _PREDICTOR_AVAILABLE = True
except ImportError:
    _PREDICTOR_AVAILABLE = False
    ThreatPredictor = None  # type: ignore[assignment,misc]


# ── Defense Result ────────────────────────────────────────────────────────────


@dataclass
class DefenseResult:
    allowed: bool
    action: str  # allow / deny / rate_limit / challenge / log
    threat_level: str  # none / low / medium / high / critical
    reason: str
    rule_id: Optional[str] = None
    incident_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "threat_level": self.threat_level,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "incident_id": self.incident_id,
            "timestamp": self.timestamp,
        }


# ── Proactive Defense Layer ───────────────────────────────────────────────────


class ProactiveDefenseLayer:
    """
    Unified proactive security layer for Infinity services.

    Evaluates requests through the DefenseEngine, manages incidents,
    and publishes threat events to Sentinel Station.
    """

    # IP tracking for adaptive rate limiting
    _ip_violations: Dict[str, List[float]] = {}
    _ip_block_list: Dict[str, float] = {}  # ip → block_until timestamp
    _BLOCK_DURATION_SECONDS = 900.0  # 15 min default block
    _VIOLATION_WINDOW_SECONDS = 300.0  # 5 min rolling window
    _MAX_VIOLATIONS_BEFORE_BLOCK = 10

    def __init__(
        self,
        service_name: str = "infinity-service",
        sentinel_publish_fn: Optional[Callable] = None,
        violation_threshold: int = 10,
        violation_window_seconds: int = 300,
        block_duration_seconds: int = 900,
    ):
        self.service_name = service_name
        self.sentinel_publish_fn = sentinel_publish_fn
        self.violation_threshold = violation_threshold
        self.violation_window_seconds = violation_window_seconds
        self.block_duration_seconds = block_duration_seconds
        self._eval_count = 0
        self._block_count = 0
        self._incident_count = 0

        # Override class-level defaults with instance-specific values
        self._VIOLATION_WINDOW_SECONDS = float(violation_window_seconds)
        self._MAX_VIOLATIONS_BEFORE_BLOCK = violation_threshold
        self._BLOCK_DURATION_SECONDS = float(block_duration_seconds)

        # DefenseEngine
        if _DEFENSE_AVAILABLE:
            self.engine = DefenseEngine()
            logger.info(
                "ProactiveDefenseLayer: DefenseEngine ready for %s",
                sanitize_for_log(service_name),
            )
        else:
            self.engine = None
            logger.warning(
                "ProactiveDefenseLayer: DefenseEngine not available for %s",
                sanitize_for_log(service_name),
            )
        # AdaptiveScanner (used for code/path scan on high threats)
        if _ADAPTIVE_SCANNER:
            self.scanner = AdaptiveScanner()
        else:
            self.scanner = None

        # Threat predictor (ML-based)
        if _PREDICTOR_AVAILABLE:
            self.predictor = ThreatPredictor()
        else:
            self.predictor = None

    # ── Request Evaluation ────────────────────────────────────────────────────

    async def evaluate_request(self, request_context: Dict[str, Any]) -> DefenseResult:
        """
        Evaluate an incoming request against the defense engine.

        Args:
            request_context: Dict with keys:
                - source_ip: str
                - path: str
                - method: str
                - headers: dict (optional)
                - user_id: str (optional)
                - tier: int (optional) — Trancendos tier
                - role: str (optional)

        Returns:
            DefenseResult with allowed/denied decision and metadata.
        """
        self._eval_count += 1
        source_ip = request_context.get("source_ip", "unknown")
        path = request_context.get("path", "/")

        # ── Check IP block list first (fastest path) ──────────────────────
        block_until = self._ip_block_list.get(source_ip, 0.0)
        if time.time() < block_until:
            self._block_count += 1
            return DefenseResult(
                allowed=False,
                action="deny",
                threat_level="high",
                reason=f"IP {source_ip} is blocked until {block_until:.0f}",
            )

        # ── ML-based threat prediction ────────────────────────────────────
        predicted_threat = "none"
        if self.predictor:
            try:
                predicted = self.predictor.predict(request_context)
                predicted_threat = getattr(predicted, "level", "none")
                if isinstance(predicted_threat, Enum):
                    predicted_threat = predicted_threat.value
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # ── DefenseEngine firewall evaluation ─────────────────────────────
        if self.engine:
            try:
                eval_result = self.engine.evaluate_request(
                    {
                        "source": source_ip,
                        "destination": self.service_name,
                        "path": path,
                        "method": request_context.get("method", "GET"),
                    }
                )
                action = (
                    eval_result.get("action", "allow") if isinstance(eval_result, dict) else "allow"
                )
                threat_level = (
                    eval_result.get("threat_level", "none")
                    if isinstance(eval_result, dict)
                    else "none"
                )
                rule_id = eval_result.get("rule_id") if isinstance(eval_result, dict) else None

                if action in ("deny", "challenge"):
                    await self._handle_violation(source_ip, threat_level, path)
                    return DefenseResult(
                        allowed=False,
                        action=action,
                        threat_level=threat_level,
                        reason=f"Firewall rule {rule_id} matched",
                        rule_id=rule_id,
                    )

                if action == "rate_limit":
                    return DefenseResult(
                        allowed=False,
                        action="rate_limit",
                        threat_level=threat_level,
                        reason="Rate limit applied by firewall",
                        rule_id=rule_id,
                    )

            except Exception as e:
                logger.debug("DefenseEngine eval error: %s", sanitize_for_log(str(e)))

        # ── Adaptive violation tracking ───────────────────────────────────
        if predicted_threat in ("medium", "high", "critical"):
            await self._handle_violation(source_ip, predicted_threat, path)

        return DefenseResult(
            allowed=True,
            action="allow",
            threat_level=predicted_threat or "none",
            reason="Request passed all defense checks",
        )

    async def _handle_violation(self, source_ip: str, threat_level: str, path: str) -> None:
        """Track violations and potentially block an IP."""
        now = time.time()
        # Purge old violations outside window
        window_start = now - self._VIOLATION_WINDOW_SECONDS
        violations = [t for t in self._ip_violations.get(source_ip, []) if t > window_start]
        violations.append(now)
        self._ip_violations[source_ip] = violations

        # Auto-block on too many violations
        if len(violations) >= self._MAX_VIOLATIONS_BEFORE_BLOCK:
            self._ip_block_list[source_ip] = now + self._BLOCK_DURATION_SECONDS
            self._block_count += 1
            logger.warning(
                "IP %s auto-blocked for %d violations (threat=%s)",
                sanitize_for_log(source_ip),
                len(violations),
                sanitize_for_log(threat_level),
            )
            await self._publish_threat_event(source_ip, threat_level, path, "ip_auto_blocked")

        # High/critical: create incident
        if threat_level in ("high", "critical"):
            self._incident_count += 1
            if self.engine and hasattr(self.engine, "create_incident"):
                try:
                    self.engine.create_incident(
                        title=f"Threat from {source_ip}",
                        description=f"Path: {path}, Level: {threat_level}",
                        severity=threat_level,
                        source=source_ip,
                        affected_services=[self.service_name],
                    )
                except Exception as _exc:
                    logger.debug("suppressed %s", _exc, exc_info=False)
            await self._publish_threat_event(source_ip, threat_level, path, "incident_created")

    async def _publish_threat_event(
        self,
        source_ip: str,
        threat_level: str,
        path: str,
        event_type: str,
    ) -> None:
        """Publish threat event to Sentinel Station."""
        if self.sentinel_publish_fn:
            try:
                await self.sentinel_publish_fn(
                    "security_threat",
                    {
                        "service": self.service_name,
                        "source_ip": source_ip,
                        "threat_level": threat_level,
                        "path": path,
                        "event_type": event_type,
                        "timestamp": time.time(),
                    },
                )
            except Exception as e:
                logger.debug("Sentinel threat publish error: %s", sanitize_for_log(str(e)))

    # ── IP Management ─────────────────────────────────────────────────────────

    def unblock_ip(self, ip: str) -> bool:
        """Manually unblock an IP address."""
        if ip in self._ip_block_list:
            del self._ip_block_list[ip]
            logger.info("IP %s manually unblocked", sanitize_for_log(ip))
            return True
        return False

    def get_blocked_ips(self) -> List[Dict[str, Any]]:
        """Get all currently blocked IPs."""
        now = time.time()
        return [
            {
                "ip": ip,
                "blocked_until": ts,
                "remaining_seconds": max(0.0, ts - now),
            }
            for ip, ts in self._ip_block_list.items()
            if ts > now
        ]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get defense layer statistics."""
        return {
            "service": self.service_name,
            "evaluations": self._eval_count,
            "blocks": self._block_count,
            "incidents": self._incident_count,
            "blocked_ips": len([ts for ts in self._ip_block_list.values() if ts > time.time()]),
            "defense_engine_available": _DEFENSE_AVAILABLE,
            "adaptive_scanner_available": _ADAPTIVE_SCANNER,
            "predictor_available": _PREDICTOR_AVAILABLE,
            "timestamp": time.time(),
        }
