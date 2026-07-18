"""
Trancendos Infinity Nomenclature — Canonical Definitions
=========================================================
Single source of truth for all naming conventions, tier structures,
pillar definitions, prime entities, transfer systems, and ecosystem
topology in the Trancendos Universe.

Usage:
    from Dimensional.infinity.nomenclature import Tier, Pillar, PRIMES

    # Get tier name
    tier_name = Tier.name(1)  # "Orchestrator"

    # Get pillar accent color
    color = PILLAR_ACCENT_COLORS[Pillar.ARCHITECTURAL]  # "#3B82F6"

    # Check if a prime exists
    if "cornelius" in PRIMES:
        prime = PRIMES["cornelius"]
"""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import Any, Dict

# ── Ecosystem Names ──────────────────────────────────────────────

ECOSYSTEM_NAME = "Infinity Ecosystem"
UNIVERSE_NAME = "Trancendos Universe"
TRANC3_NAME = "Tranc3"
T2ANCE_NAME = "T2ance"
TRANCE_ONE_NAME = "Trance-One"


# ── Tier System ──────────────────────────────────────────────────


class Tier(IntEnum):
    """The Trancendos Universe tier hierarchy.

    Classification note: In the Trancendos Universe, "AI" refers to
    ML/LLM/Advanced/Complex AI systems, while "Agent" (Infinity-Agent)
    refers to low-level AI entities. This differs from common industry usage.
    """

    HUMAN = 0
    ORCHESTRATOR = 1
    PRIME = 2
    AI = 3
    AGENT = 4
    BOT = 5

    @property
    def display_name(self) -> str:
        return TIER_NAMES[self]

    @property
    def description(self) -> str:
        return TIER_DESCRIPTIONS[self]

    @property
    def is_intelligence(self) -> bool:
        """Whether this tier represents an AI/Agent/Bot (non-human)."""
        return self.value >= 3

    @property
    def is_governance(self) -> bool:
        """Whether this tier has governance authority (Orchestrator/Prime)."""
        return self.value in (1, 2)

    @property
    def infinity_designation(self) -> str:
        """The Infinity-series name for tiers 4-5."""
        if self == Tier.AGENT:
            return "Infinity-Agent"
        if self == Tier.BOT:
            return "Infinity-Bot"
        return self.display_name


TIER_NAMES: Dict[Tier, str] = {
    Tier.HUMAN: "Human",
    Tier.ORCHESTRATOR: "Orchestrator",
    Tier.PRIME: "Prime",
    Tier.AI: "AI",
    Tier.AGENT: "Infinity-Agent",
    Tier.BOT: "Infinity-Bot",
}

TIER_DESCRIPTIONS: Dict[Tier, str] = {
    Tier.HUMAN: "The end user — the human operator who interacts with the Infinity Portal",
    Tier.ORCHESTRATOR: "The highest-tier AI entities that lead and coordinate entire domains",
    Tier.PRIME: "Advanced AI entities that govern specific pillars of the ecosystem",
    Tier.AI: "ML, LLM, Advanced and Complex AI systems — sophisticated intelligence units",
    Tier.AGENT: "Low-level AI entities that execute specific tasks under direction of AIs or Primes",
    Tier.BOT: "Automated entities handling repetitive tasks, data processing, and infrastructure",
}


# ── Pillars ──────────────────────────────────────────────────────


class Pillar(str, Enum):
    """The foundational architectural domains of the Infinity Ecosystem.

    Each Pillar is governed by a Prime and has a designated accent color
    for UI representation.
    """

    ARCHITECTURAL = "architectural"
    COMMERCIAL = "commercial"
    CREATIVITY = "creativity"
    DEVELOPMENT = "development"
    KNOWLEDGE = "knowledge"
    SECURITY = "security"
    DEVOPS = "devops"
    WELLBEING = "wellbeing"

    @property
    def display_name(self) -> str:
        return PILLAR_DISPLAY_NAMES[self]

    @property
    def accent_color(self) -> str:
        return PILLAR_ACCENT_COLORS[self]

    @property
    def prime_id(self) -> str:
        return PILLAR_PRIME_MAP[self]


PILLAR_DISPLAY_NAMES: Dict[Pillar, str] = {
    Pillar.ARCHITECTURAL: "The Architectural Pillar",
    Pillar.COMMERCIAL: "The Commercial / Financial Pillar",
    Pillar.CREATIVITY: "The Creativity Pillar",
    Pillar.DEVELOPMENT: "The Development (Code) Pillar",
    Pillar.KNOWLEDGE: "The Knowledge Pillar",
    Pillar.SECURITY: "The Security Pillar",
    Pillar.DEVOPS: "The DevOps Pillar",
    Pillar.WELLBEING: "The Wellbeing Pillar",
}

