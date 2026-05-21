"""
agent_types.py — Specialist Agent Profiles for Tranc3 Platform (Phase 5)

Defines the AgentType enum for categorizing specialist agents and the
AgentProfile dataclass that captures each agent type's capabilities,
preferred tools, and behavioral parameters.

Agent types:
  - GENERAL:     versatile all-rounder, balanced across all domains
  - RESEARCHER:  information gathering, analysis, knowledge synthesis
  - CODER:       code generation, debugging, refactoring, testing
  - PLANNER:     task decomposition, scheduling, resource allocation
  - ANALYZER:    data analysis, pattern detection, statistical reasoning
  - ORCHESTRATOR: multi-agent coordination, workflow management
  - GUARDIAN:    security, compliance, anomaly detection, safety

Each profile specifies:
  - default tools the agent prefers to use
  - behavioral parameters (creativity, caution, thoroughness)
  - capability tags for AttentionRouter-based service discovery

Zero-cost: pure Python, no external dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent type enum
# ---------------------------------------------------------------------------


class AgentType(str, Enum):
    """Classification of specialist agent types."""

    GENERAL = "general"
    RESEARCHER = "researcher"
    CODER = "coder"
    PLANNER = "planner"
    ANALYZER = "analyzer"
    ORCHESTRATOR = "orchestrator"
    GUARDIAN = "guardian"


# ---------------------------------------------------------------------------
# Agent profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentProfile:
    """
    Immutable profile describing an agent type's capabilities and behavioral
    parameters. Used by AgentRuntime to configure behavior, by TaskDecomposer
    to match subtasks to agents, and by AttentionRouter for service discovery.
    """

    agent_type: AgentType
    description: str
    capability_tags: FrozenSet[str]
    preferred_tools: FrozenSet[str]
    creativity: float = 0.5       # 0.0 (conservative) to 1.0 (creative)
    caution: float = 0.5          # 0.0 (aggressive) to 1.0 (cautious)
    thoroughness: float = 0.5     # 0.0 (quick) to 1.0 (thorough)
    max_concurrent_tasks: int = 3
    default_priority: int = 5
    reflection_enabled: bool = True
    memory_retention_sec: float = 3600.0  # how long episodic memories persist

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the profile to a plain dict."""
        return {
            "agent_type": self.agent_type.value,
            "description": self.description,
            "capability_tags": sorted(self.capability_tags),
            "preferred_tools": sorted(self.preferred_tools),
            "creativity": self.creativity,
            "caution": self.caution,
            "thoroughness": self.thoroughness,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "default_priority": self.default_priority,
            "reflection_enabled": self.reflection_enabled,
            "memory_retention_sec": self.memory_retention_sec,
        }

    def matches_tags(self, required_tags: Set[str]) -> float:
        """
        Return a 0.0–1.0 score indicating how well this profile matches
        a set of required capability tags. Uses Jaccard similarity.
        """
        if not required_tags:
            return 1.0
        available = set(self.capability_tags)
        if not available:
            return 0.0
        intersection = available & required_tags
        union = available | required_tags
        return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------


