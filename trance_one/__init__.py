"""
Trance-One — Tier 1: Sovereign Orchestrator
=============================================
The apex of the Trancendos 5-tier AI hierarchy.

Hierarchy:
  Tier 1  →  Trance-One        (Sovereign Orchestrator — this package)
  Tier 2  →  T2ance            (Prime Level — executive AI authorities)
  Tier 3  →  Tranc3            (High-Spec Complex ML/LLM AI Base)
  Tier 4  →  Infinity-Agent    (Low-Level AI Agent — Alpha + Beta per entity)
  Tier 5  →  Infinity-Worker   (Bots, Workers, Scrapers)

Trance-One responsibilities:
  - Sovereign-level platform control and policy enforcement
  - Cross-tier orchestration and lifecycle management
  - Top-level failover authority (overrides all lower tiers)
  - Platform-wide zero-cost compliance enforcement
  - Entity activation / deactivation across all 43 locations
  - Tier bridge to T2ance prime councils
"""

from trance_one.platform_manifest import PlatformManifest, get_manifest
from trance_one.sovereign_controller import SovereignController, get_sovereign
from trance_one.tier_bridge import TierBridge, TierCommand, TierCommandType

__all__ = [
    "SovereignController",
    "get_sovereign",
    "TierBridge",
    "TierCommand",
    "TierCommandType",
    "PlatformManifest",
    "get_manifest",
]
