"""
Tranc3 Health Aggregation — Zero-Cost Service Health Monitoring
================================================================
Aggregates health status from all workers and computes overall system health.
Replaces Cloudflare Health Checks and CF Analytics Dashboard.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.health")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SystemHealth(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# Service Registry
# ---------------------------------------------------------------------------

# All known services with their default health check URLs.
# Ports match the canonical map in CLAUDE.md / docker-compose.production.yml.
SERVICE_REGISTRY = {
    # ── Main App ────────────────────────────────────────────────────────────
    "tranc3-backend": {
        "url": "http://localhost:8000/health",
        "priority": "P0",
        "named": "Tranc3 Backend",
    },
    "nanoservices": {
        "url": "http://localhost:8001/health",
        "priority": "P0",
        "named": "Nanoservices",
    },
    # ── P0 — Critical Path ──────────────────────────────────────────────────
    "infinity-void": {
        "url": "http://localhost:8002/health",
        "priority": "P0",
        "named": "The Void",
    },
    "api-gateway": {
        "url": "http://localhost:8003/health",
        "priority": "P0",
        "named": "The Citadel (API Gateway)",
    },
    "infinity-ws": {
        "url": "http://localhost:8004/health",
        "priority": "P0",
        "named": "The Nexus",
    },
    "infinity-auth": {
        "url": "http://localhost:8005/health",
        "priority": "P0",
        "named": "Infinity (Core Auth)",
    },
    # ── P1 — Core Services ──────────────────────────────────────────────────
    "infinity-portal": {
        "url": "http://localhost:8042/health",
        "priority": "P1",
        "named": "Infinity Portal",
    },
    "infinity-one": {
        "url": "http://localhost:8043/health",
        "priority": "P1",
        "named": "Infinity-One (Identity)",
    },
    "infinity-admin": {
        "url": "http://localhost:8044/health",
        "priority": "P1",
        "named": "Infinity Admin",
    },
    "infinity-shards": {
        "url": "http://localhost:8045/health",
        "priority": "P1",
        "named": "Infinity Shards",
    },
    "infinity-bridge": {
        "url": "http://localhost:8070/health",
        "priority": "P1",
        "named": "Infinity Bridge",
    },
    "users-service": {
        "url": "http://localhost:8006/health",
        "priority": "P1",
        "named": "Users Service",
    },
    "monitoring": {
        "url": "http://localhost:8007/health",
        "priority": "P1",
        "named": "The Observatory",
    },
    "notifications": {
        "url": "http://localhost:8008/health",
        "priority": "P1",
        "named": "Notifications Service",
    },
    "infinity-ai": {
        "url": "http://localhost:8009/health",
        "priority": "P1",
        "named": "Luminous (AI Gateway)",
    },
    # ── P2 — Domain Services ────────────────────────────────────────────────
    "the-grid": {
        "url": "http://localhost:8010/health",
        "priority": "P2",
        "named": "The Digital Grid",
    },
    "products-service": {
        "url": "http://localhost:8011/health",
        "priority": "P2",
        "named": "Products Service",
    },
    "orders-service": {
        "url": "http://localhost:8012/health",
        "priority": "P2",
        "named": "Arcadian Exchange (Orders)",
    },
    "payments-service": {
        "url": "http://localhost:8013/health",
        "priority": "P2",
        "named": "Royal Bank of Arcadia (Payments)",
    },
    "files-service": {
        "url": "http://localhost:8014/health",
        "priority": "P2",
        "named": "DocUtari (Files)",
    },
    "identity-service": {
        "url": "http://localhost:8015/health",
        "priority": "P2",
        "named": "Infinity Identity",
    },
    # ── P3 — Extended Services (8016–8029) ──────────────────────────────────
    "analytics-service": {
        "url": "http://localhost:8016/health",
        "priority": "P3",
        "named": "Analytics Service",
    },
    "search-service": {
        "url": "http://localhost:8017/health",
        "priority": "P3",
        "named": "Search Service",
    },
    "email-service": {
        "url": "http://localhost:8018/health",
        "priority": "P3",
        "named": "Email Service",
    },
    "sms-service": {
        "url": "http://localhost:8019/health",
        "priority": "P3",
        "named": "SMS Service",
    },
    "storage-service": {
        "url": "http://localhost:8020/health",
        "priority": "P3",
        "named": "Storage Service",
    },
    "cron-service": {
        "url": "http://localhost:8021/health",
        "priority": "P3",
        "named": "ChronosSphere (Cron)",
    },
    "queue-service": {
        "url": "http://localhost:8022/health",
        "priority": "P3",
        "named": "Queue Service",
    },
    "cache-service": {
        "url": "http://localhost:8023/health",
        "priority": "P3",
        "named": "Cache Service",
    },
    "config-service": {
        "url": "http://localhost:8024/health",
        "priority": "P3",
        "named": "Config Service",
    },
    "audit-service": {
        "url": "http://localhost:8025/health",
        "priority": "P3",
        "named": "Audit Service",
    },
    "rate-limit-service": {
        "url": "http://localhost:8026/health",
        "priority": "P3",
        "named": "Rate Limit Service",
    },
    "geo-service": {
        "url": "http://localhost:8027/health",
        "priority": "P3",
        "named": "Geo Service",
    },
    "cdn-service": {
        "url": "http://localhost:8028/health",
        "priority": "P3",
        "named": "CDN Service",
    },
    # ── P3 — Intelligence / AI Layer (8030–8038) ────────────────────────────
    "gbrain-bridge": {
        "url": "http://localhost:8030/health",
        "priority": "P3",
        "named": "The Library (GBrain Bridge)",
    },
    "topology-service": {
        "url": "http://localhost:8031/health",
        "priority": "P3",
        "named": "Topology Service",
    },
    "ledger-service": {
        "url": "http://localhost:8032/health",
        "priority": "P3",
        "named": "Ledger Service",
    },
    "model-router-service": {
        "url": "http://localhost:8033/health",
        "priority": "P3",
        "named": "Model Router",
    },
    "workflow-engine-service": {
        "url": "http://localhost:8034/health",
        "priority": "P3",
        "named": "Workflow Engine",
    },
    "skills-benchmark-service": {
        "url": "http://localhost:8035/health",
        "priority": "P3",
        "named": "Turing's Hub (3D AI Model Builder)",
    },
    "langchain-integration-service": {
        "url": "http://localhost:8036/health",
        "priority": "P3",
        "named": "LangChain Integration",
    },
    "deepagents-orchestrator-service": {
        "url": "http://localhost:8037/health",
        "priority": "P3",
        "named": "DeepAgents Orchestrator",
    },
    "vault-service": {
        "url": "http://localhost:8038/health",
        "priority": "P3",
        "named": "Vault Service (Secret Management)",
    },
    # ── Bots ────────────────────────────────────────────────────────────────
    "tranc3-bots": {
        "url": "http://localhost:8080/health",
        "priority": "P1",
        "named": "Tranc3 Bots",
    },
}


# ---------------------------------------------------------------------------
# Health Checker
# ---------------------------------------------------------------------------


class HealthChecker:
    """Checks the health of all registered services."""

    def __init__(self, registry: Optional[Dict[str, Dict[str, str]]] = None):
        self.registry = registry or SERVICE_REGISTRY
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def check_service(self, name: str, timeout: float = 5.0) -> Dict[str, Any]:
        """Check health of a single service."""
        svc = self.registry.get(name)
        if not svc:
            return {"service": name, "status": "unknown", "error": "Not registered"}

        url = svc["url"]
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
                result = {
                    "service": name,
                    "named": svc.get("named", ""),
                    "priority": svc.get("priority", ""),
                    "status": "healthy",
                    "details": body,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                self._cache[name] = result
                return result
        except urllib.error.HTTPError as e:
            result = {
                "service": name,
                "named": svc.get("named", ""),
                "priority": svc.get("priority", ""),
                "status": "degraded" if e.code < 500 else "unhealthy",
                "error": f"HTTP {e.code}",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache[name] = result
            return result
        except Exception as e:
            result = {
                "service": name,
                "named": svc.get("named", ""),
                "priority": svc.get("priority", ""),
                "status": "unhealthy",
                "error": str(e),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache[name] = result
            return result

    async def check_all(self) -> Dict[str, Any]:
        """Check health of all registered services and compute overall status."""
        results = {}
        for name in self.registry:
            results[name] = await self.check_service(name)

        total = len(results)
        healthy = sum(1 for r in results.values() if r["status"] == "healthy")
        degraded = sum(1 for r in results.values() if r["status"] == "degraded")
        unhealthy = sum(1 for r in results.values() if r["status"] == "unhealthy")

        # Overall status based on P0 services first
        p0_unhealthy = sum(
            1
            for r in results.values()
            if r.get("priority") == "P0" and r["status"] in ("unhealthy", "unknown")
        )

        if p0_unhealthy > 0:
            overall = SystemHealth.unhealthy
        elif unhealthy > total // 2:
            overall = SystemHealth.unhealthy
        elif degraded > 0 or unhealthy > 0:
            overall = SystemHealth.degraded
        else:
            overall = SystemHealth.healthy

        return {
            "overall": overall.value,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "total": total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": results,
        }

    def get_cached(self) -> Dict[str, Any]:
        """Return the last cached health check results."""
        return {
            "services": self._cache,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_service_list(self) -> List[Dict[str, str]]:
        """Return the list of all registered services."""
        return [
            {
                "name": name,
                "url": svc["url"],
                "priority": svc.get("priority", ""),
                "named": svc.get("named", ""),
            }
            for name, svc in self.registry.items()
        ]