PROFILES: Dict[AgentType, AgentProfile] = {
    AgentType.GENERAL: AgentProfile(
        agent_type=AgentType.GENERAL,
        description=(
            "General-purpose agent capable of handling a wide range of tasks. "
            "Balanced creativity, caution, and thoroughness. Good default choice "
            "when no specialist is required."
        ),
        capability_tags=frozenset({
            "general", "reasoning", "communication", "planning",
            "tool-use", "adaptation",
        }),
        preferred_tools=frozenset({
            "execute_code", "search_skills", "query_vector_store",
            "run_workflow", "get_system_health",
        }),
        creativity=0.5,
        caution=0.5,
        thoroughness=0.5,
        max_concurrent_tasks=3,
        default_priority=5,
    ),
    AgentType.RESEARCHER: AgentProfile(
        agent_type=AgentType.RESEARCHER,
        description=(
            "Information gathering and synthesis specialist. Excels at "
            "searching knowledge bases, analyzing documents, and synthesizing "
            "findings into coherent reports. High thoroughness, moderate caution."
        ),
        capability_tags=frozenset({
            "research", "search", "analysis", "synthesis", "knowledge",
            "document-processing", "summarization",
        }),
        preferred_tools=frozenset({
            "query_vector_store", "search_skills", "ingest_document",
            "knowledge_graph_query", "knowledge_graph_path",
            "knowledge_graph_expand", "collective_memory_query",
        }),
        creativity=0.4,
        caution=0.6,
        thoroughness=0.8,
        max_concurrent_tasks=5,
        default_priority=5,
    ),
    AgentType.CODER: AgentProfile(
        agent_type=AgentType.CODER,
        description=(
            "Code generation, debugging, and refactoring specialist. "
            "Skilled at writing clean code, fixing bugs, adding tests, and "
            "refactoring for performance and maintainability."
        ),
        capability_tags=frozenset({
            "coding", "debugging", "refactoring", "testing", "code-review",
            "implementation", "optimization",
        }),
        preferred_tools=frozenset({
            "execute_code", "search_skills", "run_workflow",
            "neural_mesh_emit", "attention_route",
        }),
        creativity=0.6,
        caution=0.7,
        thoroughness=0.7,
        max_concurrent_tasks=2,
        default_priority=6,
    ),
    AgentType.PLANNER: AgentProfile(
        agent_type=AgentType.PLANNER,
        description=(
            "Task decomposition and scheduling specialist. Breaks complex goals "
            "into manageable subtasks, determines optimal execution order, and "
            "allocates resources. High thoroughness, strong planning capabilities."
        ),
        capability_tags=frozenset({
            "planning", "decomposition", "scheduling", "resource-allocation",
            "prioritization", "workflow-design", "estimation",
        }),
        preferred_tools=frozenset({
            "run_workflow", "register_workflow", "grid_list_workflows",
            "attention_route", "causal_predict",
        }),
        creativity=0.3,
        caution=0.6,
        thoroughness=0.9,
        max_concurrent_tasks=4,
        default_priority=7,
    ),
    AgentType.ANALYZER: AgentProfile(
        agent_type=AgentType.ANALYZER,
        description=(
            "Data analysis and pattern detection specialist. Excels at "
            "statistical reasoning, anomaly detection, trend identification, "
            "and generating data-driven insights."
        ),
        capability_tags=frozenset({
            "analysis", "statistics", "anomaly-detection", "pattern-recognition",
            "data-processing", "visualization", "insight-generation",
        }),
        preferred_tools=frozenset({
            "execute_code", "query_vector_store", "collective_memory_query",
            "causal_predict", "causal_diagnose", "meta_learn_adapt",
        }),
        creativity=0.3,
        caution=0.7,
        thoroughness=0.8,
        max_concurrent_tasks=3,
        default_priority=5,
    ),
    AgentType.ORCHESTRATOR: AgentProfile(
        agent_type=AgentType.ORCHESTRATOR,
        description=(
            "Multi-agent coordination and workflow management specialist. "
            "Orchestrates teams of agents, manages inter-agent communication, "
            "and ensures coherent execution of complex multi-step plans."
        ),
        capability_tags=frozenset({
            "orchestration", "coordination", "communication", "delegation",
            "monitoring", "workflow-management", "agent-routing",
        }),
        preferred_tools=frozenset({
            "run_workflow", "register_workflow", "grid_list_workflows",
            "neural_mesh_emit", "attention_route", "collective_memory_store",
        }),
        creativity=0.4,
        caution=0.7,
        thoroughness=0.7,
        max_concurrent_tasks=6,
        default_priority=8,
    ),
    AgentType.GUARDIAN: AgentProfile(
        agent_type=AgentType.GUARDIAN,
        description=(
            "Security, compliance, and safety specialist. Monitors for anomalies, "
            "enforces safety constraints, validates outputs, and ensures system "
            "integrity. Very high caution and thoroughness."
        ),
        capability_tags=frozenset({
            "security", "compliance", "anomaly-detection", "safety",
            "validation", "audit", "risk-assessment",
        }),
        preferred_tools=frozenset({
            "get_system_health", "causal_diagnose", "collective_memory_query",
            "observatory_observe", "attention_route",
        }),
        creativity=0.1,
        caution=0.95,
        thoroughness=0.95,
        max_concurrent_tasks=4,
        default_priority=9,
        reflection_enabled=True,
    ),
}


def get_profile(agent_type: AgentType) -> AgentProfile:
    """Return the built-in profile for an agent type, or GENERAL as fallback."""
    return PROFILES.get(agent_type, PROFILES[AgentType.GENERAL])


def get_profile_by_name(name: str) -> AgentProfile:
    """Look up a profile by string name (case-insensitive). Returns GENERAL if unknown."""
    try:
        agent_type = AgentType(name.lower())
    except ValueError:
        logger.warning("Unknown agent type '%s', falling back to GENERAL", name)
        agent_type = AgentType.GENERAL
    return get_profile(agent_type)


def list_profiles() -> List[Dict[str, Any]]:
    """Return serialized profiles for all agent types."""
    return [profile.to_dict() for profile in PROFILES.values()]


def find_best_profile(required_tags: Set[str]) -> AgentProfile:
    """
    Find the agent profile that best matches a set of required capability tags.
    Uses Jaccard similarity scoring across all profiles.
    """
    best_profile = PROFILES[AgentType.GENERAL]
    best_score = best_profile.matches_tags(required_tags)

    for profile in PROFILES.values():
        score = profile.matches_tags(required_tags)
        if score > best_score:
            best_score = score
            best_profile = profile

    return best_profile
