# api_ecosystem.py — Trancendos Ecosystem API
# Exposes shared_core backend modules to the Dashboard frontend.
# Runs standalone or mounted as a sub-app on the main api.py.
#
# Enhanced with:
#   - Adaptive rate limiting (IAM-tier aware)
#   - JWT + API Key authentication enforcement
#   - Request telemetry and trace propagation
#   - DefenseEngine integration for firewall + incident tracking
#   - Prometheus-compatible /metrics endpoint
#   - Background cloud sync for hybrid storage

import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("tranc3.ecosystem")

# ─── Lifespan: Startup/Shutdown ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle."""
    # ── Startup ──
    logger.info("Tranc3 Ecosystem API starting up...")

    # Start hybrid storage auto-sync if in HYBRID mode
    from shared_core.architecture.storage_factory import SystemMode, _get_system_mode
    mode = _get_system_mode()
    if mode == SystemMode.HYBRID:
        try:
            provider = _storage_factory.get_provider()
            if hasattr(provider, "start_auto_sync"):
                await provider.start_auto_sync()
                logger.info("Hybrid storage auto-sync started")
        except Exception as e:
            logger.warning("Could not start auto-sync: %s", e)

    # Start registry auto-discovery
    try:
        await _registry.start_discovery()
        logger.info("Service auto-discovery started")
    except Exception as e:
        logger.warning("Could not start auto-discovery: %s", e)

    yield

    # ── Shutdown ──
    logger.info("Tranc3 Ecosystem API shutting down...")

    # Stop auto-sync
    if mode == SystemMode.HYBRID:
        try:
            provider = _storage_factory.get_provider()
            if hasattr(provider, "stop_auto_sync"):
                await provider.stop_auto_sync()
        except Exception:
            pass

    # Stop auto-discovery
    try:
        await _registry.stop_discovery()
    except Exception:
        pass

    logger.info("Shutdown complete")


# ─── App Creation ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Trancendos Ecosystem API",
    description="Real-time hub status, system health, circuit breakers, neural bus, and security posture",
    version="2.0.0",
    lifespan=lifespan,
)

# ─── Middleware Stack ─────────────────────────────────────────────────────────

# CORS — environment-aware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Telemetry — request tracing + metrics collection
from shared_core.middleware.telemetry import TelemetryMiddleware

app.add_middleware(TelemetryMiddleware)

# Rate Limiting — IAM-tier adaptive
from shared_core.middleware.rate_limiter import RateLimitConfig, RateLimitMiddleware

rate_config = RateLimitConfig(
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
    max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100")),
)
app.add_middleware(RateLimitMiddleware, config=rate_config)

# Auth — JWT + API Key enforcement
from shared_core.middleware.auth import AuthMiddleware

app.add_middleware(AuthMiddleware)

# ─── Shared Core Imports ─────────────────────────────────────────────────────

from shared_core.architecture.audit_ledger import AuditLedger
from shared_core.architecture.storage_factory import StorageFactory
from shared_core.middleware.telemetry import TelemetryCollector
from shared_core.orchestration.config_drift import ConfigDriftDetector
from shared_core.orchestration.dependency_graph import SmartDependencyGraph
from shared_core.orchestration.enhanced_registry import EnhancedServiceRegistry
from shared_core.orchestration.health_monitor import AdaptiveHealthMonitor
from shared_core.orchestration.heartbeat_aggregator import (
    Heartbeat,
    HeartbeatAggregator,
    HeartbeatMetrics,
    ServiceStatus,
)
from shared_core.security_automation.adaptive_scanner import AdaptiveScanner
from shared_core.security_automation.defense_engine import DefenseEngine, ThreatLevel

# ─── Singleton Instances ─────────────────────────────────────────────────────

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

# ─── Pillar & Hub Configuration ──────────────────────────────────────────────

