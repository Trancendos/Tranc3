"""
Energy and crystal constants for the Three-Bridge Architecture.

Dialithium  — highest-priority crystal; Crystal Bridge power source.
Trilithium  — stabiliser crystal; quorum and consistency operations.
Crystal     — base energy carrier; standard routing token.
Lightning   — impulse energy; Transwarp Bridge burst transfers.
Light       — ambient energy; Cell Bridge cellular automata ticks.
Transwarp   — warp-drive class topology; high-throughput async corridors.
Cell        — cellular-automata unit; micro-state propagation.
"""

from __future__ import annotations  # noqa: I001

from enum import Enum

# ---------------------------------------------------------------------------
# Crystal / energy classification
# ---------------------------------------------------------------------------


class EnergyClass(str, Enum):
    DIALITHIUM = "dialithium"
    TRILITHIUM = "trilithium"
    CRYSTAL = "crystal"
    LIGHTNING = "lightning"
    LIGHT = "light"
    TRANSWARP = "transwarp"
    CELL = "cell"


class BridgeType(str, Enum):
    CRYSTAL = "crystal_bridge"
    TRANSWARP = "transwarp_bridge"
    CELL = "cell_bridge"


# ---------------------------------------------------------------------------
# Priority weights (lower = higher priority in scheduling queues)
# ---------------------------------------------------------------------------

DIALITHIUM_PRIORITY: int = 1
TRILITHIUM_PRIORITY: int = 2
CRYSTAL_PRIORITY: int = 3
LIGHTNING_PRIORITY: int = 4
LIGHT_PRIORITY: int = 5

ENERGY_PRIORITY: dict[EnergyClass, int] = {
    EnergyClass.DIALITHIUM: DIALITHIUM_PRIORITY,
    EnergyClass.TRILITHIUM: TRILITHIUM_PRIORITY,
    EnergyClass.CRYSTAL: CRYSTAL_PRIORITY,
    EnergyClass.LIGHTNING: LIGHTNING_PRIORITY,
    EnergyClass.LIGHT: LIGHT_PRIORITY,
    EnergyClass.TRANSWARP: LIGHTNING_PRIORITY,
    EnergyClass.CELL: LIGHT_PRIORITY,
}

# ---------------------------------------------------------------------------
# Routing cost multipliers (applied to base token cost)
# ---------------------------------------------------------------------------

DIALITHIUM_COST_FACTOR: float = 1.0
TRILITHIUM_COST_FACTOR: float = 0.8
CRYSTAL_BASE_COST: float = 0.6
LIGHTNING_COST_FACTOR: float = 0.3
LIGHT_COST_FACTOR: float = 0.1

ENERGY_COST_FACTOR: dict[EnergyClass, float] = {
    EnergyClass.DIALITHIUM: DIALITHIUM_COST_FACTOR,
    EnergyClass.TRILITHIUM: TRILITHIUM_COST_FACTOR,
    EnergyClass.CRYSTAL: CRYSTAL_BASE_COST,
    EnergyClass.LIGHTNING: LIGHTNING_COST_FACTOR,
    EnergyClass.LIGHT: LIGHT_COST_FACTOR,
    EnergyClass.TRANSWARP: LIGHTNING_COST_FACTOR,
    EnergyClass.CELL: LIGHT_COST_FACTOR,
}

# ---------------------------------------------------------------------------
# Bridge affinity — default energy class per bridge
# ---------------------------------------------------------------------------

BRIDGE_DEFAULT_ENERGY: dict[BridgeType, EnergyClass] = {
    BridgeType.CRYSTAL: EnergyClass.DIALITHIUM,
    BridgeType.TRANSWARP: EnergyClass.LIGHTNING,
    BridgeType.CELL: EnergyClass.LIGHT,
}

BRIDGE_SECONDARY_ENERGY: dict[BridgeType, EnergyClass] = {
    BridgeType.CRYSTAL: EnergyClass.TRILITHIUM,
    BridgeType.TRANSWARP: EnergyClass.TRANSWARP,
    BridgeType.CELL: EnergyClass.CELL,
}

# ---------------------------------------------------------------------------
# Performance limits
# ---------------------------------------------------------------------------

LIGHTNING_BURST_LIMIT_MS: float = 50.0
LIGHT_AMBIENT_TICK_HZ: float = 10.0
DIALITHIUM_STABILITY_FACTOR: float = 0.95
TRILITHIUM_STABILITY_FACTOR: float = 0.99

# Transwarp corridor throughput cap (requests/sec per corridor)
TRANSWARP_MAX_RPS: float = 10_000.0

# Cell bridge automata grid default tick interval (seconds)
CELL_TICK_INTERVAL_S: float = 1.0 / LIGHT_AMBIENT_TICK_HZ


def cost_for(energy: EnergyClass, base: float = 1.0) -> float:
    """Return routed cost for a given energy class."""
    return base * ENERGY_COST_FACTOR.get(energy, CRYSTAL_BASE_COST)


def priority_for(energy: EnergyClass) -> int:
    """Return scheduling priority (1=highest) for a given energy class."""
    return ENERGY_PRIORITY.get(energy, CRYSTAL_PRIORITY)
