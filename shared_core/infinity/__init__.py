"""
Trancendos Infinity Package — Ecosystem Architecture Definitions
================================================================
Programmatic definitions for the Infinity Ecosystem: tiers, pillars,
primes, dimensional services, transfer systems, and location topology.

This module is the single source of truth for all naming conventions
and structural definitions used across the Trancendos Universe.
"""

from shared_core.infinity.nomenclature import (
    # Ecosystem names
    ECOSYSTEM_NAME,
    GATE_ROUTING,
    INFINITY_LOCATIONS,
    INFINITY_ROLES,
    PILLAR_ACCENT_COLORS,
    PILLAR_PRIME_MAP,
    PRIME_PILLAR_MAP,
    PRIMES,
    SENTINEL_CHANNELS,
    T2ANCE_NAME,
    TIER_DESCRIPTIONS,
    TIER_NAMES,
    TRANC3_NAME,
    TRANCE_ONE_NAME,
    TRANSFER_SYSTEMS,
    UNIVERSE_NAME,
    # Infinity locations
    InfinityLocation,
    # RBAC roles
    InfinityRole,
    Pillar,
    # Primes and Pillars
    Prime,
    # Sentinel Station channels
    SentinelChannel,
    # Tier system
    Tier,
    # Transfer systems
    TransferSystem,
)

__all__ = [
    # Tier system
    "Tier",
    "TIER_NAMES",
    "TIER_DESCRIPTIONS",
    # Primes and Pillars
    "Prime",
    "Pillar",
    "PRIMES",
    "PILLAR_ACCENT_COLORS",
    "PILLAR_PRIME_MAP",
    "PRIME_PILLAR_MAP",
    # Transfer systems
    "TransferSystem",
    "TRANSFER_SYSTEMS",
    # Infinity locations
    "InfinityLocation",
    "INFINITY_LOCATIONS",
    "GATE_ROUTING",
    # Ecosystem names
    "ECOSYSTEM_NAME",
    "UNIVERSE_NAME",
    "TRANC3_NAME",
    "T2ANCE_NAME",
    "TRANCE_ONE_NAME",
    # Sentinel Station channels
    "SentinelChannel",
    "SENTINEL_CHANNELS",
    # RBAC roles
    "InfinityRole",
    "INFINITY_ROLES",
]