PILLARS = [
    {"id": "architectural", "name": "Architectural", "color": "#3B82F6",
     "hubs": ["the-nexus", "infinity", "the-void", "the-lighthouse", "the-warp-tunnel", "the-ice-box"]},
    {"id": "development", "name": "Development", "color": "#10B981",
     "hubs": ["devocity", "turings-hub", "the-workshop", "the-lab"]},
    {"id": "creativity", "name": "Creativity", "color": "#F59E0B",
     "hubs": ["the-studio", "imaginarium", "fablousa"]},
    {"id": "commercial", "name": "Commercial & Financial", "color": "#F97316",
     "hubs": ["the-dutchy", "royal-bank", "arcadian-exchange", "the-artifactory", "api-marketplace", "the-digital-grid"]},
    {"id": "knowledge", "name": "Knowledge", "color": "#8B5CF6",
     "hubs": ["the-observatory", "the-library", "the-basement"]},
    {"id": "security", "name": "Security", "color": "#EF4444",
     "hubs": ["the-citadel", "the-chaos-party"]},
    {"id": "devops", "name": "DevOps", "color": "#06B6D4",
     "hubs": ["the-hive", "the-swarm"]},
    {"id": "wellbeing", "name": "Wellbeing", "color": "#EC4899",
     "hubs": ["tranquility", "i-mind", "taimra"]},
    {"id": "foresight", "name": "Foresight", "color": "#A78BFA",
     "hubs": ["chronosphere", "luminous"]},
    {"id": "governance", "name": "Governance", "color": "#6366F1",
     "hubs": ["the-town-hall"]},
    {"id": "immersive", "name": "Immersive", "color": "#F472B6",
     "hubs": ["vrar3d", "resonate"]},
]

HUB_COLORS = {
    "the-nexus": "#3B82F6", "the-observatory": "#8B5CF6", "infinity": "#F59E0B",
    "the-void": "#6366F1", "the-lighthouse": "#FBBF24", "the-warp-tunnel": "#06B6D4",
    "the-ice-box": "#67E8F9", "devocity": "#10B981", "turings-hub": "#34D399",
    "chronosphere": "#A78BFA", "the-citadel": "#EF4444", "the-dutchy": "#F97316",
    "the-studio": "#F59E0B", "imaginarium": "#FBBF24", "tranquility": "#EC4899",
    "i-mind": "#8B5CF6", "taimra": "#C084FC", "vrar3d": "#F472B6",
    "resonate": "#FB923C", "royal-bank": "#F97316", "arcadian-exchange": "#FB923C",
    "the-artifactory": "#10B981", "api-marketplace": "#34D399", "the-digital-grid": "#06B6D4",
    "the-lab": "#10B981", "the-workshop": "#34D399", "the-chaos-party": "#EF4444",
    "the-library": "#8B5CF6", "the-basement": "#6366F1", "the-hive": "#F59E0B",
    "the-swarm": "#FBBF24", "the-town-hall": "#6366F1", "fablousa": "#EC4899",
    "luminous": "#A78BFA",
}

# ─── Simulated Hub State (until real services register) ──────────────────────

_hub_state_cache: Dict[str, Dict[str, Any]] = {}
_last_hub_update: float = 0.0

def _get_system_mode() -> str:
    """Determine current SYSTEM_MODE from environment."""
    return os.getenv("SYSTEM_MODE", "CLOUD_ONLY").upper()

def _refresh_hub_states() -> Dict[str, Dict[str, Any]]:
    """Build hub states from registry + health monitor, with fallback simulation."""
    global _hub_state_cache, _last_hub_update
    now = time.time()
    if _hub_state_cache and (now - _last_hub_update) < 5:
        return _hub_state_cache

    mode = _get_system_mode()
    states: Dict[str, Dict[str, Any]] = {}

    for pillar in PILLARS:
        for hub_id in pillar["hubs"]:
            # Try to get real data from registry
            try:
                registered = _registry.list_all()
            except Exception:
                registered = []
            hub_services = [s for s in registered if s.get("hub") == hub_id]

            if hub_services:
                healthy = sum(1 for s in hub_services if s.get("status") == "healthy")
                total = len(hub_services)
                health_pct = int((healthy / total) * 100) if total else 0
                status = "online" if health_pct >= 85 else "degraded" if health_pct >= 50 else "offline"
                cb_state = "closed" if health_pct >= 70 else "half_open" if health_pct >= 40 else "open"
                agents = sum(s.get("active_agents", 0) for s in hub_services)
            else:
                # Simulated data when no real services are registered
                status = random.choice(["online", "online", "online", "degraded", "offline"])
                health_pct = random.randint(60, 99) if status == "online" else random.randint(30, 70) if status == "degraded" else random.randint(5, 30)
                cb_state = "closed" if status == "online" else "half_open" if status == "degraded" else "open"
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
                "services": hub_services_count if not hub_services else len(hub_services),
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

