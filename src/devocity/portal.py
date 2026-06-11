# src/devocity/portal.py
# DevOcity — Developer centre for Trancendos users.
#
# DevOcity provides:
#   - Developer account management (API keys, webhooks)
#   - SDK documentation and quickstart guides
#   - API usage analytics per developer
#   - Sandbox environment management
#   - Integration catalogue (available connectors)
#   - Developer forum links (via The Library)
#
# Foundation: Custom developer portal wired to Infinity (SSO) + The Spark (MCP).

from __future__ import annotations

import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class DevAccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    SANDBOX = "sandbox"


class ApiKeyScope(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    SPARK = "spark"  # Access to The Spark MCP tools
    GRID = "grid"  # Access to The Digital Grid
    FULL = "full"


@dataclass
class ApiKey:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    developer_id: str = ""
    name: str = ""
    key_prefix: str = ""  # First 8 chars — shown in UI
    key_hash: str = ""  # SHA-256 of full key — never store plain
    scopes: List[ApiKeyScope] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    revoked: bool = False
    request_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix + "****",
            "scopes": [s.value for s in self.scopes],
            "created_at": self.created_at,
            "last_used": self.last_used,
            "revoked": self.revoked,
            "request_count": self.request_count,
        }


@dataclass
class WebhookEndpoint:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    developer_id: str = ""
    url: str = ""
    events: List[str] = field(default_factory=list)
    secret: str = field(default_factory=lambda: secrets.token_hex(32))
    active: bool = True
    created_at: float = field(default_factory=time.time)
    delivery_count: int = 0
    failure_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "events": self.events,
            "active": self.active,
            "created_at": self.created_at,
            "delivery_count": self.delivery_count,
            "failure_count": self.failure_count,
        }


@dataclass
class DeveloperAccount:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""  # Infinity user ID
    display_name: str = ""
    status: DevAccountStatus = DevAccountStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    api_keys: List[ApiKey] = field(default_factory=list)
    webhooks: List[WebhookEndpoint] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)  # endpoint → call count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "status": self.status.value,
            "created_at": self.created_at,
            "api_key_count": len([k for k in self.api_keys if not k.revoked]),
            "webhook_count": len([w for w in self.webhooks if w.active]),
        }


# Built-in quickstart guides
_GUIDES: List[Dict[str, Any]] = [
    {
        "id": "quickstart-spark",
        "title": "Getting Started with The Spark (MCP)",
        "description": "Connect to The Spark JSON-RPC 2.0 endpoint and call your first MCP tool.",
        "url": "/library/articles/the-spark-guide",
        "tags": ["mcp", "spark", "json-rpc"],
    },
    {
        "id": "quickstart-grid",
        "title": "Building Workflows with The Digital Grid",
        "description": "Register a workflow DAG, wire nodes together, and trigger execution via REST.",
        "url": "/library/articles/digital-grid-guide",
        "tags": ["workflow", "grid", "dag"],
    },
    {
        "id": "quickstart-auth",
        "title": "Authenticating with Infinity (SSO + JWT)",
        "description": "Obtain a JWT from Infinity and use it across all Trancendos services.",
        "url": "/library/articles/infinity-auth",
        "tags": ["auth", "jwt", "infinity"],
    },
    {
        "id": "quickstart-void",
        "title": "Storing Secrets in The Void",
        "description": "Encrypt and retrieve secrets using the AES-GCM vault API.",
        "url": "/library/articles/the-void-guide",
        "tags": ["secrets", "vault", "void"],
    },
]


_ACCOUNT_TTL = 365 * 86400  # 1 year — API keys must outlive process restarts


