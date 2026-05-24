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

Components:
    DimensionalNexus: Central coordinator and API surface
    TierAccessBridge: Unified RBAC+ABAC access control with tier hierarchy
    HealthAggregator: Real-time health across all dimensional services
    EventRouter: Cross-dimensional sentinel event distribution
    CausalOrderingEngine: Vector-clock based event timeline consistency

Port: 8050
Zero-cost: FastAPI + SQLite + in-process bus. No external dependencies.
"""

from .nexus_core import (
    CausalOrderingEngine,
    DimensionalNexus,
    EventRouter,
    HealthAggregator,
    TierAccessBridge,
    get_nexus,
)

__all__ = [
    "CausalOrderingEngine",
    "DimensionalNexus",
    "EventRouter",
    "HealthAggregator",
    "TierAccessBridge",
    "get_nexus",
]