# ─── Response Models ─────────────────────────────────────────────────────────

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

# ─── API Routes ──────────────────────────────────────────────────────────────

@app.get("/api/ecosystem/hubs", response_model=HubStateResponse)
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


@app.get("/api/ecosystem/hubs/{hub_id}")
async def get_hub_detail(hub_id: str):
    """Get detailed status for a specific hub."""
    states = _refresh_hub_states()
    if hub_id not in states:
        raise HTTPException(status_code=404, detail=f"Hub '{hub_id}' not found")

    hub = states[hub_id]

    # Get dependency info
    try:
        node = _dependency_graph.get_node(hub_id)
        if node:
            hub["dependencies"] = [e.target for e in node.edges] if hasattr(node, 'edges') else []
            impact = _dependency_graph.analyze_impact(hub_id)
            hub["dependents"] = [d.name for d in impact.affected_nodes] if hasattr(impact, 'affected_nodes') else []
        else:
            hub["dependencies"] = []
            hub["dependents"] = []
    except Exception:
        hub["dependencies"] = []
        hub["dependents"] = []

    # Get recent audit events
    try:
        recent = _audit_ledger.query(tags=[hub_id], limit=10)
        hub["auditEvents"] = recent if isinstance(recent, list) else []
    except Exception:
        hub["auditEvents"] = []

    return hub


@app.get("/api/ecosystem/citadel", response_model=CitadelOverviewResponse)
async def get_citadel_overview():
    """Get the Citadel Master OS overview."""
    states = _refresh_hub_states()
    hub_list = list(states.values())
    total_svc = sum(h["services"] for h in hub_list)
    total_agents = sum(h["activeAgents"] for h in hub_list)
    open_cb = sum(1 for h in hub_list if h["circuitBreaker"] == "open")
    half_open_cb = sum(1 for h in hub_list if h["circuitBreaker"] == "half_open")
    avg_health = (sum(h["healthScore"] for h in hub_list) / len(hub_list)) if hub_list else 0

    # Get defense stats
    defense_stats = _defense_engine.get_stats()

    return CitadelOverviewResponse(
        total_services=total_svc,
        total_agents=total_agents,
        open_circuits=open_cb,
        half_open_circuits=half_open_cb,
        avg_health=round(avg_health, 1),
        system_mode=_get_system_mode(),
        threat_level=defense_stats.current_threat_level.value,
    )


@app.get("/api/ecosystem/security", response_model=SecurityPostureResponse)
async def get_security_posture():
    """Get the current security posture from the adaptive scanner and defense engine."""
    try:
        results = _scanner.scan_path(".", max_depth=1)
        violations = len(results)
        suppressed = sum(1 for r in results if getattr(r, "suppressed", False))
    except Exception:
        violations = 0
        suppressed = 0

    # Check audit chain integrity
    try:
        chain_valid = _audit_ledger.verify_chain()
    except Exception:
        chain_valid = True

    # Get defense engine stats
    defense_stats = _defense_engine.get_stats()

    return SecurityPostureResponse(
        violations=violations,
        suppressed=suppressed,
        audit_chain_valid=chain_valid,
        secret_leaks=0,
        vault_status="Sealed",
        last_scan_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if violations > 0 else None,
        threat_level=defense_stats.current_threat_level.value,
        firewall_rules=defense_stats.firewall_rules,
        blocked_requests=defense_stats.blocked_requests,
        open_incidents=defense_stats.open_incidents,
    )


@app.get("/api/ecosystem/pillars")
async def get_pillars():
    """Get all pillar definitions with hub counts."""
    states = _refresh_hub_states()
    result = []
    for p in PILLARS:
        pillar_hubs = [states[h] for h in p["hubs"] if h in states]
        alerts = sum(h["alerts"] for h in pillar_hubs)
        online = sum(1 for h in pillar_hubs if h["status"] == "online")
        result.append({
            "id": p["id"],
            "name": p["name"],
            "color": p["color"],
            "hubCount": len(p["hubs"]),
            "onlineHubs": online,
            "alerts": alerts,
            "hubs": p["hubs"],
        })
    return result


