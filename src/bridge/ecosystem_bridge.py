"""
Python-TypeScript Ecosystem Bridge — Python Implementation
===========================================================

Provides the Python side of the bridge connecting to the TypeScript
ecosystem. Uses JSON-RPC 2.0 over HTTP for communication.

Key components:
  - EcosystemBridge: Client for calling TypeScript services from Python
  - EcosystemRegistry: Unified registry of all 43 platform entities
  - BridgeConfig: Configuration for the bridge connection
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("tranc3.bridge")


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────

class BridgeTransport(str, Enum):
    HTTP = "http"
    STDIO = "stdio"
    IN_MEMORY = "in-memory"


@dataclass
class BridgeEndpoint:
    """A registered bridge endpoint."""
    id: str
    ecosystem: str  # 'typescript' or 'python'
    service: str
    transport: BridgeTransport = BridgeTransport.HTTP
    url: str = ""
    command: str = ""
    health_url: str = ""


@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"rpc-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params,
        }


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    id: str = ""
    result: Any = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JsonRpcResponse":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id", ""),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class BridgeConfig:
    """Bridge configuration."""
    python_base_url: str = "http://localhost:8000"
    typescript_base_url: str = "http://localhost:3000"
    transport: BridgeTransport = BridgeTransport.HTTP
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    health_monitoring: bool = True
    health_check_interval_seconds: float = 60.0


# ─────────────────────────────────────────────────────────────────────────────
# Ecosystem Bridge
# ─────────────────────────────────────────────────────────────────────────────

class EcosystemBridge:
    """
    The client that connects Python and TypeScript ecosystems.

    Provides methods to:
      - Call TypeScript services from Python
      - Register Python services for TypeScript to call
      - Share protocol messages across ecosystems
      - Monitor bridge health
    """

    def __init__(self, config: Optional[BridgeConfig] = None):
        self._config = config or BridgeConfig()
        self._endpoints: Dict[str, BridgeEndpoint] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected: bool = False
        self._health_task: Optional[asyncio.Task] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def config(self) -> BridgeConfig:
        return self._config

    # ─────────────────────────────────────────────────────────────────────────
    # Connection Management
    # ─────────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the bridge and begin health monitoring."""
        logger.info("Starting EcosystemBridge...")
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._config.timeout_seconds),
        )
        self._connected = True

        if self._config.health_monitoring:
            self._health_task = asyncio.create_task(self._health_loop())

        logger.info("EcosystemBridge started")

    async def stop(self) -> None:
        """Stop the bridge."""
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None

        if self._session:
            await self._session.close()
            self._session = None

        self._connected = False
        logger.info("EcosystemBridge stopped")

    # ─────────────────────────────────────────────────────────────────────────
    # Endpoint Registration
    # ─────────────────────────────────────────────────────────────────────────

    def register_endpoint(self, endpoint: BridgeEndpoint) -> None:
        """Register a bridge endpoint."""
        self._endpoints[endpoint.id] = endpoint
        logger.info(f"Registered bridge endpoint: {endpoint.id} ({endpoint.ecosystem}/{endpoint.service})")

    def get_endpoint(self, endpoint_id: str) -> Optional[BridgeEndpoint]:
        """Get a registered endpoint."""
        return self._endpoints.get(endpoint_id)

    def list_endpoints(self) -> List[BridgeEndpoint]:
        """List all registered endpoints."""
        return list(self._endpoints.values())

    # ─────────────────────────────────────────────────────────────────────────
    # JSON-RPC Calls
    # ─────────────────────────────────────────────────────────────────────────

    async def call_typescript(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Call a TypeScript service method from Python."""
        request = JsonRpcRequest(method=method, params=params or {})
        return await self._send_request(request, self._config.typescript_base_url)

    async def call_python(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Call a Python service method (local call via the bridge protocol)."""
        request = JsonRpcRequest(method=method, params=params or {})
        return await self._send_request(request, self._config.python_base_url)

    async def _send_request(self, request: JsonRpcRequest, base_url: str) -> Any:
        """Send a JSON-RPC request with retry logic."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._config.timeout_seconds),
            )

        url = f"{base_url}/rpc"
        last_error: Optional[Exception] = None

        for attempt in range(self._config.max_retries + 1):
            try:
                async with self._session.post(url, json=request.to_dict()) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}: {resp.reason}")

                    data = await resp.json()
                    response = JsonRpcResponse.from_dict(data)

                    if response.error:
                        raise Exception(f"RPC Error {response.error.get('code')}: {response.error.get('message')}")

                    return response.result

            except Exception as e:
                last_error = e
                logger.warning(f"Bridge request attempt {attempt + 1} failed: {e}")

                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.backoff_seconds * (attempt + 1))

        raise last_error or Exception("Bridge request failed")

    # ─────────────────────────────────────────────────────────────────────────
    # Protocol Bridge Methods
    # ─────────────────────────────────────────────────────────────────────────

    async def send_a2a_to_typescript(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send an A2A message to the TypeScript ecosystem."""
        result = await self.call_typescript("a2a.handleMessage", {"message": message})
        return result or {}

    async def send_a2a_to_python(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send an A2A message to the Python ecosystem."""
        result = await self.call_python("a2a.handleMessage", {"message": message})
        return result or {}

    async def route_traffic_via_typescript(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """Route traffic through the TypeScript Three-Bridge coordinator."""
        result = await self.call_typescript("threeBridge.routeTraffic", {"packet": packet})
        return result or {}

    async def submit_hila_action_to_typescript(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a HIL-A action to the TypeScript chain."""
        result = await self.call_typescript("hilA.submitAction", {"action": action})
        return result or {}

    # ─────────────────────────────────────────────────────────────────────────
    # Health Monitoring
    # ─────────────────────────────────────────────────────────────────────────

    async def check_health(self) -> Dict[str, Any]:
        """Check the health of the bridge and all endpoints."""
        python_status = "offline"
        typescript_status = "offline"

        try:
            if self._session:
                async with self._session.get(f"{self._config.python_base_url}/health") as resp:
                    python_status = "healthy" if resp.status == 200 else "degraded"
        except Exception:
            python_status = "offline"

        try:
            if self._session:
                async with self._session.get(f"{self._config.typescript_base_url}/health") as resp:
                    typescript_status = "healthy" if resp.status == 200 else "degraded"
        except Exception:
            typescript_status = "offline"

        if python_status == "healthy" and typescript_status == "healthy":
            overall = "healthy"
        elif python_status == "offline" and typescript_status == "offline":
            overall = "offline"
        else:
            overall = "degraded"

        return {
            "bridge": overall,
            "python": python_status,
            "typescript": typescript_status,
            "endpoints": len(self._endpoints),
        }

    async def _health_loop(self) -> None:
        """Periodic health check loop."""
        while self._connected:
            try:
                health = await self.check_health()
                if health["bridge"] != "healthy":
                    logger.warning(f"Bridge health: {health['bridge']} (python={health['python']}, typescript={health['typescript']})")
            except Exception as e:
                logger.error(f"Health check failed: {e}")

            await asyncio.sleep(self._config.health_check_interval_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# Unified Ecosystem Registry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EcosystemEntity:
    """Entity information shared between Python and TypeScript."""
    pid: str = ""
    aid: str = ""
    location: str = ""
    pillar: str = ""
    lead_ai: str = ""
    primary_function: str = ""
    primes: List[str] = field(default_factory=list)
    agent_alpha: Dict[str, str] = field(default_factory=dict)
    agent_beta: Dict[str, str] = field(default_factory=dict)
    bots: List[Dict[str, str]] = field(default_factory=list)
    worker_port: Optional[int] = None
    worker_path: Optional[str] = None
    source: str = "python"  # 'typescript', 'python', or 'both'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "aid": self.aid,
            "location": self.location,
            "pillar": self.pillar,
            "leadAi": self.lead_ai,
            "primaryFunction": self.primary_function,
            "primes": self.primes,
            "agentAlpha": self.agent_alpha,
            "agentBeta": self.agent_beta,
            "bots": self.bots,
            "workerPort": self.worker_port,
            "workerPath": self.worker_path,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EcosystemEntity":
        return cls(
            pid=data.get("pid", ""),
            aid=data.get("aid", ""),
            location=data.get("location", ""),
            pillar=data.get("pillar", ""),
            lead_ai=data.get("leadAi", ""),
            primary_function=data.get("primaryFunction", ""),
            primes=data.get("primes", []),
            agent_alpha=data.get("agentAlpha", {}),
            agent_beta=data.get("agentBeta", {}),
            bots=data.get("bots", []),
            worker_port=data.get("workerPort"),
            worker_path=data.get("workerPath"),
            source=data.get("source", "python"),
        )


class EcosystemRegistry:
    """
    Unified registry of all 43 platform entities.

    Loads entity data from both the Python and TypeScript codebases
    and provides a single source of truth for the entire ecosystem.
    """

    def __init__(self, bridge: Optional[EcosystemBridge] = None):
        self._entities: Dict[str, EcosystemEntity] = {}
        self._bridge = bridge

    async def load_from_typescript(self) -> int:
        """Load entities from the TypeScript ecosystem via the bridge."""
        if not self._bridge:
            logger.warning("No bridge configured — cannot load from TypeScript")
            return 0

        try:
            result = await self._bridge.call_typescript("registry.listEntities")
            if not isinstance(result, list):
                return 0

            count = 0
            for entity_data in result:
                entity = EcosystemEntity.from_dict(entity_data)
                existing = self._entities.get(entity.pid)
                entity.source = "both" if existing else "typescript"
                self._entities[entity.pid] = entity
                count += 1

            logger.info(f"Loaded {count} entities from TypeScript")
            return count
        except Exception as e:
            logger.error(f"Failed to load from TypeScript: {e}")
            return 0

    def load_from_platform_entities(self) -> int:
        """Load entities from the Python platform.py module."""
        try:
            from ..entities.platform import PLATFORM_ENTITIES
            count = 0
            for location, entity in PLATFORM_ENTITIES.items():
                ecosystem_entity = EcosystemEntity(
                    pid=entity.pid,
                    aid=entity.aid,
                    location=entity.location,
                    pillar=entity.pillar.value,
                    lead_ai=entity.lead_ai,
                    primary_function=entity.primary_function,
                    primes=entity.primes,
                    agent_alpha={
                        "codeName": entity.agent_alpha.code_name,
                        "sid": entity.agent_alpha.sid,
                    },
                    agent_beta={
                        "codeName": entity.agent_beta.code_name,
                        "sid": entity.agent_beta.sid,
                    },
                    bots=[
                        {"codeName": entity.bot_01.code_name, "nid": entity.bot_01.nid},
                        {"codeName": entity.bot_02.code_name, "nid": entity.bot_02.nid},
                        {"codeName": entity.bot_03.code_name, "nid": entity.bot_03.nid},
                        {"codeName": entity.bot_04.code_name, "nid": entity.bot_04.nid},
                    ],
                    worker_port=entity.worker_port,
                    worker_path=entity.worker_path,
                    source="python",
                )
                existing = self._entities.get(ecosystem_entity.pid)
                ecosystem_entity.source = "both" if existing else "python"
                self._entities[ecosystem_entity.pid] = ecosystem_entity
                count += 1

            logger.info(f"Loaded {count} entities from platform.py")
            return count
        except Exception as e:
            logger.error(f"Failed to load from platform.py: {e}")
            return 0

    def register_entity(self, entity: EcosystemEntity) -> None:
        """Register a single entity."""
        existing = self._entities.get(entity.pid)
        if existing:
            entity.source = "both"
        self._entities[entity.pid] = entity

    def register_entities(self, entities: List[EcosystemEntity]) -> None:
        """Register entities in bulk."""
        for entity in entities:
            self.register_entity(entity)
        logger.info(f"Registered {len(entities)} entities")

    def get_entity(self, pid: str) -> Optional[EcosystemEntity]:
        """Get an entity by PID."""
        return self._entities.get(pid)

    def get_entity_by_location(self, location: str) -> Optional[EcosystemEntity]:
        """Get an entity by location name."""
        for entity in self._entities.values():
            if entity.location == location:
                return entity
        return None

    def get_entities_by_pillar(self, pillar: str) -> List[EcosystemEntity]:
        """Get entities by pillar."""
        return [e for e in self._entities.values() if e.pillar == pillar]

    def get_entities_by_lead_ai(self, lead_ai: str) -> List[EcosystemEntity]:
        """Get entities by lead AI."""
        return [e for e in self._entities.values() if e.lead_ai == lead_ai]

    def list_entities(self) -> List[EcosystemEntity]:
        """List all entities."""
        return list(self._entities.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        entities = list(self._entities.values())
        by_pillar: Dict[str, int] = {}
        by_source: Dict[str, int] = {}

        for entity in entities:
            by_pillar[entity.pillar] = by_pillar.get(entity.pillar, 0) + 1
            by_source[entity.source] = by_source.get(entity.source, 0) + 1

        return {
            "totalEntities": len(entities),
            "byPillar": by_pillar,
            "bySource": by_source,
            "withWorkerPort": sum(1 for e in entities if e.worker_port is not None),
        }

    def health_check(self) -> Dict[str, Any]:
        """Health check for the registry."""
        total = len(self._entities)
        coverage = total / 43  # Canonical count is 43
        return {
            "status": "healthy" if coverage >= 1.0 else "degraded",
            "entities": total,
            "coverage": round(coverage * 100),
        }
