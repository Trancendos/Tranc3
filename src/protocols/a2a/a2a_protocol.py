"""
A2A Protocol — Agent-to-Agent Communication (Python Implementation)
====================================================================

Implements Google's Agent-to-Agent (A2A) protocol for the Tranc3 ecosystem.
This Python version mirrors the TypeScript implementation and provides
full interoperability through shared JSON message formats.

Key components:
  - AgentCard: Describes an agent's capabilities and endpoints
  - A2AMessage: Structured envelope for inter-agent communication
  - A2ARouter: Routes messages between agents with skill-based matching
  - A2AClient: Client interface for sending/receiving A2A messages
  - A2ANetwork: Top-level coordinator for multi-hub deployments
  - InMemoryA2ATransport: Single-process transport
  - HttpA2ATransport: HTTP REST transport for cross-process communication
"""

from __future__ import annotations  # noqa: I001

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger("tranc3.a2a")


# ─────────────────────────────────────────────────────────────────────────────
# A2A Types
# ─────────────────────────────────────────────────────────────────────────────


class A2AMessageType(str, Enum):
    """Types of A2A messages"""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"
    QUERY = "query"
    DELEGATE = "delegate"
    ESCALATE = "escalate"
    HEARTBEAT = "heartbeat"


class A2AResponseStatus(str, Enum):
    """Status codes for A2A responses"""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    DELEGATED = "delegated"


class A2APriority(int, Enum):
    """Message priority levels"""

    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15
    EMERGENCY = 20


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AgentSkill:
    """Describes a single capability an agent can perform."""

    id: str
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSkill":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", {}),
            output_schema=data.get("outputSchema", {}),
            tags=data.get("tags", []),
        )


@dataclass
class AgentCard:
    """
    Describes an agent's capabilities, skills, and endpoints.
    Used for agent discovery and routing decisions.
    """

    id: str
    name: str
    description: str
    skills: List[AgentSkill] = field(default_factory=list)
    endpoints: Dict[str, str] = field(default_factory=dict)
    tier: int = 4  # Default Tier 4 (Agent)
    pillar: str = ""
    hub: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skills": [s.to_dict() for s in self.skills],
            "endpoints": self.endpoints,
            "tier": self.tier,
            "pillar": self.pillar,
            "hub": self.hub,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCard":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            skills=[AgentSkill.from_dict(s) for s in data.get("skills", [])],
            endpoints=data.get("endpoints", {}),
            tier=data.get("tier", 4),
            pillar=data.get("pillar", ""),
            hub=data.get("hub", ""),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class A2ASecurityContext:
    """Security context for A2A message authorization."""

    auth_tier: int = 5
    permissions: List[str] = field(default_factory=list)
    token: str = ""
    source_bridge: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authTier": self.auth_tier,
            "permissions": self.permissions,
            "token": self.token,
            "sourceBridge": self.source_bridge,
        }