class DevOcity:
    """DevOcity — developer portal and API key management. Persisted to Redis."""

    def __init__(self):
        self._accounts: Dict[str, DeveloperAccount] = {}
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            from src.core.redis_store import get_store

            store = await get_store()
            keys = await store.keys("devocity:account:*")
            for key in keys:
                data = await store.get(key)
                if not data:
                    continue
                try:
                    acct = DeveloperAccount(
                        user_id=data["user_id"],
                        display_name=data["display_name"],
                    )
                    acct.id = data["id"]
                    acct.created_at = data.get("created_at", acct.created_at)
                    acct.api_keys = [
                        ApiKey(
                            developer_id=k["developer_id"],
                            name=k["name"],
                            key_prefix=k["key_prefix"],
                            key_hash=k["key_hash"],
                            scopes=[ApiKeyScope(s) for s in k.get("scopes", [])],
                            revoked=k.get("revoked", False),
                        )
                        for k in data.get("api_keys", [])
                    ]
                    self._accounts[acct.id] = acct
                except Exception:
                    pass  # nosec B110 — graceful degradation; error logged upstream

            logger.info("devocity: loaded %d accounts from Redis", sanitize_for_log(len(self._accounts)))
        except Exception as exc:
            logger.warning("devocity: Redis hydration skipped: %s", sanitize_for_log(exc))

    async def _persist_account(self, account: DeveloperAccount) -> None:
        try:
            from src.core.redis_store import get_store

            store = await get_store()
            data = {
                "id": account.id,
                "user_id": account.user_id,
                "display_name": account.display_name,
                "created_at": account.created_at,
                "api_keys": [
                    {
                        "id": k.id,
                        "developer_id": k.developer_id,
                        "name": k.name,
                        "key_prefix": k.key_prefix,
                        "key_hash": k.key_hash,
                        "scopes": [s.value for s in k.scopes],
                        "revoked": k.revoked,
                        "created_at": k.created_at,
                    }
                    for k in account.api_keys
                ],
                "webhooks": [
                    {"id": w.id, "url": w.url, "events": w.events} for w in account.webhooks
                ],
            }
            await store.set(f"devocity:account:{account.id}", data, ttl=_ACCOUNT_TTL)
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream

    def _fire_persist(self, account: DeveloperAccount) -> None:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._persist_account(account))
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream

    def create_account(self, user_id: str, display_name: str) -> DeveloperAccount:
        account = DeveloperAccount(user_id=user_id, display_name=display_name)
        self._accounts[account.id] = account
        self._fire_persist(account)
        self._emit("devocity.account.created", {"account_id": account.id, "user_id": user_id})
        logger.info(
            "devocity: account created id=%s user=%s",
            sanitize_for_log(account.id),
            sanitize_for_log(user_id),
        )  # codeql[py/cleartext-logging]
        return account

    def get_account(self, account_id: str) -> Optional[DeveloperAccount]:
        return self._accounts.get(account_id)

    def get_account_by_user(self, user_id: str) -> Optional[DeveloperAccount]:
        for a in self._accounts.values():
            if a.user_id == user_id:
                return a
        return None

    def issue_api_key(
        self,
        account_id: str,
        name: str,
        scopes: Optional[List[ApiKeyScope]] = None,
    ) -> Optional[tuple]:
        """Returns (plain_key, ApiKey) or None."""
        account = self._accounts.get(account_id)
        if not account:
            return None
        plain = "trx_" + secrets.token_hex(28)
        import hashlib

        key_hash = hashlib.sha256(plain.encode()).hexdigest()
        api_key = ApiKey(
            developer_id=account_id,
            name=name,
            key_prefix=plain[:8],
            key_hash=key_hash,
            scopes=scopes or [ApiKeyScope.READ],
        )
        account.api_keys.append(api_key)
        self._fire_persist(account)
        self._emit("devocity.apikey.issued", {"account_id": account_id, "key_id": api_key.id})
        return plain, api_key

    def revoke_api_key(self, account_id: str, key_id: str) -> bool:
        account = self._accounts.get(account_id)
        if not account:
            return False
        for k in account.api_keys:
            if k.id == key_id:
                k.revoked = True
                self._fire_persist(account)
                return True
        return False

    def register_webhook(
        self,
        account_id: str,
        url: str,
        events: List[str],
    ) -> Optional[WebhookEndpoint]:
        account = self._accounts.get(account_id)
        if not account:
            return None
        webhook = WebhookEndpoint(developer_id=account_id, url=url, events=events)
        account.webhooks.append(webhook)
        self._emit(
            "devocity.webhook.registered",
            {"account_id": account_id, "webhook_id": webhook.id},
        )
        return webhook

    def guides(self) -> List[Dict[str, Any]]:
        return _GUIDES

    def stats(self) -> Dict[str, Any]:
        total_keys = sum(
            len([k for k in a.api_keys if not k.revoked]) for a in self._accounts.values()
        )
        return {
            "service": "devocity",
            "total_accounts": len(self._accounts),
            "total_active_keys": total_keys,
            "guides": len(_GUIDES),
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                event_type,
                category=EventCategory.DATA,
                service="devocity",
                metadata=metadata or {},
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


_devocity: Optional[DevOcity] = None


def get_devocity() -> DevOcity:
    global _devocity
    if _devocity is None:
        _devocity = DevOcity()
    return _devocity
