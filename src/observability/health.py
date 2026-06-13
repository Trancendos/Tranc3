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

# All known services with their default health check URLs
SERVICE_REGISTRY = {
    # P0 — Critical Path
    "tranc3-ai": {"url": "http://localhost:8001/health", "priority": "P0", "named": "The Spark"},
    "infinity-void": {"url": "http://localhost:8002/health", "priority": "P0", "named": "The Void"},
    "api-gateway": {
        "url": "http://localhost:8003/health",
        "priority": "P0",
        "named": "The Citadel",
    },
    "infinity-ws": {"url": "http://localhost:8004/health", "priority": "P0", "named": "The Nexus"},
    "infinity-auth": {"url": "http://localhost:8005/health", "priority": "P0", "named": "Infinity"},
    # P1 — Core Services
    "users-service": {"url": "http://localhost:8006/health", "priority": "P1", "named": "Users"},
    "monitoring": {
        "url": "http://localhost:8007/health",
        "priority": "P1",
        "named": "The Observatory",
    },
    "notifications": {
        "url": "http://localhost:8008/health",
        "priority": "P1",
        "named": "Notifications",
    },
    "infinity-ai": {"url": "http://localhost:8009/health", "priority": "P1", "named": "AI Gateway"},
    # P2 — Domain Services
    "the-grid": {
        "url": "http://localhost:8010/health",
        "priority": "P2",
        "named": "The Digital Grid",
    },
    "products-service": {
        "url": "http://localhost:8011/health",
        "priority": "P2",
        "named": "Products",
    },
    "orders-service": {"url": "http://localhost:8012/health", "priority": "P2", "named": "Orders"},
    "payments-service": {
        "url": "http://localhost:8013/health",
        "priority": "P2",
        "named": "Payments",
    },
    "files-service": {"url": "http://localhost:8014/health", "priority": "P2", "named": "Files"},
    "identity-service": {
        "url": "http://localhost:8015/health",
        "priority": "P2",
        "named": "Identity",
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