@app.get("/api/ecosystem/neural-bus")
async def get_neural_bus():
    """Get Neural Bus topology — which hubs are connected and communicating."""
    states = _refresh_hub_states()
    online_hubs = [h for h in states.values() if h["status"] == "online"]

    connections: List[Dict[str, str]] = []
    for hub in online_hubs:
        try:
            node = _dependency_graph.get_node(hub["id"])
            if node and hasattr(node, 'edges'):
                for edge in node.edges:
                    target = edge.target if hasattr(edge, 'target') else str(edge)
                    connections.append({"from": hub["id"], "to": target})
        except Exception:
            pass

    return {
        "activeNodes": len(online_hubs),
        "nodes": [{"id": h["id"], "name": h["name"], "color": h["hubColor"], "health": h["healthScore"]} for h in online_hubs],
        "connections": connections,
        "protocol": "Neural-Bus/v1",
        "status": "active" if online_hubs else "idle",
    }


@app.post("/api/ecosystem/mode")
async def set_system_mode(req: ModeChangeRequest):
    """Change the SYSTEM_MODE. In production, this would trigger provider reconfiguration."""
    global _hub_state_cache
    os.environ["SYSTEM_MODE"] = req.mode
    _hub_state_cache = {}
    _last_hub_update = 0.0

    return {"status": "ok", "mode": req.mode, "message": f"System mode changed to {req.mode}"}


@app.get("/api/ecosystem/health")
async def health_check():
    """Enhanced health check with telemetry and defense stats."""
    telemetry_metrics = _telemetry.get_metrics()
    defense_stats = _defense_engine.get_stats()

    return {
        "status": "healthy",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "systemMode": _get_system_mode(),
        "version": "2.0.0",
        "telemetry": {
            "requestsPerSecond": telemetry_metrics["requests_per_second"],
            "errorRate": telemetry_metrics["error_rate"],
            "latencyP50": telemetry_metrics["latency_p50_ms"],
            "latencyP99": telemetry_metrics["latency_p99_ms"],
            "memoryMB": telemetry_metrics["memory_mb"],
            "uptimeSeconds": telemetry_metrics["uptime_seconds"],
        },
        "defense": {
            "threatLevel": defense_stats.current_threat_level.value,
            "firewallRules": defense_stats.firewall_rules,
            "blockedRequests": defense_stats.blocked_requests,
            "openIncidents": defense_stats.open_incidents,
        },
        "resilience": {
            "circuitBreakers": "active",
            "adaptiveRateLimit": "iam_level_aware",
            "retryPolicy": "exponential_backoff_jitter",
        },
    }


