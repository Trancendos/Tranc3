"""
Trancendos Dimensional Nexus — The Central Nervous System
==========================================================
The Nexus module provides the unified coordination layer for the entire
Dimensional infrastructure. It bridges health monitoring, service orchestration,
tier-aware access control, and cross-dimensional event routing into a single
coherent API surface.

Architecture:
    Nexus → Health Aggregator → Dimensional Service Bus → Underverse
         → Tier Access Bridge (RBAC ↔ ABAC unification)
         → Sentinel Event Router → Cross-platform event distribution
         → Causal Ordering Engine → Timeline consistency for all events
         → Sentinel Bridge → Bidirectional Nexus ↔ Sentinel Station flow

Components:
    DimensionalNexus: Central coordinator and API surface
    TierAccessBridge: Unified RBAC+ABAC access control with tier hierarchy
    HealthAggregator: Real-time health across all dimensional services
    EventRouter: Cross-dimensional sentinel event distribution
    CausalOrderingEngine: Vector-clock based event timeline consistency
    NexusSentinelBridge: Bidirectional event bridge to Sentinel Station

Port: 8050
Zero-cost: FastAPI + SQLite + in-process bus. No external dependencies.
"""

from .nexus_core import (
    CausalOrderingEngine,
    DimensionalNexus,
    EventRouter,
    HealthAggregator,
    NexusWSManager,
    TierAccessBridge,
    get_nexus,
)
from .sentinel_bridge import NexusSentinelBridge, get_bridge

__all__ = [
    "CausalOrderingEngine",
    "DimensionalNexus",
    "EventRouter",
    "HealthAggregator",
    "NexusWSManager",
    "NexusSentinelBridge",
    "TierAccessBridge",
    "get_bridge",
    "get_nexus",
]
