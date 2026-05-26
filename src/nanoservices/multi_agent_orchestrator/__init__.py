"""Multi-Agent Orchestrator — Phase 9

Coordinates multiple AI agents for collaborative task execution.
"""

from .multi_agent_orchestrator import (
    AgentRole,
    AgentState,
    MessageType,
    AgentMessage,
    AgentCapability,
    AgentProfile,
    OrchestratedTask,
    ConsensusProposal,
    MessageBus,
    CapabilityMatcher,
    ConsensusEngine,
    MultiAgentOrchestrator,
)

__all__ = [
    "AgentRole",
    "AgentState",
    "MessageType",
    "AgentMessage",
    "AgentCapability",
    "AgentProfile",
    "OrchestratedTask",
    "ConsensusProposal",
    "MessageBus",
    "CapabilityMatcher",
    "ConsensusEngine",
    "MultiAgentOrchestrator",
]
