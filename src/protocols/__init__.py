"""
Tranc3 Protocols — Python Ecosystem
=====================================

Protocol implementations that mirror and interoperate with the
TypeScript protocol layer:

  A2A Protocol     — Agent-to-Agent communication (Google A2A compatible)
  Three-Bridge     — Infinity/Nexus/HIVE traffic separation via Sentinel Station
  HIL-A Protocol   — Human-In-Loop-Action tier escalation chain
"""

from .a2a import (
    A2AClient,
    A2AMessage,
    A2AMessageType,
    A2ANetwork,
    A2APriority,
    A2AResponse,
    A2AResponseStatus,
    A2ARouter,
    A2ARouteRule,
    A2ASecurityContext,
    AgentCard,
    AgentSkill,
    HttpA2ATransport,
    InMemoryA2ATransport,
)
from .hil_a import (
    DEFAULT_CATEGORY_TIERS,
    DEFAULT_TIER_TIMEOUTS,
    HILAAction,
    HILAActionCategory,
    HILAActionStatus,
    HILAChain,
    HILAConfig,
    HILADecision,
    HILADecisionType,
    HILATierHandler,
)
from .three_bridge import (
    TRAFFIC_TO_BRIDGE,
    BridgeDomain,
    BridgeHealthReport,
    BridgeStatus,
    BridgeTrafficPacket,
    EscalationRequest,
    EscalationResult,
    HIVEBridge,
    IBridge,
    InfinityBridge,
    NexusBridge,
    RoutingRule,
    SentinelStation,
    TrafficClass,
)

__all__ = [
    "AgentCard",
    "AgentSkill",
    "A2AMessage",
    "A2AMessageType",
    "A2AResponse",
    "A2AResponseStatus",
    "A2APriority",
    "A2ASecurityContext",
    "A2ARouteRule",
    "A2ARouter",
    "A2AClient",
    "A2ANetwork",
    "InMemoryA2ATransport",
    "HttpA2ATransport",
    "BridgeDomain",
    "BridgeStatus",
    "TrafficClass",
    "BridgeTrafficPacket",
    "BridgeHealthReport",
    "RoutingRule",
    "EscalationRequest",
    "EscalationResult",
    "IBridge",
    "InfinityBridge",
    "NexusBridge",
    "HIVEBridge",
    "SentinelStation",
    "TRAFFIC_TO_BRIDGE",
    "HILAActionStatus",
    "HILAActionCategory",
    "HILADecisionType",
    "HILADecision",
    "HILAAction",
    "HILAConfig",
    "HILATierHandler",
    "HILAChain",
    "DEFAULT_CATEGORY_TIERS",
    "DEFAULT_TIER_TIMEOUTS",
]
