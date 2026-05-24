"""
The Nexus — AI, Agent, and Bot Traffic Coordination
=====================================================
The Nexus is ONE of the three bridges that route traffic through
Sentinel Station:

    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus      : AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE       : Data movement and swarm system coordination

The Nexus module provides dedicated coordination for AI (Tier 3),
Agent (Tier 4), and Bot (Tier 5) traffic with tier-aware access control,
causal event ordering, real-time health aggregation, and cross-Nexus
event routing.

Architecture:
    Nexus → Health Aggregator → AI/Agent/Bot Service Health
         → Tier Access Bridge (RBAC ↔ ABAC unification)
         → Sentinel Event Router → Cross-platform event distribution
         → Causal Ordering Engine → Timeline consistency for all events
         → Sentinel Bridge → Bidirectional Nexus ↔ Sentinel Station flow

Components:
    Nexus: AI/Agent/Bot traffic coordinator (the primary class)
    TierAccessBridge: Unified RBAC+ABAC access control with tier hierarchy
    HealthAggregator: Real-time health across AI/Agent/Bot services
    EventRouter: Cross-Nexus sentinel event distribution
    CausalOrderingEngine: Vector-clock based event timeline consistency
    NexusSentinelBridge: Bidirectional event bridge to Sentinel Station

IMPORTANT: Nexus ≠ Dimensional. Nexus is AI/Agent/Bot traffic.
Dimensional is core/shared services. They are separate concepts.
"DimensionalNexus" is a backward-compatible alias, only valid when
referring to both systems in conjunction.

Port: 8050
Zero-cost: FastAPI + SQLite + in-process bus. No external dependencies.
"""

from .nexus_core import (
    CausalOrderingEngine,
    DimensionalNexus,
    EventRouter,
    HealthAggregator,
    Nexus,
    NexusWSManager,
    TierAccessBridge,
    get_nexus,
)
from .sentinel_bridge import NexusSentinelBridge, get_bridge

__all__ = [
    # Primary class
    "Nexus",
    # Backward-compatible alias (only for Dimensional+Nexus conjunction)
    "DimensionalNexus",
    # Subsystems
    "CausalOrderingEngine",
    "EventRouter",
    "HealthAggregator",
    "NexusWSManager",
    "TierAccessBridge",
    "NexusSentinelBridge",
    # Singletons
    "get_bridge",
    "get_nexus",
]