@dataclass
class A2AMessage:
    """
    Structured envelope for A2A communication.
    Compatible with Google's A2A protocol specification.
    """

    id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:12]}")
    type: A2AMessageType = A2AMessageType.REQUEST
    sender: str = ""
    recipient: str = ""
    skill_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: A2APriority = A2APriority.NORMAL
    security: A2ASecurityContext = field(default_factory=A2ASecurityContext)
    ttl_ms: int = 30000
    retry_count: int = 0
    max_retries: int = 3
    correlation_id: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "skillId": self.skill_id,
            "payload": self.payload,
            "priority": self.priority.value,
            "security": self.security.to_dict(),
            "ttlMs": self.ttl_ms,
            "retryCount": self.retry_count,
            "maxRetries": self.max_retries,
            "correlationId": self.correlation_id,
            "createdAt": self.created_at,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2AMessage":
        security_data = data.get("security", {})
        security = A2ASecurityContext(
            auth_tier=security_data.get("authTier", 5),
            permissions=security_data.get("permissions", []),
            token=security_data.get("token", ""),
            source_bridge=security_data.get("sourceBridge", ""),
        )
        return cls(
            id=data.get("id", f"msg-{uuid.uuid4().hex[:12]}"),
            type=A2AMessageType(data.get("type", "request")),
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            skill_id=data.get("skillId", ""),
            payload=data.get("payload", {}),
            priority=A2APriority(data.get("priority", 5)),
            security=security,
            ttl_ms=data.get("ttlMs", 30000),
            retry_count=data.get("retryCount", 0),
            max_retries=data.get("maxRetries", 3),
            correlation_id=data.get("correlationId", ""),
            created_at=data.get("createdAt", time.time()),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "A2AMessage":
        return cls.from_dict(json.loads(json_str))


@dataclass
class A2AResponse:
    """Response to an A2A message."""

    id: str = field(default_factory=lambda: f"res-{uuid.uuid4().hex[:12]}")
    correlation_id: str = ""
    status: A2AResponseStatus = A2AResponseStatus.SUCCESS
    sender: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    delegated_to: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "correlationId": self.correlation_id,
            "status": self.status.value,
            "sender": self.sender,
            "payload": self.payload,
            "error": self.error,
            "delegatedTo": self.delegated_to,
            "createdAt": self.created_at,
        }


@dataclass
class A2ARouteRule:
    """Routing rule for the A2A router."""

    sender_pattern: str = "*"
    recipient_pattern: str = "*"
    skill_pattern: str = "*"
    target_agent: str = ""
    priority_boost: int = 0
    enabled: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Transport Layer
# ─────────────────────────────────────────────────────────────────────────────


class A2ATransport(ABC):
    """Abstract base class for A2A transports."""

    @abstractmethod
    async def send(self, message: A2AMessage, endpoint: str) -> A2AResponse: ...

    @abstractmethod
    async def broadcast(self, message: A2AMessage, endpoints: List[str]) -> List[A2AResponse]: ...

    async def start(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Optional startup hook; in-process transports may not need any setup."""
        return None

    async def stop(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Optional shutdown hook; in-process transports may not need any teardown."""
        return None


class InMemoryA2ATransport(A2ATransport):
    """
    In-memory transport for single-process deployments.
    Agents communicate directly through shared references.
    """

    def __init__(self):
        self._handlers: Dict[str, Callable[[A2AMessage], Awaitable[A2AResponse]]] = {}

    def register_handler(
        self,
        agent_id: str,
        handler: Callable[[A2AMessage], Awaitable[A2AResponse]],
    ) -> None:
        self._handlers[agent_id] = handler

    async def send(self, message: A2AMessage, endpoint: str) -> A2AResponse:
        handler = self._handlers.get(endpoint)
        if not handler:
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.REFUSED,
                sender="transport",
                error=f"No handler registered for endpoint: {endpoint}",
            )
        try:
            return await handler(message)
        except Exception as e:
            logger.error(f"InMemory transport error: {e}")
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.FAILURE,
                sender="transport",
                error=str(e),
            )

    async def broadcast(self, message: A2AMessage, endpoints: List[str]) -> List[A2AResponse]:
        tasks = [self.send(message, ep) for ep in endpoints]
        return await asyncio.gather(*tasks, return_exceptions=False)


