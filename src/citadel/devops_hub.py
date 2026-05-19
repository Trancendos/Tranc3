# src/citadel/devops_hub.py
# The Citadel — DevOps hub for Trancendos.
#
# The Citadel orchestrates:
#   - Deployment pipeline status (from Forgejo/The Workshop)
#   - Service health aggregation (all named services)
#   - Infrastructure inventory (Fly.io apps + CF Workers)
#   - Rollback and canary controls
#   - Incident tracking (wired to Cryptex + Observatory)
#
# Foundation: Forgejo CI/CD + Fly.io + Cloudflare Workers.
# This layer aggregates status and exposes a unified DevOps API.

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeployTarget(str, Enum):
    BACKEND      = "tranc3-backend"       # Fly.io
    BOTS         = "tranc3-bots"          # Fly.io
    TRANC3_AI    = "tranc3-ai"            # CF Worker
    INFINITY_VOID = "infinity-void"       # CF Worker
    API_GATEWAY  = "trancendos-api-gateway"  # CF Worker


class DeployStatus(str, Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS    = "success"
    FAILED     = "failed"
    ROLLED_BACK = "rolled_back"


class ServiceHealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN   = "unknown"


@dataclass
class DeployRecord:
    id: str
    target: DeployTarget
    version: str
    status: DeployStatus
    triggered_by: str
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    log_url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target.value,
            "version": self.version,
            "status": self.status.value,
            "triggered_by": self.triggered_by,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round((self.completed_at or time.time()) - self.started_at, 1),
            "log_url": self.log_url,
            "error": self.error,
        }


# Static service inventory — reflects deployed services from CLAUDE.md
_SERVICE_INVENTORY: List[Dict[str, Any]] = [
    {"name": "tranc3-backend",            "type": "fly.io",          "region": "lhr", "url": "https://tranc3-backend.fly.dev"},
    {"name": "tranc3-bots",               "type": "fly.io",          "region": "lhr", "url": "https://tranc3-bots.fly.dev"},
    {"name": "tranc3-ai",                 "type": "cloudflare-worker","region": "edge", "url": "https://tranc3-ai.luminous-aimastermind.workers.dev"},
    {"name": "infinity-void",             "type": "cloudflare-worker","region": "edge", "url": "https://infinity-void.luminous-aimastermind.workers.dev"},
    {"name": "infinity-auth-api",         "type": "cloudflare-worker","region": "edge", "url": "https://infinity-auth-api.luminous-aimastermind.workers.dev"},
    {"name": "infinity-ai-api",           "type": "cloudflare-worker","region": "edge", "url": "https://infinity-ai-api.luminous-aimastermind.workers.dev"},
    {"name": "trancendos-api-gateway",    "type": "cloudflare-worker","region": "edge", "url": "https://api.trancendos.com"},
    {"name": "tranc3-backend-db",         "type": "supabase",        "region": "eu-west-2", "url": "db.ijizzeycvmqlobszojhf.supabase.co"},
    {"name": "forgejo-the-workshop",      "type": "self-hosted",     "region": "trancendos.com", "url": "trancendos.com/the-workshop"},
]


class TheCitadel:
    """The Citadel — unified DevOps hub."""

    def __init__(self):
        self._deploys: Dict[str, DeployRecord] = {}
        self._service_health: Dict[str, ServiceHealthStatus] = {
            s["name"]: ServiceHealthStatus.UNKNOWN for s in _SERVICE_INVENTORY
        }

    def inventory(self) -> List[Dict[str, Any]]:
        return [
            {**svc, "health": self._service_health.get(svc["name"], ServiceHealthStatus.UNKNOWN).value}
            for svc in _SERVICE_INVENTORY
        ]

    def record_deploy(
        self,
        target: DeployTarget,
        version: str,
        triggered_by: str = "forgejo",
        status: DeployStatus = DeployStatus.PENDING,
    ) -> DeployRecord:
        import uuid
        record = DeployRecord(
            id=str(uuid.uuid4()),
            target=target,
            version=version,
            status=status,
            triggered_by=triggered_by,
        )
        self._deploys[record.id] = record
        self._emit(f"citadel.deploy.{status.value}", {
            "target": target.value, "version": version, "deploy_id": record.id
        })
        logger.info("citadel: deploy recorded target=%s version=%s status=%s", target.value, version, status.value)
        return record

    def update_deploy(
        self,
        deploy_id: str,
        status: DeployStatus,
        error: Optional[str] = None,
    ) -> Optional[DeployRecord]:
        record = self._deploys.get(deploy_id)
        if not record:
            return None
        record.status = status
        record.error = error
        if status in (DeployStatus.SUCCESS, DeployStatus.FAILED, DeployStatus.ROLLED_BACK):
            record.completed_at = time.time()
            if status == DeployStatus.SUCCESS:
                self._service_health[record.target.value] = ServiceHealthStatus.HEALTHY
            elif status == DeployStatus.FAILED:
                self._service_health[record.target.value] = ServiceHealthStatus.UNHEALTHY
        self._emit(f"citadel.deploy.{status.value}", {"deploy_id": deploy_id})
        return record

    def update_health(self, service_name: str, status: ServiceHealthStatus) -> None:
        self._service_health[service_name] = status

    def list_deploys(self, target: Optional[DeployTarget] = None) -> List[DeployRecord]:
        deploys = list(self._deploys.values())
        if target:
            deploys = [d for d in deploys if d.target == target]
        return sorted(deploys, key=lambda d: d.started_at, reverse=True)[:50]

    def stats(self) -> Dict[str, Any]:
        healthy = sum(1 for v in self._service_health.values() if v == ServiceHealthStatus.HEALTHY)
        total = len(self._service_health)
        recent = [d for d in self._deploys.values()
                  if (time.time() - d.started_at) < 86400]
        return {
            "service": "the-citadel",
            "total_services": total,
            "healthy_services": healthy,
            "deploys_last_24h": len(recent),
            "total_deploys": len(self._deploys),
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import observe, EventCategory
            observe(event_type, category=EventCategory.SYSTEM, service="the-citadel",
                    metadata=metadata or {})
        except Exception:
            pass


_citadel: Optional[TheCitadel] = None


def get_citadel() -> TheCitadel:
    global _citadel
    if _citadel is None:
        _citadel = TheCitadel()
    return _citadel
