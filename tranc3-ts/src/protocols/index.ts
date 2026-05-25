/**
 * Tranc3 Protocols — Unified Export
 *
 * All protocol implementations for the Tranc3 ecosystem:
 *
 *   A2A Protocol    — Agent-to-Agent communication (Google A2A compatible)
 *   Three-Bridge    — Infinity/Nexus/HIVE traffic separation via Sentinel Station
 *   HIL-A Protocol  — Human-In-Loop-Action tier escalation chain
 */

// A2A — Agent-to-Agent Protocol
export { A2ANetwork, A2AClient, A2ARouter } from './a2a';
export type {
  AgentCard,
  AgentSkill,
  A2AMessage,
  A2AResponse,
  A2AProtocol,
  A2AMessageType,
  A2APriority,
  A2ASecurityContext,
  A2ARouteRule,
} from './a2a';
export { InMemoryA2ATransport, HttpA2ATransport } from './a2a';
export type { IA2ATransport } from './a2a';

// Three-Bridge Architecture
export { SentinelStation, InfinityBridge, NexusBridge, HIVEBridge } from './three_bridge';
export type {
  BridgeDomain,
  BridgeStatus,
  TrafficClass,
  BridgeTrafficPacket,
  BridgeHealthReport,
  RoutingRule,
  IBridge,
} from './three_bridge';

// HIL-A — Human-In-Loop-Action Protocol
export { HILAChain, submitAndWait } from './hil_a';
export type {
  HILATier,
  HILAActionStatus,
  HILAActionCategory,
  HILADecision,
  HILAAction,
  HILAConfig,
  HILATierHandler,
} from './hil_a';