class HttpA2ATransport(A2ATransport):
    """
    HTTP REST transport for cross-process deployments.
    Sends A2A messages as JSON over HTTP POST requests.
    """

    def __init__(self, timeout_seconds: float = 30.0):
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def send(self, message: A2AMessage, endpoint: str) -> A2AResponse:
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

        url = f"{endpoint}/a2a/message"
        try:
            async with self._session.post(url, json=message.to_dict()) as resp:
                data = await resp.json()
                return A2AResponse(
                    id=data.get("id", f"res-{uuid.uuid4().hex[:12]}"),
                    correlation_id=data.get("correlationId", message.id),
                    status=A2AResponseStatus(data.get("status", "success")),
                    sender=data.get("sender", ""),
                    payload=data.get("payload", {}),
                    error=data.get("error", ""),
                )
        except asyncio.TimeoutError:
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.TIMEOUT,
                sender="transport",
                error=f"Request to {url} timed out",
            )
        except Exception as e:
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.FAILURE,
                sender="transport",
                error=str(e),
            )

    async def broadcast(self, message: A2AMessage, endpoints: List[str]) -> List[A2AResponse]:
        tasks = [self.send(message, ep) for ep in endpoints]
        return list(await asyncio.gather(*tasks, return_exceptions=False))


# ─────────────────────────────────────────────────────────────────────────────
# A2A Router
# ─────────────────────────────────────────────────────────────────────────────


class A2ARouter:
    """
    Routes A2A messages between agents.
    Supports skill-based routing, agent discovery, and custom routing rules.
    """

    def __init__(self):
        self._agents: Dict[str, AgentCard] = {}
        self._skill_index: Dict[str, List[str]] = {}  # skill_id → [agent_ids]
        self._rules: List[A2ARouteRule] = []
        self._load_counters: Dict[str, int] = {}

    def register(self, card: AgentCard) -> None:
        """Register an agent's capabilities."""
        self._agents[card.id] = card
        self._load_counters[card.id] = 0

        # Index skills for routing
        for skill in card.skills:
            if skill.id not in self._skill_index:
                self._skill_index[skill.id] = []
            self._skill_index[skill.id].append(card.id)

        logger.info(
            f"A2A Router: Registered agent {card.id} ({card.name}) with {len(card.skills)} skills"
        )

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent."""
        card = self._agents.pop(agent_id, None)
        if card:
            for skill in card.skills:
                agents = self._skill_index.get(skill.id, [])
                if agent_id in agents:
                    agents.remove(agent_id)
        self._load_counters.pop(agent_id, None)

    def add_rule(self, rule: A2ARouteRule) -> None:
        """Add a routing rule."""
        self._rules.append(rule)

    def find_by_skill(self, skill_id: str) -> List[AgentCard]:
        """Find agents that have a specific skill."""
        agent_ids = self._skill_index.get(skill_id, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def find_by_tier(self, tier: int) -> List[AgentCard]:
        """Find agents at a specific tier."""
        return [card for card in self._agents.values() if card.tier == tier]

    def find_by_hub(self, hub: str) -> List[AgentCard]:
        """Find agents belonging to a specific hub."""
        return [card for card in self._agents.values() if card.hub == hub]

    def find_by_tag(self, tag: str) -> List[AgentCard]:
        """Find agents with a specific tag."""
        return [card for card in self._agents.values() if tag in card.tags]

    def resolve_recipient(self, message: A2AMessage) -> Optional[str]:
        """
        Resolve the destination for a message.
        Returns the agent ID that should handle this message.
        """
        # Direct recipient specified
        if message.recipient and message.recipient in self._agents:
            return message.recipient

        # Skill-based routing
        if message.skill_id:
            candidates = self._skill_index.get(message.skill_id, [])
            if candidates:
                # Least-loaded selection
                return min(candidates, key=lambda aid: self._load_counters.get(aid, 0))

        # Check routing rules
        import re

        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.sender_pattern != "*":
                if not re.match(rule.sender_pattern, message.sender):
                    continue
            if rule.recipient_pattern != "*":
                if not re.match(rule.recipient_pattern, message.recipient):
                    continue
            if rule.skill_pattern != "*":
                if not re.match(rule.skill_pattern, message.skill_id):
                    continue
            if rule.target_agent in self._agents:
                return rule.target_agent

        return message.recipient if message.recipient in self._agents else None

    def get_card(self, agent_id: str) -> Optional[AgentCard]:
        """Get an agent's card by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[AgentCard]:
        """List all registered agents."""
        return list(self._agents.values())

    def increment_load(self, agent_id: str) -> None:
        """Track message load for an agent."""
        self._load_counters[agent_id] = self._load_counters.get(agent_id, 0) + 1

    def decrement_load(self, agent_id: str) -> None:
        """Decrement load counter when message completes."""
        if agent_id in self._load_counters:
            self._load_counters[agent_id] = max(0, self._load_counters[agent_id] - 1)


