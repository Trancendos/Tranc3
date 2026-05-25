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
    AgentCard,
    AgentSkill,
    A2AMessage,
    A2AMessageType,
    A2AResponse,
    A2AResponseStatus,
    A2APriority,
    A2ASecurityContext,
    A2ARouteRule,
    A2ARouter,
    A2AClient,
    A2ANetwork,
    InMemoryA2ATransport,
    HttpA2ATransport,
)

from .three_bridge import (
    BridgeDomain,
    BridgeStatus,
    TrafficClass,
    BridgeTrafficPacket,
    BridgeHealthReport,
    RoutingRule,
    EscalationRequest,
    EscalationResult,
    IBridge,
    InfinityBridge,
    NexusBridge,
    HIVEBridge,
    SentinelStation,
    TRAFFIC_TO_BRIDGE,
)

from .hil_a import (
    HILAActionStatus,
    HILAActionCategory,
    HILADecisionType,
    HILADecision,
    HILAAction,
    HILAConfig,
    HILATierHandler,
    HILAChain,
    DEFAULT_CATEGORY_TIERS,
    DEFAULT_TIER_TIMEOUTS,
)
