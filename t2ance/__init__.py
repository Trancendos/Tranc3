"""
T2ance — Tier 2: Prime Level
==============================
Executive AI authorities within the Trancendos 5-tier hierarchy.

The Primes are domain-specialist executive AIs that govern clusters of
Tier 3 Lead AI agents across the 43 platform entities. Each Prime holds
authority over one or more Pillars and arbitrates escalations from Tier 3.

Hierarchy position:
  Tier 1  →  Trance-One     (Sovereign Orchestrator)
  Tier 2  →  T2ance         (Prime Level — this package)
  Tier 3  →  Tranc3         (High-Spec ML/LLM AI Base Level)
  Tier 4  →  Infinity-Agent (Low-Level AI Agents — Alpha + Beta)
  Tier 5  →  Infinity-Worker (Bots, Workers, Scrapers)

T2ance Primes (one per domain cluster):
  - ArchPrime   → Architectural pillar (The Spark, The Hive, Infinity, etc.)
  - CommPrime   → Commercial & Financial (Royal Bank, Arcadian Exchange, etc.)
  - CreatePrime → Creativity pillar (Studio, TranceFlow, TateKing, etc.)
  - DevPrime    → Development & Code (The Workshop, The Lab, API Marketplace)
  - KnowPrime   → Knowledge pillar (The Library, The Academy, DocUtari)
  - SecPrime    → Security pillar (Cryptex, The Void, The Warp Tunnel)
  - WellPrime   → Wellbeing pillar (Tranquility, I-Mind, Resonate, tAimra)
  - GovPrime    → Governance pillar (The Town Hall, Arcadia)
  - OpsPrime    → DevOps (The Citadel, The Observatory)
"""

from t2ance.domain_authority import DomainPrime, PrimeDomain
from t2ance.prime_registry import PrimeRegistry, get_prime_registry
from t2ance.tier_relay import TierRelay, get_relay

__all__ = [
    "PrimeRegistry",
    "get_prime_registry",
    "DomainPrime",
    "PrimeDomain",
    "TierRelay",
    "get_relay",
]