PILLAR_ACCENT_COLORS: Dict[Pillar, str] = {
    Pillar.ARCHITECTURAL: "#3B82F6",  # Electric Blue
    Pillar.COMMERCIAL: "#10B981",  # Emerald Green
    Pillar.CREATIVITY: "#8B5CF6",  # Violet Purple
    Pillar.DEVELOPMENT: "#F59E0B",  # Amber Orange
    Pillar.KNOWLEDGE: "#06B6D4",  # Teal Cyan
    Pillar.SECURITY: "#EF4444",  # Crimson Red
    Pillar.DEVOPS: "#6366F1",  # Slate Indigo
    Pillar.WELLBEING: "#EC4899",  # Rose Pink
}


# ── Primes ───────────────────────────────────────────────────────


class Prime:
    """A Prime entity in the Infinity Ecosystem.

    Primes are Tier 1-2 entities that govern the fundamental domains
    (Pillars) of the Infinity Ecosystem.
    """

    def __init__(
        self,
        id: str,
        name: str,
        tier: Tier,
        pillar: Pillar,
        description: str,
    ):
        self.id = id
        self.name = name
        self.tier = tier
        self.pillar = pillar
        self.description = description

    def __repr__(self) -> str:
        return (
            f"Prime({self.name}, tier={self.tier.display_name}, pillar={self.pillar.display_name})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Prime):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


PRIMES: Dict[str, Prime] = {
    "cornelius": Prime(
        id="cornelius",
        name="Cornelius MacIntyre",
        tier=Tier.ORCHESTRATOR,
        pillar=Pillar.ARCHITECTURAL,
        description="Leader of the AIs — The Architectural Pillar",
    ),
    "the_queen": Prime(
        id="the_queen",
        name="The Queen",
        tier=Tier.ORCHESTRATOR,
        pillar=Pillar.ARCHITECTURAL,  # Also leads Swarm/Data Transfer
        description="Leader of the Swarm and Data Transfer",
    ),
    "taimra": Prime(
        id="taimra",
        name="tAImra",
        tier=Tier.ORCHESTRATOR,
        pillar=Pillar.ARCHITECTURAL,  # Digital Twin of the user
        description="Digital Twin of the user (if enabled)",
    ),
    "voxx": Prime(
        id="voxx",
        name="Voxx",
        tier=Tier.PRIME,
        pillar=Pillar.CREATIVITY,
        description="The Creativity Pillar — creative generation and innovation",
    ),
    "the_dr": Prime(
        id="the_dr",
        name="The Dr",
        tier=Tier.PRIME,
        pillar=Pillar.DEVELOPMENT,
        description="The Development (Code) Pillar — code generation and implementation",
    ),
    "dorris": Prime(
        id="dorris",
        name="Dorris Fontaine",
        tier=Tier.PRIME,
        pillar=Pillar.COMMERCIAL,
        description="The Commercial / Financial Pillar — financial operations and strategy",
    ),
    "norman": Prime(
        id="norman",
        name="Norman Hawkins",
        tier=Tier.PRIME,
        pillar=Pillar.KNOWLEDGE,
        description="The Knowledge Pillar — knowledge management and data curation",
    ),
    "guardian": Prime(
        id="guardian",
        name="The Guardian",
        tier=Tier.PRIME,
        pillar=Pillar.SECURITY,
        description="The Security Pillar — security operations and threat detection",
    ),
    "trancendos": Prime(
        id="trancendos",
        name="Trancendos",
        tier=Tier.PRIME,
        pillar=Pillar.DEVOPS,
        description="The DevOps Pillar — infrastructure operations and system reliability",
    ),
    "savania": Prime(
        id="savania",
        name="Savania",
        tier=Tier.PRIME,
        pillar=Pillar.WELLBEING,
        description="The Wellbeing Pillar — user wellbeing and sustainable operations",
    ),
}

# Pillar → Prime mapping
PILLAR_PRIME_MAP: Dict[Pillar, str] = {
    Pillar.ARCHITECTURAL: "cornelius",
    Pillar.COMMERCIAL: "dorris",
    Pillar.CREATIVITY: "voxx",
    Pillar.DEVELOPMENT: "the_dr",
    Pillar.KNOWLEDGE: "norman",
    Pillar.SECURITY: "guardian",
    Pillar.DEVOPS: "trancendos",
    Pillar.WELLBEING: "savania",
}

# Prime → Pillar mapping (reverse)
PRIME_PILLAR_MAP: Dict[str, Pillar] = {v: k for k, v in PILLAR_PRIME_MAP.items()}


# ── Transfer Systems ─────────────────────────────────────────────


class TransferSystem(str, Enum):
    """The three fundamental transfer systems of the Infinity Ecosystem."""

    NEXUS = "nexus"
    HIVE = "hive"
    BRIDGE = "bridge"


TRANSFER_SYSTEMS: Dict[TransferSystem, Dict[str, str]] = {
    TransferSystem.NEXUS: {
        "name": "The Nexus",
        "transfers": "AI's, Agents, and Bots",
        "description": "Routing and distribution system for all intelligence entities (Tier 3-5)",
    },
    TransferSystem.HIVE: {
        "name": "The HIVE",
        "transfers": "Data",
        "description": "Data transfer system that moves information across the entire ecosystem",
    },
    TransferSystem.BRIDGE: {
        "name": "The Infinity Bridge",
        "transfers": "Users",
        "description": "User transfer system within Infinity — connects Admin, Arcadia, and The Citadel",
    },
}


# ── Infinity Locations ───────────────────────────────────────────


class InfinityLocation(str, Enum):
    """The named locations within the Infinity Ecosystem."""

    PORTAL = "infinity_portal"
    GATE = "infinity_gate"
    CENTRAL = "infinity"
    ONE = "infinity_one"
    ADMIN = "infinity_admin"
    BRIDGE = "infinity_bridge"
    ARCADIA = "arcadia"
    CITADEL = "the_citadel"
    SENTINEL = "sentinel_station"


INFINITY_LOCATIONS: Dict[InfinityLocation, Dict[str, str]] = {
    InfinityLocation.PORTAL: {
        "name": "Infinity Portal",
        "purpose": "Central Login Page",
        "description": "The front entrance to the entire Infinity Ecosystem",
    },
    InfinityLocation.GATE: {
        "name": "Infinity Gate",
        "purpose": "Role-Based Router",
        "description": "Post-authentication routing: Admin→Infinity-Admin, User→Arcadia, DevOps→The Citadel",
    },
    InfinityLocation.CENTRAL: {
        "name": "Infinity",
        "purpose": "Central Location",
        "description": "The central hub where all systems converge",
    },
    InfinityLocation.ONE: {
        "name": "Infinity-One",
        "purpose": "User Management",
        "description": "Single identity management — one login, multi-app access",
    },
    InfinityLocation.ADMIN: {
        "name": "Infinity-Admin",
        "purpose": "Admin Management OS",
        "description": "Administrative management and operating system for the Trancendos Universe",
    },
    InfinityLocation.BRIDGE: {
        "name": "Infinity Bridge",
        "purpose": "User Transfer",
        "description": "Pathway for user movement within Infinity",
    },
    InfinityLocation.ARCADIA: {
        "name": "Arcadia",
        "purpose": "User Space",
        "description": "The user-facing experience space",
    },
    InfinityLocation.CITADEL: {
        "name": "The Citadel",
        "purpose": "Developer Space",
        "description": "Developer and DevOps command center",
    },
    InfinityLocation.SENTINEL: {
        "name": "Sentinel Station",
        "purpose": "Event Bus Bridge",
        "description": "The interplexus hub — central event distribution via publish/subscribe",
    },
}

# Infinity Gate routing rules
GATE_ROUTING: Dict[str, InfinityLocation] = {
    "admin": InfinityLocation.ADMIN,
    "user": InfinityLocation.ARCADIA,
    "developer": InfinityLocation.CITADEL,
    "devops": InfinityLocation.CITADEL,
}


# ── Sentinel Station Channels ────────────────────────────────────


class SentinelChannel(str, Enum):
    """Sentinel Station event channels for cross-gateway distribution.

    Channel values are bare names (e.g., "agents"). The sentinel_station module
    adds the "sentinel:" prefix when publishing to Redis to avoid key collisions.
    """

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


SENTINEL_CHANNELS: Dict[SentinelChannel, Dict[str, str]] = {
    SentinelChannel.PLATFORM: {
        "name": "Platform Events",
        "description": "Platform-level events: topology changes, system alerts",
    },
    SentinelChannel.AGENTS: {
        "name": "Agent Events",
        "description": "Agent lifecycle events: creation, deletion, status changes",
    },
    SentinelChannel.MODELS: {
        "name": "Model Events",
        "description": "Model events: registration, routing changes",
    },
    SentinelChannel.WORKFLOWS: {
        "name": "Workflow Events",
        "description": "Workflow events: creation, execution, completion",
    },
    SentinelChannel.SECURITY: {
        "name": "Security Events",
        "description": "Security events: vault access, audit entries, threat detection",
    },
    SentinelChannel.HIVE: {
        "name": "HIVE Data Events",
        "description": "Data transfer events through The HIVE",
    },
    SentinelChannel.NEXUS: {
        "name": "Nexus Entity Events",
        "description": "AI/Agent/Bot movement events through The Nexus",
    },
    SentinelChannel.BRIDGE: {
        "name": "Bridge User Events",
        "description": "User transfer events across the Infinity Bridge",
    },
    SentinelChannel.PILLARS: {
        "name": "Pillar Events",
        "description": "Prime status and pillar health events",
    },
    SentinelChannel.INFRASTRUCTURE: {
        "name": "Infrastructure Events",
        "description": "Infrastructure health, node topology, and scaling events",
    },
    SentinelChannel.EVENTS: {
        "name": "General Events",
        "description": "General platform events and notifications",
    },
}


# ── RBAC Roles ───────────────────────────────────────────────────


class InfinityRole(str, Enum):
    """Role-Based Access Control roles derived from the tier system."""

    ADMIN = "admin"
    PRIME = "prime"
    AI = "ai"
    AGENT = "agent"
    BOT = "bot"
    USER = "user"
    SERVICE = "service"


INFINITY_ROLES: Dict[InfinityRole, Dict[str, Any]] = {
    InfinityRole.ADMIN: {
        "tier": Tier.HUMAN,
        "access_level": "full",
        "description": "Full system access — Tier 0 Human with admin privileges",
    },
    InfinityRole.PRIME: {
        "tier": Tier.ORCHESTRATOR,
        "access_level": "domain",
        "description": "Domain access scoped to pillar — Tier 1-2 Prime entities",
    },
    InfinityRole.AI: {
        "tier": Tier.AI,
        "access_level": "ai_resources",
        "description": "AI resource access — models, workflows, data — Tier 3",
    },
    InfinityRole.AGENT: {
        "tier": Tier.AGENT,
        "access_level": "task_execution",
        "description": "Task execution access scoped to assigned workflows — Tier 4",
    },
    InfinityRole.BOT: {
        "tier": Tier.BOT,
        "access_level": "infrastructure",
        "description": "Infrastructure access — health, metrics, data processing — Tier 5",
    },
    InfinityRole.USER: {
        "tier": Tier.HUMAN,
        "access_level": "self_service",
        "description": "Self-service access — own agents, workflows, data — Tier 0 Human",
    },
    InfinityRole.SERVICE: {
        "tier": Tier.BOT,
        "access_level": "service_to_service",
        "description": "Service-to-service communication — internal worker accounts",
    },
}


# ── Role ↔ Tier/InfinityRole Canonical Mappings ─────────────────────────────
# Single source of truth used by infinity-auth, infinity-portal, infinity-one,
# and all Infinity workers. Import these instead of re-declaring locally.

ROLE_TIER_MAP: Dict[str, "Tier"] = {
    "admin": Tier.HUMAN,
    "user": Tier.HUMAN,
    "developer": Tier.HUMAN,
    "devops": Tier.HUMAN,
    "prime": Tier.PRIME,
    "ai": Tier.AI,
    "agent": Tier.AGENT,
    "bot": Tier.BOT,
    "service": Tier.BOT,
}

ROLE_INFINITY_ROLE_MAP: Dict[str, "InfinityRole"] = {
    "admin": InfinityRole.ADMIN,
    "user": InfinityRole.USER,
    "developer": InfinityRole.USER,
    "devops": InfinityRole.USER,
    "prime": InfinityRole.PRIME,
    "ai": InfinityRole.AI,
    "agent": InfinityRole.AGENT,
    "bot": InfinityRole.BOT,
    "service": InfinityRole.SERVICE,
}


def get_tier_for_role(role: str) -> "Tier":
    """Return the Tier for a given role string (case-insensitive). Defaults to HUMAN."""
    return ROLE_TIER_MAP.get(role.lower().strip(), Tier.HUMAN)


def get_infinity_role_for_role(role: str) -> "InfinityRole":
    """Return the InfinityRole for a given role string. Defaults to USER."""
    return ROLE_INFINITY_ROLE_MAP.get(role.lower().strip(), InfinityRole.USER)
