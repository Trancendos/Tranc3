# Dimensional/security_automation/defense_engine.py — Active Defense & Firewall Engine
# Ported from the-citadel/src/defense/defense-engine.ts (TypeScript → Python)
#
# Features:
#   - Priority-based firewall rule evaluation
#   - Security incident management with timeline tracking
#   - Threat level assessment (none → critical)
#   - Default firewall rules seeded on initialization
#   - Request evaluation: allow, deny, rate_limit, challenge, log
#   - Zero external dependencies

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class FirewallAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    RATE_LIMIT = "rate_limit"
    CHALLENGE = "challenge"
    LOG = "log"


@dataclass
class FirewallRule:
    """A single firewall rule with priority-based matching."""

    id: str
    name: str
    description: str
    priority: int
    source: str = "*"
    destination: str = "*"
    port: Optional[int] = None
    protocol: str = "any"
    action: FirewallAction = FirewallAction.ALLOW
    enabled: bool = True
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "source": self.source,
            "destination": self.destination,
            "port": self.port,
            "protocol": self.protocol,
            "action": self.action.value,
            "enabled": self.enabled,
            "hitCount": self.hit_count,
        }


@dataclass
class IncidentEvent:
    """An event in a security incident's timeline."""

    id: str
    timestamp: float
    actor: str
    action: str
    details: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "details": self.details,
        }


@dataclass
class SecurityIncident:
    """A tracked security incident with timeline."""

    id: str
    title: str
    description: str
    severity: ThreatLevel
    status: IncidentStatus = IncidentStatus.OPEN
    source: str = ""
    affected_services: List[str] = field(default_factory=list)
    timeline: List[IncidentEvent] = field(default_factory=list)
    assigned_to: str = ""
    resolved_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "source": self.source,
            "affectedServices": self.affected_services,
            "timeline": [e.to_dict() for e in self.timeline],
            "assignedTo": self.assigned_to,
            "resolvedAt": self.resolved_at,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class DefenseStats:
    """Aggregate defense statistics."""

    current_threat_level: ThreatLevel = ThreatLevel.NONE
    total_incidents: int = 0
    open_incidents: int = 0
    resolved_incidents: int = 0
    firewall_rules: int = 0
    blocked_requests: int = 0
    allowed_requests: int = 0
    last_incident_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currentThreatLevel": self.current_threat_level.value,
            "totalIncidents": self.total_incidents,
            "openIncidents": self.open_incidents,
            "resolvedIncidents": self.resolved_incidents,
            "firewallRules": self.firewall_rules,
            "blockedRequests": self.blocked_requests,
            "allowedRequests": self.allowed_requests,
            "lastIncidentAt": self.last_incident_at,
        }