# ─────────────────────────────────────────────────────────────────────────────
# A2A Client
# ─────────────────────────────────────────────────────────────────────────────


class A2AClient:
    """
    Client for an agent to send and receive A2A messages.
    Each agent gets its own client instance.
    """

    def __init__(
        self,
        agent_id: str,
        router: A2ARouter,
        transport: A2ATransport,
        message_handler: Optional[Callable[[A2AMessage], Awaitable[A2AResponse]]] = None,
    ):
        self.agent_id = agent_id
        self._router = router
        self._transport = transport
        self._handler = message_handler
        self._pending: Dict[str, asyncio.Future[A2AResponse]] = {}

    def set_handler(self, handler: Callable[[A2AMessage], Awaitable[A2AResponse]]) -> None:
        """Set the message handler for incoming messages."""
        self._handler = handler

    async def send_request(
        self,
        recipient: str,
        skill_id: str,
        payload: Dict[str, Any],
        priority: A2APriority = A2APriority.NORMAL,
        ttl_ms: int = 30000,
    ) -> A2AResponse:
        """Send a request to another agent and wait for the response."""
        message = A2AMessage(
            type=A2AMessageType.REQUEST,
            sender=self.agent_id,
            recipient=recipient,
            skill_id=skill_id,
            payload=payload,
            priority=priority,
            ttl_ms=ttl_ms,
            correlation_id=f"corr-{uuid.uuid4().hex[:12]}",
        )

        # Resolve the actual recipient through routing
        resolved = self._router.resolve_recipient(message)
        if not resolved:
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.REFUSED,
                sender=self.agent_id,
                error=f"No route to agent: {recipient}",
            )

        # Get the endpoint for the resolved agent
        card = self._router.get_card(resolved)
        endpoint = card.endpoints.get("a2a", resolved) if card else resolved

        self._router.increment_load(resolved)
        try:
            response = await self._transport.send(message, endpoint)
            return response
        finally:
            self._router.decrement_load(resolved)

    async def send_notification(
        self,
        recipient: str,
        payload: Dict[str, Any],
        priority: A2APriority = A2APriority.NORMAL,
    ) -> None:
        """Send a fire-and-forget notification to another agent."""
        message = A2AMessage(
            type=A2AMessageType.NOTIFICATION,
            sender=self.agent_id,
            recipient=recipient,
            payload=payload,
            priority=priority,
        )
        resolved = self._router.resolve_recipient(message)
        if resolved:
            card = self._router.get_card(resolved)
            endpoint = card.endpoints.get("a2a", resolved) if card else resolved
            await self._transport.send(message, endpoint)

    async def broadcast(
        self,
        payload: Dict[str, Any],
        skill_id: str = "",
        priority: A2APriority = A2APriority.NORMAL,
    ) -> List[A2AResponse]:
        """Broadcast a message to all agents with a matching skill."""
        if skill_id:
            cards = self._router.find_by_skill(skill_id)
        else:
            cards = self._router.list_agents()

        # Exclude self
        cards = [c for c in cards if c.id != self.agent_id]
        endpoints = [c.endpoints.get("a2a", c.id) for c in cards]

        message = A2AMessage(
            type=A2AMessageType.BROADCAST,
            sender=self.agent_id,
            skill_id=skill_id,
            payload=payload,
            priority=priority,
        )

        return await self._transport.broadcast(message, endpoints)

    async def delegate(
        self,
        recipient: str,
        skill_id: str,
        payload: Dict[str, Any],
    ) -> A2AResponse:
        """Delegate a task to another agent (transfer of responsibility)."""
        message = A2AMessage(
            type=A2AMessageType.DELEGATE,
            sender=self.agent_id,
            recipient=recipient,
            skill_id=skill_id,
            payload=payload,
            priority=A2APriority.HIGH,
        )
        resolved = self._router.resolve_recipient(message)
        if not resolved:
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.REFUSED,
                error=f"No route to delegate target: {recipient}",
            )
        card = self._router.get_card(resolved)
        endpoint = card.endpoints.get("a2a", resolved) if card else resolved
        return await self._transport.send(message, endpoint)

    async def escalate(
        self,
        recipient: str,
        payload: Dict[str, Any],
    ) -> A2AResponse:
        """Escalate an issue to a higher-tier agent."""
        message = A2AMessage(
            type=A2AMessageType.ESCALATE,
            sender=self.agent_id,
            recipient=recipient,
            payload=payload,
            priority=A2APriority.HIGH,
        )
        resolved = self._router.resolve_recipient(message)
        if not resolved:
            return A2AResponse(
                correlation_id=message.id,
                status=A2AResponseStatus.REFUSED,
                error=f"No route to escalation target: {recipient}",
            )
        card = self._router.get_card(resolved)
        endpoint = card.endpoints.get("a2a", resolved) if card else resolved
        return await self._transport.send(message, endpoint)

    async def handle_message(self, message: A2AMessage) -> A2AResponse:
        """Handle an incoming A2A message."""
        if self._handler:
            return await self._handler(message)
        return A2AResponse(
            correlation_id=message.id,
            status=A2AResponseStatus.REFUSED,
            sender=self.agent_id,
            error="No message handler registered",
        )


