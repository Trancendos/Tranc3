"""
AeonMind Definitions — Tier Hierarchy, Entity Types, Sentinel Channels.

Custom Hierarchy (MUST be preserved):
  Tier 0: HUMAN        — Human oversight and governance
  Tier 1: ORCHESTRATOR — Logical orchestrator managing AI complexes
  Tier 2: PRIME        — Prime coordinator for multi-agent systems
  Tier 3: AI           — The overarching ML/LLM Complex
  Tier 4: AGENT        — Lower-level autonomous AI
  Tier 5: BOT          — Stateless service worker/function
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

# ── Tier System ──────────────────────────────────────────────────────────────


class Tier(IntEnum):
    """Platform entity tier hierarchy."""

    HUMAN = 0
    ORCHESTRATOR = 1
    PRIME = 2
    AI = 3
    AGENT = 4
    BOT = 5


# ── Sentinel Channels ───────────────────────────────────────────────────────


class SentinelChannel(str, Enum):
    """Inter-entity communication channels for the sentinel broadcast system."""

    PLATFORM = "platform"
    AGENTS = "agents"
    MODELS = "models"
    WORKFLOWS = "workflows"
    SECURITY = "security"
    HIVE = "hive"
    NEXUS = "nexus"
    BRIDGE = "bridge"
    PILLARS = "pillars"
    INFRASTRUCTURE = "infrastructure"
    EVENTS = "events"


# ── Entity Types ─────────────────────────────────────────────────────────────


@dataclass
class BotService:
    """Tier 5 — Stateless service worker / function.

    Bots are the lowest-tier entities in the Tranc3 hierarchy.
    They perform single-purpose, stateless operations and cannot
    act autonomously — they are invoked by Agents or AI complexes.
    """

    id: str = field(default_factory=lambda: f"bot-{uuid.uuid4().hex[:8]}")
    name: str = "unnamed-bot"
    capability: str = "generic"
    stateless: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "idle"

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a stateless bot function."""
        self.status = "running"
        result = {
            "bot_id": self.id,
            "capability": self.capability,
            "payload": payload,
            "status": "completed",
        }
        self.status = "idle"
        return result


@dataclass
class AgentEntity:
    """Tier 4 — Lower-level autonomous AI.

    Agents are autonomous entities that can make decisions, maintain
    internal state, and coordinate with other agents. They report
    to AI complexes (Tier 3) and can invoke bots (Tier 5).
    """

    id: str = field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:8]}")
    name: str = "unnamed-agent"
    tier: Tier = Tier.AGENT
    capabilities: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    dna: list[float] | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "idle"
    subscriptions: list[SentinelChannel] = field(default_factory=list)

    def can_act_autonomously(self, confidence: float | None = None) -> bool:
        """Check if the agent can act autonomously based on confidence threshold."""
        threshold = confidence if confidence is not None else self.confidence
        return threshold >= 0.5

    def subscribe(self, channel: SentinelChannel) -> None:
        """Subscribe to a sentinel channel."""
        if channel not in self.subscriptions:
            self.subscriptions.append(channel)

    def unsubscribe(self, channel: SentinelChannel) -> None:
        """Unsubscribe from a sentinel channel."""
        if channel in self.subscriptions:
            self.subscriptions.remove(channel)


@dataclass
class AiComplex:
    """Tier 3 — The overarching ML/LLM Complex.

    An AI Complex is the primary intelligence unit. It manages
    multiple agents, coordinates their activities, and provides
    the high-level ML/LLM inference capabilities. AI Complexes
    are managed by Orchestrators (Tier 1).
    """

    id: str = field(default_factory=lambda: f"ai-{uuid.uuid4().hex[:8]}")
    name: str = "unnamed-ai-complex"
    tier: Tier = Tier.AI
    agents: dict[str, AgentEntity] = field(default_factory=dict)
    bots: dict[str, BotService] = field(default_factory=dict)
    models: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "active"

    def add_agent(self, agent_id: str, agent: AgentEntity | None = None) -> AgentEntity:
        """Add an agent to this AI complex. Returns the agent."""
        if agent is None:
            agent = AgentEntity(id=agent_id, name=agent_id)
        else:
            agent.id = agent_id
        self.agents[agent_id] = agent
        return agent

    def remove_agent(self, agent_id: str) -> AgentEntity | None:
        """Remove an agent from this AI complex."""
        return self.agents.pop(agent_id, None)

    def add_bot(self, bot_id: str, bot: BotService | None = None) -> BotService:
        """Add a bot to this AI complex. Returns the bot."""
        if bot is None:
            bot = BotService(id=bot_id, name=bot_id)
        else:
            bot.id = bot_id
        self.bots[bot_id] = bot
        return bot

    def remove_bot(self, bot_id: str) -> BotService | None:
        """Remove a bot from this AI complex."""
        return self.bots.pop(bot_id, None)

    def get_agent(self, agent_id: str) -> AgentEntity | None:
        """Get an agent by ID."""
        return self.agents.get(agent_id)

    def get_bot(self, bot_id: str) -> BotService | None:
        """Get a bot by ID."""
        return self.bots.get(bot_id)

    def list_agents(self) -> list[str]:
        """List all agent IDs."""
        return list(self.agents.keys())

    def list_bots(self) -> list[str]:
        """List all bot IDs."""
        return list(self.bots.keys())


# ── Tier Display ─────────────────────────────────────────────────────────────

TIER_NAMES: dict[Tier, str] = {
    Tier.HUMAN: "Human Oversight",
    Tier.ORCHESTRATOR: "Logical Orchestrator",
    Tier.PRIME: "Prime Coordinator",
    Tier.AI: "AI Complex (ML/LLM)",
    Tier.AGENT: "Autonomous Agent",
    Tier.BOT: "Stateless Bot Service",
}

TIER_DESCRIPTIONS: dict[Tier, str] = {
    Tier.HUMAN: "Human governance and oversight — the ultimate authority tier.",
    Tier.ORCHESTRATOR: "Logical orchestrator managing AI complexes and resource allocation.",
    Tier.PRIME: "Prime coordinator for cross-agent and cross-AI complex operations.",
    Tier.AI: "The overarching ML/LLM Complex — the primary intelligence unit that manages agents and bots.",
    Tier.AGENT: "Lower-level autonomous AI — capable of independent decision-making within delegated scope.",
    Tier.BOT: "Stateless service worker/function — single-purpose, no autonomy, invoked by agents or AI.",
}


def tier_hierarchy() -> str:
    """Return a formatted string of the tier hierarchy."""
    lines = ["═" * 60, "  TRANC3 INFINITY — TIER HIERARCHY", "═" * 60]
    for tier in Tier:
        lines.append(f"\n  Tier {tier.value}: {TIER_NAMES[tier]}")
        lines.append(f"    {TIER_DESCRIPTIONS[tier]}")
    lines.append("\n" + "═" * 60)
    lines.append("  KEY: AI = ML/LLM Complex (T3) | Agent = Autonomous AI (T4) | Bot = Worker (T5)")
    lines.append("═" * 60)
    return "\n".join(lines)


def sentinel_channels() -> str:
    """Return a formatted string of all sentinel channels."""
    lines = ["─" * 40, "  SENTINEL CHANNELS", "─" * 40]
    for ch in SentinelChannel:
        lines.append(f"  • {ch.name:<16} → {ch.value}")
    lines.append("─" * 40)
    return "\n".join(lines)