class DefenseEngine:
    """
    Active defense engine with firewall rules and incident management.

    Ported from the-citadel's DefenseEngine TypeScript class.
    Provides priority-based firewall rule evaluation, security incident
    tracking with timeline, and automatic threat level assessment.

    Usage:
        engine = DefenseEngine()
        result = engine.evaluate_request("external", "/api/data")
        if result["action"] == "deny":
            raise HTTPException(status_code=403)
    """

    def __init__(self):
        self._firewall_rules: Dict[str, FirewallRule] = {}
        self._incidents: Dict[str, SecurityIncident] = {}
        self._blocked_count = 0
        self._allowed_count = 0
        self._seed_default_firewall_rules()
        logger.info("DefenseEngine initialized with %d default rules", len(self._firewall_rules))

    # ─── Firewall ────────────────────────────────────────────

    def add_rule(
        self,
        name: str,
        description: str,
        priority: int,
        action: FirewallAction = FirewallAction.ALLOW,
        source: str = "*",
        destination: str = "*",
        port: Optional[int] = None,
        protocol: str = "any",
        enabled: bool = True,
    ) -> FirewallRule:
        """Add a new firewall rule."""
        rule = FirewallRule(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            priority=priority,
            source=source,
            destination=destination,
            port=port,
            protocol=protocol,
            action=action,
            enabled=enabled,
        )
        self._firewall_rules[rule.id] = rule
        logger.info(
            "Firewall rule added: %s (priority=%d, action=%s)",
            sanitize_for_log(name),
            priority,
            action.value,
        )
        return rule

    def evaluate_request(
        self,
        source: str,
        destination: str,
        port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a request against all enabled firewall rules.

        Rules are evaluated in priority order (lowest first).
        First matching rule wins.

        Returns:
            Dict with keys: action (FirewallAction value), rule_id, reason
        """
        rules = sorted(
            [r for r in self._firewall_rules.values() if r.enabled],
            key=lambda r: r.priority,
        )

        for rule in rules:
            source_match = rule.source == "*" or source == rule.source or source in rule.source
            dest_match = (
                rule.destination == "*"
                or destination == rule.destination
                or destination in rule.destination
            )
            port_match = rule.port is None or rule.port == port

            if source_match and dest_match and port_match:
                rule.hit_count += 1
                if rule.action in (FirewallAction.DENY, FirewallAction.RATE_LIMIT):
                    self._blocked_count += 1
                else:
                    self._allowed_count += 1
                return {
                    "action": rule.action.value,
                    "rule_id": rule.id,
                    "reason": rule.name,
                }

        self._allowed_count += 1
        return {"action": "allow", "rule_id": None, "reason": "Default allow — no matching rule"}

    def get_rules(self, enabled_only: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get all firewall rules, optionally filtered by enabled status."""
        rules = list(self._firewall_rules.values())
        if enabled_only is not None:
            rules = [r for r in rules if r.enabled == enabled_only]
        return [r.to_dict() for r in sorted(rules, key=lambda r: r.priority)]

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a firewall rule by ID."""
        return self._firewall_rules.pop(rule_id, None) is not None

    def toggle_rule(self, rule_id: str) -> bool:
        """Toggle a firewall rule's enabled status."""
        rule = self._firewall_rules.get(rule_id)
        if not rule:
            return False
        rule.enabled = not rule.enabled
        return True

    # ─── Incidents ───────────────────────────────────────────

    def create_incident(
        self,
        title: str,
        description: str,
        severity: ThreatLevel,
        source: str = "",
        affected_services: Optional[List[str]] = None,
    ) -> SecurityIncident:
        """Create a new security incident."""
        incident = SecurityIncident(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            severity=severity,
            source=source,
            affected_services=affected_services or [],
            timeline=[
                IncidentEvent(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    actor="system",
                    action="created",
                    details="Incident created",
                )
            ],
        )
        self._incidents[incident.id] = incident
        logger.warning(
            "Security incident created: %s (severity=%s)",
            sanitize_for_log(title),
            severity.value,
        )
        return incident

    def update_incident(
        self,
        incident_id: str,
        status: Optional[IncidentStatus] = None,
        assigned_to: Optional[str] = None,
        note: Optional[str] = None,
        actor: str = "system",
    ) -> Optional[SecurityIncident]:
        """Update a security incident's status and add timeline events."""
        incident = self._incidents.get(incident_id)
        if not incident:
            return None

        if status:
            incident.status = status
            if status == IncidentStatus.RESOLVED:
                incident.resolved_at = time.time()

        if assigned_to:
            incident.assigned_to = assigned_to

        if note:
            incident.timeline.append(
                IncidentEvent(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    actor=actor,
                    action="updated",
                    details=note,
                )
            )

        incident.updated_at = time.time()
        return incident

    def get_incidents(
        self,
        status: Optional[IncidentStatus] = None,
    ) -> List[Dict[str, Any]]:
        """Get all incidents, optionally filtered by status."""
        incidents = list(self._incidents.values())
        if status:
            incidents = [i for i in incidents if i.status == status]
        incidents.sort(key=lambda i: i.created_at, reverse=True)
        return [i.to_dict() for i in incidents]

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get a single incident by ID."""
        incident = self._incidents.get(incident_id)
        return incident.to_dict() if incident else None

    # ─── Threat Assessment ───────────────────────────────────

    def get_current_threat_level(self) -> ThreatLevel:
        """Assess current threat level based on open incidents."""
        open_incidents = [
            i
            for i in self._incidents.values()
            if i.status in (IncidentStatus.OPEN, IncidentStatus.INVESTIGATING)
        ]
        if any(i.severity == ThreatLevel.CRITICAL for i in open_incidents):
            return ThreatLevel.CRITICAL
        if any(i.severity == ThreatLevel.HIGH for i in open_incidents):
            return ThreatLevel.HIGH
        if any(i.severity == ThreatLevel.MEDIUM for i in open_incidents):
            return ThreatLevel.MEDIUM
        if any(i.severity == ThreatLevel.LOW for i in open_incidents):
            return ThreatLevel.LOW
        return ThreatLevel.NONE

    def get_stats(self) -> DefenseStats:
        """Get aggregate defense statistics."""
        incidents = list(self._incidents.values())
        last_incident = max((i.created_at for i in incidents), default=None) if incidents else None

        return DefenseStats(
            current_threat_level=self.get_current_threat_level(),
            total_incidents=len(incidents),
            open_incidents=sum(
                1
                for i in incidents
                if i.status in (IncidentStatus.OPEN, IncidentStatus.INVESTIGATING)
            ),
            resolved_incidents=sum(
                1 for i in incidents if i.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)
            ),
            firewall_rules=len(self._firewall_rules),
            blocked_requests=self._blocked_count,
            allowed_requests=self._allowed_count,
            last_incident_at=last_incident,
        )

    # ─── Private ─────────────────────────────────────────────

    def _seed_default_firewall_rules(self) -> None:
        """Seed default firewall rules for basic security posture."""
        defaults = [
            {
                "name": "Block external access to internal ports",
                "description": "Deny external traffic to agent/service ports",
                "priority": 1,
                "source": "external",
                "destination": "internal",
                "action": FirewallAction.DENY,
            },
            {
                "name": "Allow health checks",
                "description": "Allow health check endpoints from any source",
                "priority": 2,
                "destination": "/health",
                "action": FirewallAction.ALLOW,
            },
            {
                "name": "Rate limit API endpoints",
                "description": "Rate limit public API access to prevent abuse",
                "priority": 5,
                "destination": "/api/",
                "action": FirewallAction.RATE_LIMIT,
            },
            {
                "name": "Allow internal agent communication",
                "description": "Allow all internal agent-to-agent traffic",
                "priority": 10,
                "source": "internal",
                "destination": "internal",
                "action": FirewallAction.ALLOW,
            },
            {
                "name": "Log all denied requests",
                "description": "Log denied requests for audit trail",
                "priority": 100,
                "action": FirewallAction.LOG,
            },
        ]

        for d in defaults:
            self.add_rule(**d)  # type: ignore[arg-type]


# Singleton instance for global use
defense_engine = DefenseEngine()
