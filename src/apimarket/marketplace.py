# src/apimarket/marketplace.py
# API Marketplace — API connector hub for Trancendos.
#
# The API Marketplace provides:
#   - REST connector registry (register, discover, call external APIs)
#   - OAuth 2.0 credential management per connector
#   - Webhook subscription management
#   - Rate limiting and usage tracking per connector
#   - Integration with The Spark (MCP tools auto-generated from connector specs)
#
# Foundation: Gravitee.io API Management (self-hosted, open-source).
# This scaffold handles the registry layer; Gravitee integration
# is wired in production via the Gravitee Management API.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConnectorStatus(str, Enum):
    ACTIVE      = "active"
    INACTIVE    = "inactive"
    RATE_LIMITED = "rate_limited"
    ERROR       = "error"


class AuthType(str, Enum):
    NONE       = "none"
    API_KEY    = "api_key"
    BEARER     = "bearer"
    OAUTH2     = "oauth2"
    BASIC      = "basic"


@dataclass
class ConnectorEndpoint:
    method: str    # GET / POST / PUT / DELETE / PATCH
    path: str      # e.g. /users/{id}
    description: str = ""
    params: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "description": self.description,
        }


@dataclass
class APIConnector:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    slug: str = ""              # URL-safe identifier
    description: str = ""
    base_url: str = ""
    auth_type: AuthType = AuthType.NONE
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    endpoints: List[ConnectorEndpoint] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    call_count: int = 0
    error_count: int = 0
    rate_limit_per_min: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "base_url": self.base_url,
            "auth_type": self.auth_type.value,
            "status": self.status.value,
            "version": self.version,
            "tags": self.tags,
            "endpoint_count": len(self.endpoints),
            "call_count": self.call_count,
            "error_count": self.error_count,
            "rate_limit_per_min": self.rate_limit_per_min,
        }


class APIMarketplace:
    """
    API Marketplace — connector registry and API hub.

    Production delegates to Gravitee.io API Management for full lifecycle
    management, policies, analytics, and developer portal.
    """

    def __init__(self):
        self._connectors: Dict[str, APIConnector] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        import os
        _backend = os.getenv("TRANC3_BACKEND_URL", "http://localhost:8000")
        defaults = [
            ("The Spark", "the-spark", f"{_backend}/mcp/rpc", AuthType.BEARER,
             ["mcp", "ai", "tools"], "JSON-RPC 2.0 MCP tool registry"),
            ("The Digital Grid", "the-grid", f"{_backend}/grid", AuthType.BEARER,
             ["workflow", "automation"], "Workflow DAG builder and executor"),
            ("The Observatory", "observatory", f"{_backend}/observatory", AuthType.BEARER,
             ["audit", "events"], "Platform audit log and event stream"),
            ("The Void", "the-void", "https://infinity-void.luminous-aimastermind.workers.dev", AuthType.API_KEY,
             ["secrets", "vault"], "AES-GCM encrypted secrets vault"),
            ("Infinity Auth", "infinity-auth", "https://infinity-auth-api.luminous-aimastermind.workers.dev", AuthType.OAUTH2,
             ["auth", "sso", "identity"], "OAuth 2.0 / SSO via Infinity"),
        ]
        for name, slug, base_url, auth, tags, desc in defaults:
            connector = APIConnector(
                name=name, slug=slug, base_url=base_url, auth_type=auth,
                tags=tags, description=desc,
            )
            self._connectors[connector.id] = connector

    def register(
        self,
        name: str,
        slug: str,
        base_url: str,
        auth_type: AuthType = AuthType.NONE,
        description: str = "",
        tags: Optional[List[str]] = None,
        rate_limit_per_min: int = 60,
    ) -> APIConnector:
        connector = APIConnector(
            name=name,
            slug=slug,
            base_url=base_url,
            auth_type=auth_type,
            description=description,
            tags=tags or [],
            rate_limit_per_min=rate_limit_per_min,
        )
        self._connectors[connector.id] = connector
        self._emit("apimarket.connector.registered", {"connector_id": connector.id, "slug": slug})
        logger.info("apimarket: registered connector slug=%s base=%s", slug, base_url)
        return connector

    def get_connector(self, connector_id: str) -> Optional[APIConnector]:
        return self._connectors.get(connector_id)

    def find_by_slug(self, slug: str) -> Optional[APIConnector]:
        for c in self._connectors.values():
            if c.slug == slug:
                return c
        return None

    def list_connectors(
        self,
        tag: Optional[str] = None,
        status: Optional[ConnectorStatus] = None,
    ) -> List[APIConnector]:
        connectors = list(self._connectors.values())
        if tag:
            connectors = [c for c in connectors if tag in c.tags]
        if status:
            connectors = [c for c in connectors if c.status == status]
        return sorted(connectors, key=lambda c: c.name)

    def add_endpoint(
        self,
        connector_id: str,
        method: str,
        path: str,
        description: str = "",
    ) -> Optional[ConnectorEndpoint]:
        connector = self._connectors.get(connector_id)
        if not connector:
            return None
        ep = ConnectorEndpoint(method=method.upper(), path=path, description=description)
        connector.endpoints.append(ep)
        return ep

    def record_call(self, connector_id: str, success: bool = True) -> None:
        connector = self._connectors.get(connector_id)
        if not connector:
            return
        connector.call_count += 1
        if not success:
            connector.error_count += 1

    def stats(self) -> Dict[str, Any]:
        active = sum(1 for c in self._connectors.values() if c.status == ConnectorStatus.ACTIVE)
        total_calls = sum(c.call_count for c in self._connectors.values())
        return {
            "service": "api-marketplace",
            "total_connectors": len(self._connectors),
            "active_connectors": active,
            "total_api_calls": total_calls,
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import EventCategory, observe
            observe(event_type, category=EventCategory.DATA, service="api-marketplace",
                    metadata=metadata or {})
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream



_marketplace: Optional[APIMarketplace] = None


def get_marketplace() -> APIMarketplace:
    global _marketplace
    if _marketplace is None:
        _marketplace = APIMarketplace()
    return _marketplace
