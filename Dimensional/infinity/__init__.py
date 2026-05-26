"""
Trancendos Infinity Package — Ecosystem Architecture Definitions
================================================================
Programmatic definitions for the Infinity Ecosystem: tiers, pillars,
primes, dimensional services, transfer systems, location topology,
and the HIL-A chain protocol.

This module is the single source of truth for all naming conventions
and structural definitions used across the Trancendos Universe.
"""

from Dimensional.infinity.hil_a import (
    BypassReason,
    # HIL-A Chain Protocol
    ChainProtocol,
    EnhancementRequest,
    EnhancementStatus,
    EnhancementType,
    SelfGoverningVotingSystem,
    UrgencyLevel,
    Vote,
    create_default_chain,
    get_default_chain,
)
from Dimensional.infinity.nomenclature import (
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
from Dimensional.infinity.worker_bridges import (
    AdminConfigTunerBridge,
    BridgeStatus,
    DefenseSentinelBridge,
    ForesightPortalBridge,
    NexusSentinelBridge,
    RegistryDiscoveryBridge,
    # Phase 23.5 Worker Integration Bridges
    WorkerBridge,
    create_all_bridges,
    start_all_bridges,
    stop_all_bridges,
)
from Dimensional.infinity.zkp import (
    TierMembershipProof,
    ZKPChallenge,
    # ZKP Authentication
    ZKPKeyPair,
    ZKPProof,
    ZKPProver,
    ZKPRegistry,
    ZKPResponse,
    ZKPVerificationResult,
    ZKPVerifier,
    create_zkp_session,
    verify_zkp_auth,
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
    # HIL-A Chain Protocol
    "ChainProtocol",
    "EnhancementRequest",
    "EnhancementStatus",
    "EnhancementType",
    "UrgencyLevel",
    "Vote",
    "BypassReason",
    "SelfGoverningVotingSystem",
    "create_default_chain",
    "get_default_chain",
    # ZKP Authentication
    "ZKPKeyPair",
    "ZKPChallenge",
    "ZKPResponse",
    "ZKPProof",
    "ZKPVerificationResult",
    "TierMembershipProof",
    "ZKPRegistry",
    "ZKPProver",
    "ZKPVerifier",
    "create_zkp_session",
    "verify_zkp_auth",
    # Phase 23.5 Worker Integration Bridges
    "WorkerBridge",
    "BridgeStatus",
    "NexusSentinelBridge",
    "ForesightPortalBridge",
    "AdminConfigTunerBridge",
    "DefenseSentinelBridge",
    "RegistryDiscoveryBridge",
    "create_all_bridges",
    "start_all_bridges",
    "stop_all_bridges",
]