# ─────────────────────────────────────────────────────────────────────────────
# A2A Network — Top-Level Coordinator
# ─────────────────────────────────────────────────────────────────────────────


class A2ANetwork:
    """
    Top-level coordinator for A2A communication across the ecosystem.
    Manages hubs, creates clients, and provides the unified API.
    """

    def __init__(self, transport: Optional[A2ATransport] = None):
        self._router = A2ARouter()
        self._transport = transport or InMemoryA2ATransport()
        self._clients: Dict[str, A2AClient] = {}

    @property
    def router(self) -> A2ARouter:
        return self._router

    @property
    def transport(self) -> A2ATransport:
        return self._transport

    def register_agent(
        self,
        card: AgentCard,
        message_handler: Optional[Callable[[A2AMessage], Awaitable[A2AResponse]]] = None,
    ) -> A2AClient:
        """Register an agent and get a client for it."""
        self._router.register(card)
        client = A2AClient(
            agent_id=card.id,
            router=self._router,
            transport=self._transport,
            message_handler=message_handler,
        )
        self._clients[card.id] = client

        # If in-memory transport, register the handler
        if isinstance(self._transport, InMemoryA2ATransport) and message_handler:
            self._transport.register_handler(card.id, message_handler)

        logger.info(f"A2A Network: Registered agent {card.id}")
        return client

    def get_client(self, agent_id: str) -> Optional[A2AClient]:
        """Get a client for a registered agent."""
        return self._clients.get(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the network."""
        self._router.unregister(agent_id)
        self._clients.pop(agent_id, None)

    async def start(self) -> None:
        """Start the transport layer."""
        await self._transport.start()
        logger.info("A2A Network started")

    async def stop(self) -> None:
        """Stop the transport layer."""
        await self._transport.stop()
        logger.info("A2A Network stopped")

    def health_check(self) -> Dict[str, Any]:
        """Get health status of the A2A network."""
        return {
            "status": "healthy",
            "registered_agents": len(self._clients),
            "routing_rules": len(self._router._rules),
            "skills_indexed": len(self._router._skill_index),
            "transport_type": type(self._transport).__name__,
        }