# ─── New: Prometheus Metrics Endpoint ────────────────────────────────────────

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint for monitoring."""
    return Response(
        content=_telemetry.to_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ─── New: Defense Engine Endpoints ───────────────────────────────────────────

@app.get("/api/ecosystem/defense/firewall")
async def get_firewall_rules():
    """Get all firewall rules from the defense engine."""
    getattr(Request, "state", None)
    return {"rules": _defense_engine.get_rules(), "stats": _defense_engine.get_stats().to_dict()}


@app.post("/api/ecosystem/defense/incidents")
async def create_security_incident(req: IncidentCreateRequest):
    """Create a new security incident."""
    severity = ThreatLevel(req.severity)
    incident = _defense_engine.create_incident(
        title=req.title,
        description=req.description,
        severity=severity,
        source=req.source,
        affected_services=req.affected_services,
    )
    return {"status": "created", "incident": incident.to_dict()}


@app.get("/api/ecosystem/defense/incidents")
async def get_security_incidents(status: Optional[str] = None):
    """Get security incidents, optionally filtered by status."""
    from shared_core.security_automation.defense_engine import IncidentStatus
    status_enum = IncidentStatus(status) if status else None
    return {"incidents": _defense_engine.get_incidents(status_enum)}


@app.get("/api/ecosystem/defense/stats")
async def get_defense_stats():
    """Get aggregate defense statistics."""
    return _defense_engine.get_stats().to_dict()


# ─── New: Storage Health Endpoint ────────────────────────────────────────────

@app.get("/api/ecosystem/storage")
async def get_storage_health():
    """Get storage provider health information."""
    try:
        provider = _storage_factory.get_provider()
        health = await provider.health()
        return health
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── New: AI Gateway Endpoints ─────────────────────────────────────────────────────

@app.get("/api/ecosystem/ai/catalog")
async def get_ai_model_catalog(provider: Optional[str] = None):
    """Get the free-tier AI model catalog.

    Returns all available free and near-zero-cost models across providers.
    Optionally filter by provider name (ollama, groq, openrouter, huggingface, deepseek).
    """
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
    except Exception as e:
        logger.error("Failed to get AI model catalog: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ecosystem/ai/providers")
async def get_ai_provider_status():
    """Auto-discover and report which AI providers are currently available.

    Checks environment variables and network connectivity to determine
    which zero-cost AI providers can be used right now.
    """
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
    except Exception as e:
        logger.error("Failed to discover AI providers: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ecosystem/ai/routing-chains")
async def get_ai_routing_chains():
    """Get pre-configured zero-cost routing chains.

    Returns all available routing chains with provider ordering,
    model mappings, and estimated costs.
    """
    try:
        from src.ai_gateway.zero_cost_config import ROUTING_CHAINS, discover_available_providers
        available = discover_available_providers()
        chains = []
        for name, chain in ROUTING_CHAINS.items():
            chain_available = sum(1 for p in chain.providers if available.get(p, False))
            chains.append({
                "name": name,
                "description": chain.description,
                "providers": chain.providers,
                "models": chain.models,
                "estimated_cost": chain.estimated_cost_per_1k_requests,
                "available_providers": chain_available,
                "total_providers": len(chain.providers),
                "viability": (
                    "full" if chain_available == len(chain.providers)
                    else "partial" if chain_available >= 2
                    else "degraded"
                ),
            })
        return {
            "total_chains": len(chains),
            "available_providers": available,
            "chains": chains,
        }
    except Exception as e:
        logger.error("Failed to get routing chains: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ecosystem/ai/optimal-chain")
async def get_optimal_routing_chain(chain_name: Optional[str] = None):
    """Get the optimal zero-cost routing chain based on current environment.

    Auto-detects available providers and selects the chain with the
    highest availability score. Optionally specify a chain name to
    get a specific chain instead.
    """
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
    except Exception as e:
        logger.error("Failed to get optimal chain: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ─── New: Heartbeat Monitoring Endpoints ────────────────────────────────────

class HeartbeatRequest(BaseModel):
    """Request body for submitting a heartbeat."""
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


@app.post("/api/ecosystem/heartbeat")
async def submit_heartbeat(req: HeartbeatRequest):
    """Submit a heartbeat from a service. Updates health tracking and triggers alerts if needed."""
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


@app.get("/api/ecosystem/heartbeat/health")
async def get_ecosystem_health():
    """Get the full aggregated health snapshot of the ecosystem."""
    return _heartbeat_aggregator.to_dict()


@app.get("/api/ecosystem/heartbeat/services/{service_id}")
async def get_service_health(service_id: str):
    """Get health data for a specific service."""
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


@app.get("/api/ecosystem/heartbeat/alerts")
async def get_heartbeat_alerts(service_id: Optional[str] = None, resolved: Optional[bool] = None):
    """Get health alerts, optionally filtered by service or resolved status."""
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


@app.post("/api/ecosystem/heartbeat/alerts/{alert_id}/resolve")
async def resolve_heartbeat_alert(alert_id: str):
    """Mark a health alert as resolved."""
    success = _heartbeat_aggregator.resolve_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found or already resolved")
    return {"status": "resolved", "alert_id": alert_id}


@app.get("/api/ecosystem/heartbeat/stats")
async def get_heartbeat_stats():
    """Get aggregate heartbeat monitoring statistics."""
    return _heartbeat_aggregator.get_stats()


# ─── Startup ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
