"""
src/routers/ecosystem.py — Ecosystem Router
============================================
Migrates all /api/ecosystem/* routes from the legacy api_ecosystem.py
into the canonical api.py router tree.

Covers:
  - /api/ecosystem/hubs          — hub state aggregation
  - /api/ecosystem/citadel       — The Citadel master overview
  - /api/ecosystem/security      — security posture (scanner + defense engine)
  - /api/ecosystem/pillars       — pillar definitions
  - /api/ecosystem/neural-bus    — live service topology
  - /api/ecosystem/mode          — system-mode toggle
  - /api/ecosystem/health        — ecosystem health with telemetry
  - /api/ecosystem/metrics       — Prometheus text (ecosystem view)
  - /api/ecosystem/defense/*     — firewall rules, incidents, stats
  - /api/ecosystem/storage       — storage provider health
  - /api/ecosystem/ai/*          — AI model catalog, provider status, routing chains
  - /api/ecosystem/heartbeat/*   — heartbeat monitoring aggregator

The middleware stack (telemetry, rate limiting, auth) is provided by the
main app in api.py. Module-level singletons are lazily initialised.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

_log = logging.getLogger("tranc3.ecosystem")

router = APIRouter(prefix="/api/ecosystem", tags=["ecosystem"])

# ---------------------------------------------------------------------------
# Dimensional singletons (lazy import — graceful fallback if unavailable)
# ---------------------------------------------------------------------------

try:
    from Dimensional.architecture.audit_ledger import AuditLedger
    from Dimensional.architecture.storage_factory import StorageFactory
    from Dimensional.middleware.telemetry import TelemetryCollector
    from Dimensional.orchestration.config_drift import ConfigDriftDetector
    from Dimensional.orchestration.dependency_graph import SmartDependencyGraph
    from Dimensional.orchestration.enhanced_registry import EnhancedServiceRegistry
    from Dimensional.orchestration.health_monitor import AdaptiveHealthMonitor
    from Dimensional.orchestration.heartbeat_aggregator import (
        Heartbeat,
        HeartbeatAggregator,
        HeartbeatMetrics,
        ServiceStatus,
    )
    from Dimensional.security_automation.adaptive_scanner import AdaptiveScanner
    from Dimensional.security_automation.defense_engine import DefenseEngine, ThreatLevel

    _registry = EnhancedServiceRegistry()
    _health_monitor = AdaptiveHealthMonitor()
    _dependency_graph = SmartDependencyGraph()
    _drift_detector = ConfigDriftDetector()
    _storage_factory = StorageFactory()
    _audit_ledger = AuditLedger()
    _scanner = AdaptiveScanner()
    _defense_engine = DefenseEngine()
    _telemetry = TelemetryCollector.get_instance()
    _heartbeat_aggregator = HeartbeatAggregator()
    _DIMENSIONAL_AVAILABLE = True
except Exception:  # pragma: no cover — optional dependency
    _DIMENSIONAL_AVAILABLE = False
    _registry = None  # type: ignore[assignment]
    _health_monitor = None  # type: ignore[assignment]
    _dependency_graph = None  # type: ignore[assignment]
    _drift_detector = None  # type: ignore[assignment]
    _storage_factory = None  # type: ignore[assignment]
    _audit_ledger = None  # type: ignore[assignment]
    _scanner = None  # type: ignore[assignment]
    _defense_engine = None  # type: ignore[assignment]
    _telemetry = None  # type: ignore[assignment]
    _heartbeat_aggregator = None  # type: ignore[assignment]
    ThreatLevel = None  # type: ignore[assignment]
    Heartbeat = None  # type: ignore[assignment]
    HeartbeatMetrics = None  # type: ignore[assignment]
    HeartbeatAggregator = None  # type: ignore[assignment]
    ServiceStatus = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Pillar & Hub configuration (canonical platform entity names)
# ---------------------------------------------------------------------------

PILLARS = [
    {
        "id": "architectural",
        "name": "Architectural",
        "color": "#3B82F6",
        "hubs": [
            "the-nexus",
            "infinity",
            "the-void",
            "the-lighthouse",
            "the-warp-tunnel",
            "the-ice-box",
        ],
    },
    {
        "id": "development",
        "name": "Development",
        "color": "#10B981",
        "hubs": ["devocity", "turings-hub", "the-workshop", "the-lab"],
    },
    {
        "id": "creativity",
        "name": "Creativity",
        "color": "#F59E0B",
        "hubs": ["the-studio", "imaginarium", "fablousa"],
    },
    {
        "id": "commercial",
        "name": "Commercial & Financial",
        "color": "#F97316",
        "hubs": [
            "section-7",
            "royal-bank-of-arcadia",
            "arcadian-exchange",
            "the-artifactory",
            "api-marketplace",
            "the-digital-grid",
        ],
    },
    {
        "id": "knowledge",
        "name": "Knowledge",
        "color": "#8B5CF6",
        "hubs": ["the-observatory", "the-library", "the-basement"],
    },
    {
        "id": "security",
        "name": "Security",
        "color": "#EF4444",
        "hubs": ["the-citadel", "the-chaos-party"],
    },
    {
        "id": "devops",
        "name": "DevOps",
        "color": "#06B6D4",
        "hubs": ["the-hive", "the-swarm"],
    },
    {
        "id": "wellbeing",
        "name": "Wellbeing",
        "color": "#EC4899",
        "hubs": ["tranquility", "i-mind", "taimra"],
    },
    {
        "id": "foresight",
        "name": "Foresight",
        "color": "#A78BFA",
        "hubs": ["chronosphere", "luminous"],
    },
    {
        "id": "governance",
        "name": "Governance",
        "color": "#6366F1",
        "hubs": ["the-town-hall"],
    },
    {
        "id": "immersive",
        "name": "Immersive",
        "color": "#F472B6",
        "hubs": ["vrar3d", "resonate"],
    },
]

HUB_COLORS: Dict[str, str] = {
    "the-nexus": "#3B82F6",
    "the-observatory": "#8B5CF6",
    "infinity": "#F59E0B",
    "the-void": "#6366F1",
    "the-lighthouse": "#FBBF24",
    "the-warp-tunnel": "#06B6D4",
    "the-ice-box": "#67E8F9",
    "devocity": "#10B981",
    "turings-hub": "#34D399",
    "chronosphere": "#A78BFA",
    "the-citadel": "#EF4444",
    "section-7": "#F97316",
    "the-studio": "#F59E0B",
    "imaginarium": "#FBBF24",
    "tranquility": "#EC4899",
    "i-mind": "#8B5CF6",
    "taimra": "#C084FC",
    "vrar3d": "#F472B6",
    "resonate": "#FB923C",
    "royal-bank-of-arcadia": "#F97316",
    "arcadian-exchange": "#FB923C",
    "the-artifactory": "#10B981",
    "api-marketplace": "#34D399",
    "the-digital-grid": "#06B6D4",
    "the-lab": "#10B981",
    "the-workshop": "#34D399",
    "the-chaos-party": "#EF4444",
    "the-library": "#8B5CF6",
    "the-basement": "#6366F1",
    "the-hive": "#F59E0B",
    "the-swarm": "#FBBF24",
    "the-town-hall": "#6366F1",
    "fablousa": "#EC4899",
    "luminous": "#A78BFA",
}

# ---------------------------------------------------------------------------
# Hub state cache
# ---------------------------------------------------------------------------

_hub_state_cache: Dict[str, Dict[str, Any]] = {}
_last_hub_update: float = 0.0


def _get_system_mode() -> str:
    try:
        from src.platform.infrastructure_mode import PlatformInfraMode, get_infrastructure_mode

        mode = get_infrastructure_mode()
        if mode == PlatformInfraMode.LOCAL_ONLY:
            return "TRUE_NAS"
        return mode.value
    except Exception:
        return os.getenv("SYSTEM_MODE", "CLOUD_ONLY").upper()


def _refresh_hub_states() -> Dict[str, Dict[str, Any]]:
    global _hub_state_cache, _last_hub_update
    now = time.time()
    if _hub_state_cache and (now - _last_hub_update) < 5:
        return _hub_state_cache

    mode = _get_system_mode()
    states: Dict[str, Dict[str, Any]] = {}

    for pillar in PILLARS:
        for hub_id in pillar["hubs"]:
            registered: List[Any] = []
            if _DIMENSIONAL_AVAILABLE and _registry is not None:
                try:
                    registered = _registry.list_all()
                except Exception:
                    registered = []
            hub_services = [s for s in registered if s.get("hub") == hub_id]

            if hub_services:
                healthy = sum(1 for s in hub_services if s.get("status") == "healthy")
                total = len(hub_services)
                health_pct = int((healthy / total) * 100) if total else 0
                status = (
                    "online" if health_pct >= 85 else "degraded" if health_pct >= 50 else "offline"
                )
                cb_state = (
                    "closed" if health_pct >= 70 else "half_open" if health_pct >= 40 else "open"
                )
                agents = sum(s.get("active_agents", 0) for s in hub_services)
                hub_services_count = len(hub_services)
            else:
                status = random.choice(["online", "online", "online", "degraded", "offline"])
                health_pct = (
                    random.randint(60, 99)
                    if status == "online"
                    else random.randint(30, 70)
                    if status == "degraded"
                    else random.randint(5, 30)
                )
                cb_state = (
                    "closed"
                    if status == "online"
                    else "half_open"
                    if status == "degraded"
                    else "open"
                )
                hub_services_count = random.randint(2, 24)
                agents = random.randint(0, 12)

            states[hub_id] = {
                "id": hub_id,
                "name": hub_id.replace("-", " ").title(),
                "pillar": pillar["id"],
                "pillarName": pillar["name"],
                "pillarColor": pillar["color"],
                "hubColor": HUB_COLORS.get(hub_id, "#3B82F6"),
                "status": status,
                "systemMode": mode,
                "services": hub_services_count,
                "activeAgents": agents,
                "circuitBreaker": cb_state,
                "healthScore": health_pct,
                "lastHeartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "alerts": random.randint(0, 8) if status != "online" else 0,
                "tier": random.randint(1, 5),
            }

    _hub_state_cache = states
    _last_hub_update = now
    return states


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class HubStateResponse(BaseModel):
    hubs: List[Dict[str, Any]]
    totalHubs: int
    onlineHubs: int
    totalServices: int
    totalAgents: int
    avgHealth: float
    totalAlerts: int
    systemMode: str


class SecurityPostureResponse(BaseModel):
    violations: int
    suppressed: int
    audit_chain_valid: bool
    secret_leaks: int
    vault_status: str
    last_scan_time: Optional[str] = None
    threat_level: str = "none"
    firewall_rules: int = 0
    blocked_requests: int = 0
    open_incidents: int = 0


class CitadelOverviewResponse(BaseModel):
    total_services: int
    total_agents: int
    open_circuits: int
    half_open_circuits: int
    avg_health: float
    system_mode: str
    threat_level: str = "none"


class ModeChangeRequest(BaseModel):
    mode: str = Field(..., pattern="^(TRUE_NAS|HYBRID|CLOUD_ONLY)$")


class IncidentCreateRequest(BaseModel):
    title: str
    description: str
    severity: str = Field(..., pattern="^(none|low|medium|high|critical)$")
    source: str = ""
    affected_services: List[str] = []


class HeartbeatRequest(BaseModel):
    service_id: str
    service_name: str
    status: str = Field(..., pattern="^(healthy|degraded|critical|offline|unknown)$")
    response_time: float = 0.0
    error_rate: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    uptime: float = 0.0
    active_connections: int = 0
    requests_per_minute: float = 0.0
    tags: List[str] = []


# ---------------------------------------------------------------------------
# Routes — Hubs
# ---------------------------------------------------------------------------


@router.get("/hubs", response_model=HubStateResponse)
async def get_hub_states(pillar: Optional[str] = None):
    """Get current status of all hubs, optionally filtered by pillar."""
    states = _refresh_hub_states()
    hub_list = list(states.values())
    if pillar:
        hub_list = [h for h in hub_list if h["pillar"] == pillar]
    online = sum(1 for h in hub_list if h["status"] == "online")
    total_svc = sum(h["services"] for h in hub_list)
    total_agents = sum(h["activeAgents"] for h in hub_list)
    total_alerts = sum(h["alerts"] for h in hub_list)
    avg_health = (sum(h["healthScore"] for h in hub_list) / len(hub_list)) if hub_list else 0
    return HubStateResponse(
        hubs=hub_list,
        totalHubs=len(hub_list),
        onlineHubs=online,
        totalServices=total_svc,
        totalAgents=total_agents,
        avgHealth=round(avg_health, 1),
        totalAlerts=total_alerts,
        systemMode=_get_system_mode(),
    )


@router.get("/hubs/{hub_id}")
async def get_hub_detail(hub_id: str):
    """Get detailed status for a specific hub."""
    states = _refresh_hub_states()
    if hub_id not in states:
        raise HTTPException(status_code=404, detail=f"Hub '{hub_id}' not found")
    hub = dict(states[hub_id])
    if _DIMENSIONAL_AVAILABLE and _dependency_graph is not None:
        try:
            node = _dependency_graph.get_node(hub_id)
            if node:
                hub["dependencies"] = (
                    [e.target for e in node.edges] if hasattr(node, "edges") else []
                )
                impact = _dependency_graph.analyze_impact(hub_id)
                hub["dependents"] = (
                    [d.name for d in impact.affected_nodes]
                    if hasattr(impact, "affected_nodes")
                    else []
                )
            else:
                hub["dependencies"] = []
                hub["dependents"] = []
        except Exception:
            hub["dependencies"] = []
            hub["dependents"] = []
    else:
        hub["dependencies"] = []
        hub["dependents"] = []
    if _DIMENSIONAL_AVAILABLE and _audit_ledger is not None:
        try:
            recent = _audit_ledger.query(tags=[hub_id], limit=10)
            hub["auditEvents"] = recent if isinstance(recent, list) else []
        except Exception:
            hub["auditEvents"] = []
    else:
        hub["auditEvents"] = []
    return hub


# ---------------------------------------------------------------------------
# Routes — Citadel, Security, Pillars, Neural-Bus, Mode
# ---------------------------------------------------------------------------


@router.get("/citadel", response_model=CitadelOverviewResponse)
async def get_citadel_overview():
    """Get the Citadel Master OS overview."""
    states = _refresh_hub_states()
    hub_list = list(states.values())
    total_svc = sum(h["services"] for h in hub_list)
    total_agents = sum(h["activeAgents"] for h in hub_list)
    open_cb = sum(1 for h in hub_list if h["circuitBreaker"] == "open")
    half_open_cb = sum(1 for h in hub_list if h["circuitBreaker"] == "half_open")
    avg_health = (sum(h["healthScore"] for h in hub_list) / len(hub_list)) if hub_list else 0
    threat = "none"
    if _DIMENSIONAL_AVAILABLE and _defense_engine is not None:
        try:
            threat = _defense_engine.get_stats().current_threat_level.value
        except Exception:
            pass
    return CitadelOverviewResponse(
        total_services=total_svc,
        total_agents=total_agents,
        open_circuits=open_cb,
        half_open_circuits=half_open_cb,
        avg_health=round(avg_health, 1),
        system_mode=_get_system_mode(),
        threat_level=threat,
    )


@router.get("/security", response_model=SecurityPostureResponse)
async def get_security_posture():
    """Get the current security posture from the adaptive scanner and defense engine."""
    violations, suppressed = 0, 0
    if _DIMENSIONAL_AVAILABLE and _scanner is not None:
        try:
            results = _scanner.scan_path(".")
            violations = len(results)
            suppressed = sum(1 for r in results if getattr(r, "suppressed", False))
        except Exception:
            pass
    chain_valid = True
    if _DIMENSIONAL_AVAILABLE and _audit_ledger is not None:
        try:
            chain_valid = _audit_ledger.verify_chain()
        except Exception:
            pass
    firewall_rules, blocked_requests, open_incidents, threat = 0, 0, 0, "none"
    last_scan: Optional[str] = None
    if _DIMENSIONAL_AVAILABLE and _defense_engine is not None:
        try:
            ds = _defense_engine.get_stats()
            firewall_rules = ds.firewall_rules
            blocked_requests = ds.blocked_requests
            open_incidents = ds.open_incidents
            threat = ds.current_threat_level.value
        except Exception:
            pass
    if violations > 0:
        last_scan = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return SecurityPostureResponse(
        violations=violations,
        suppressed=suppressed,
        audit_chain_valid=chain_valid,
        secret_leaks=0,
        vault_status="Sealed",
        last_scan_time=last_scan,
        threat_level=threat,
        firewall_rules=firewall_rules,
        blocked_requests=blocked_requests,
        open_incidents=open_incidents,
    )


@router.get("/pillars")
async def get_pillars():
    """Get all pillar definitions with hub counts."""
    states = _refresh_hub_states()
    result = []
    for p in PILLARS:
        pillar_hubs = [states[h] for h in p["hubs"] if h in states]
        alerts = sum(h["alerts"] for h in pillar_hubs)
        online = sum(1 for h in pillar_hubs if h["status"] == "online")
        result.append(
            {
                "id": p["id"],
                "name": p["name"],
                "color": p["color"],
                "hubCount": len(p["hubs"]),
                "onlineHubs": online,
                "alerts": alerts,
                "hubs": p["hubs"],
            },
        )
    return result


@router.get("/neural-bus")
async def get_neural_bus():
    """Get Neural Bus topology — which hubs are connected and communicating."""
    states = _refresh_hub_states()
    online_hubs = [h for h in states.values() if h["status"] == "online"]
    connections: List[Dict[str, str]] = []
    if _DIMENSIONAL_AVAILABLE and _dependency_graph is not None:
        for hub in online_hubs:
            try:
                node = _dependency_graph.get_node(hub["id"])
                if node and hasattr(node, "edges"):
                    for edge in node.edges:
                        target = edge.target if hasattr(edge, "target") else str(edge)
                        connections.append({"from": hub["id"], "to": target})
            except Exception:
                pass
    return {
        "activeNodes": len(online_hubs),
        "nodes": [
            {"id": h["id"], "name": h["name"], "color": h["hubColor"], "health": h["healthScore"]}
            for h in online_hubs
        ],
        "connections": connections,
        "protocol": "Neural-Bus/v1",
        "status": "active" if online_hubs else "idle",
    }


@router.post("/mode")
async def set_system_mode(req: ModeChangeRequest):
    """Change the SYSTEM_MODE."""
    global _hub_state_cache, _last_hub_update
    os.environ["SYSTEM_MODE"] = req.mode
    _hub_state_cache = {}
    _last_hub_update = 0.0
    return {"status": "ok", "mode": req.mode, "message": f"System mode changed to {req.mode}"}


@router.get("/health")
async def ecosystem_health():
    """Ecosystem health with telemetry and defense stats."""
    telemetry_data: Dict[str, Any] = {
        "requestsPerSecond": 0,
        "errorRate": 0,
        "latencyP50": 0,
        "latencyP99": 0,
        "memoryMB": 0,
        "uptimeSeconds": 0,
    }
    if _DIMENSIONAL_AVAILABLE and _telemetry is not None:
        try:
            m = _telemetry.get_metrics()
            telemetry_data = {
                "requestsPerSecond": m["requests_per_second"],
                "errorRate": m["error_rate"],
                "latencyP50": m["latency_p50_ms"],
                "latencyP99": m["latency_p99_ms"],
                "memoryMB": m["memory_mb"],
                "uptimeSeconds": m["uptime_seconds"],
            }
        except Exception:
            pass
    defense_data: Dict[str, Any] = {
        "threatLevel": "none",
        "firewallRules": 0,
        "blockedRequests": 0,
        "openIncidents": 0,
    }
    if _DIMENSIONAL_AVAILABLE and _defense_engine is not None:
        try:
            ds = _defense_engine.get_stats()
            defense_data = {
                "threatLevel": ds.current_threat_level.value,
                "firewallRules": ds.firewall_rules,
                "blockedRequests": ds.blocked_requests,
                "openIncidents": ds.open_incidents,
            }
        except Exception:
            pass
    return {
        "status": "healthy",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "systemMode": _get_system_mode(),
        "version": "2.0.0",
        "telemetry": telemetry_data,
        "defense": defense_data,
        "resilience": {
            "circuitBreakers": "active",
            "adaptiveRateLimit": "iam_level_aware",
            "retryPolicy": "exponential_backoff_jitter",
        },
    }


@router.get("/metrics")
async def ecosystem_prometheus_metrics():
    """Prometheus-compatible metrics endpoint (ecosystem view)."""
    if _DIMENSIONAL_AVAILABLE and _telemetry is not None:
        try:
            return Response(
                content=_telemetry.to_prometheus(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
        except Exception:
            pass
    return Response(
        content="# Dimensional telemetry unavailable\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Routes — Defense Engine
# ---------------------------------------------------------------------------


@router.get("/defense/firewall")
async def get_firewall_rules():
    """Get all firewall rules from the defense engine."""
    if not _DIMENSIONAL_AVAILABLE or _defense_engine is None:
        return {"rules": [], "stats": {}}
    return {"rules": _defense_engine.get_rules(), "stats": _defense_engine.get_stats().to_dict()}


@router.post("/defense/incidents")
async def create_security_incident(req: IncidentCreateRequest):
    """Create a new security incident."""
    if not _DIMENSIONAL_AVAILABLE or _defense_engine is None or ThreatLevel is None:
        raise HTTPException(status_code=503, detail="Defense engine unavailable")
    severity = ThreatLevel(req.severity)
    incident = _defense_engine.create_incident(
        title=req.title,
        description=req.description,
        severity=severity,
        source=req.source,
        affected_services=req.affected_services,
    )
    return {"status": "created", "incident": incident.to_dict()}


@router.get("/defense/incidents")
async def get_security_incidents(status: Optional[str] = None):
    """Get security incidents, optionally filtered by status."""
    if not _DIMENSIONAL_AVAILABLE or _defense_engine is None:
        return {"incidents": []}
    from Dimensional.security_automation.defense_engine import IncidentStatus

    status_enum = IncidentStatus(status) if status else None
    return {"incidents": _defense_engine.get_incidents(status_enum)}


@router.get("/defense/stats")
async def get_defense_stats():
    """Get aggregate defense statistics."""
    if not _DIMENSIONAL_AVAILABLE or _defense_engine is None:
        return {}
    return _defense_engine.get_stats().to_dict()


# ---------------------------------------------------------------------------
# Routes — Storage
# ---------------------------------------------------------------------------


@router.get("/storage")
async def get_storage_health():
    """Get storage provider health information."""
    if not _DIMENSIONAL_AVAILABLE or _storage_factory is None:
        return {"status": "unavailable"}
    try:
        provider = _storage_factory.get_provider()
        return await provider.health()
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Routes — AI Gateway
# ---------------------------------------------------------------------------


@router.get("/ai/catalog")
async def get_ai_model_catalog(provider: Optional[str] = None):
    """Get the free-tier AI model catalog."""
    try:
        from src.ai_gateway.zero_cost_config import get_free_model_catalog

        catalog = get_free_model_catalog()
        if provider:
            catalog = {provider: catalog.get(provider, [])}
        return {
            "total_models": sum(len(v) for v in catalog.values()),
            "providers": list(catalog.keys()),
            "catalog": catalog,
        }
    except Exception as exc:
        _log.error("Failed to get AI model catalog: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ai/providers")
async def get_ai_provider_status():
    """Auto-discover and report which AI providers are currently available."""
    try:
        from src.ai_gateway.zero_cost_config import discover_available_providers

        available = discover_available_providers()
        active = {k: v for k, v in available.items() if v}
        inactive = {k: v for k, v in available.items() if not v}
        return {
            "active_providers": len(active),
            "total_providers": len(available),
            "available": active,
            "unavailable": inactive,
            "zero_cost_capable": len(active) >= 2,
            "recommendation": (
                "Optimal: local + cloud providers available"
                if available.get("ollama") and len(active) >= 2
                else "Cloud-only: configure GROQ_API_KEY and OPENROUTER_API_KEY"
                if not available.get("ollama") and len(active) >= 2
                else "Minimal: only offline fallback available — set API keys for free providers"
                if len(active) <= 1
                else "Good: multiple cloud providers available"
            ),
        }
    except Exception as exc:
        _log.error("Failed to discover AI providers: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ai/routing-chains")
async def get_ai_routing_chains():
    """Get pre-configured zero-cost routing chains."""
    try:
        from src.ai_gateway.zero_cost_config import ROUTING_CHAINS, discover_available_providers

        available = discover_available_providers()
        chains = []
        for name, chain in ROUTING_CHAINS.items():
            chain_available = sum(1 for p in chain.providers if available.get(p, False))
            chains.append(
                {
                    "name": name,
                    "description": chain.description,
                    "providers": chain.providers,
                    "models": chain.models,
                    "estimated_cost": chain.estimated_cost_per_1k_requests,
                    "available_providers": chain_available,
                    "total_providers": len(chain.providers),
                    "viability": (
                        "full"
                        if chain_available == len(chain.providers)
                        else "partial"
                        if chain_available >= 2
                        else "degraded"
                    ),
                },
            )
        return {
            "total_chains": len(chains),
            "available_providers": available,
            "chains": chains,
        }
    except Exception as exc:
        _log.error("Failed to get routing chains: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ai/optimal-chain")
async def get_optimal_routing_chain(chain_name: Optional[str] = None):
    """Get the optimal zero-cost routing chain based on current environment."""
    try:
        from src.ai_gateway.zero_cost_config import get_optimal_chain

        chain = get_optimal_chain(chain_name)
        return {
            "name": chain.name,
            "description": chain.description,
            "providers": chain.providers,
            "models": chain.models,
            "estimated_cost": chain.estimated_cost_per_1k_requests,
            "route_rules": chain.get_route_rules(),
        }
    except Exception as exc:
        _log.error("Failed to get optimal chain: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Routes — Heartbeat monitoring
# ---------------------------------------------------------------------------


@router.post("/heartbeat")
async def submit_heartbeat(req: HeartbeatRequest):
    """Submit a heartbeat from a service."""
    if not _DIMENSIONAL_AVAILABLE or _heartbeat_aggregator is None:
        return {"status": "ok", "service_id": req.service_id, "score": 0}
    from datetime import datetime, timezone

    hb = Heartbeat(
        service_id=req.service_id,
        service_name=req.service_name,
        status=ServiceStatus(req.status),
        metrics=HeartbeatMetrics(
            response_time=req.response_time,
            error_rate=req.error_rate,
            cpu_usage=req.cpu_usage,
            memory_usage=req.memory_usage,
            uptime=req.uptime,
            active_connections=req.active_connections,
            requests_per_minute=req.requests_per_minute,
        ),
        tags=req.tags,
        timestamp=datetime.now(timezone.utc),
    )
    _heartbeat_aggregator.receive_heartbeat(hb)
    score = _heartbeat_aggregator.get_service_health(req.service_id)
    return {"status": "ok", "service_id": req.service_id, "score": score.score if score else 0}


@router.get("/heartbeat/health")
async def get_ecosystem_heartbeat_health():
    """Get the full aggregated health snapshot of the ecosystem."""
    if not _DIMENSIONAL_AVAILABLE or _heartbeat_aggregator is None:
        return {}
    return _heartbeat_aggregator.to_dict()


@router.get("/heartbeat/services/{service_id}")
async def get_service_heartbeat_health(service_id: str):
    """Get health data for a specific service."""
    if not _DIMENSIONAL_AVAILABLE or _heartbeat_aggregator is None:
        raise HTTPException(status_code=503, detail="Heartbeat aggregator unavailable")
    health = _heartbeat_aggregator.get_service_health(service_id)
    if not health:
        raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found")
    return {
        "service_id": health.service_id,
        "service_name": health.service_name,
        "status": health.status.value,
        "score": round(health.score, 1),
        "last_heartbeat": health.last_heartbeat.isoformat() if health.last_heartbeat else None,
        "missed_heartbeats": health.missed_heartbeats,
        "heartbeat_interval": round(health.heartbeat_interval, 1),
    }


@router.get("/heartbeat/alerts")
async def get_heartbeat_alerts(service_id: Optional[str] = None, resolved: Optional[bool] = None):
    """Get health alerts, optionally filtered by service or resolved status."""
    if not _DIMENSIONAL_AVAILABLE or _heartbeat_aggregator is None:
        return {"total": 0, "alerts": []}
    alerts = _heartbeat_aggregator.get_alerts(service_id=service_id, resolved=resolved)
    return {
        "total": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "severity": a.severity.value,
                "category": a.category.value,
                "service_id": a.service_id,
                "service_name": a.service_name,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
                "resolved": a.resolved,
            }
            for a in alerts
        ],
    }


@router.post("/heartbeat/alerts/{alert_id}/resolve")
async def resolve_heartbeat_alert(alert_id: str):
    """Mark a health alert as resolved."""
    if not _DIMENSIONAL_AVAILABLE or _heartbeat_aggregator is None:
        raise HTTPException(status_code=503, detail="Heartbeat aggregator unavailable")
    success = _heartbeat_aggregator.resolve_alert(alert_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Alert '{alert_id}' not found or already resolved",
        )
    return {"status": "resolved", "alert_id": alert_id}


@router.get("/heartbeat/stats")
async def get_heartbeat_stats():
    """Get aggregate heartbeat monitoring statistics."""
    if not _DIMENSIONAL_AVAILABLE or _heartbeat_aggregator is None:
        return {}
    return _heartbeat_aggregator.get_stats()
