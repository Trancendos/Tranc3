"""
Python-TypeScript Bridge — Tranc3 Ecosystem
=============================================

Provides seamless communication between the Python and TypeScript
codebases using JSON-RPC 2.0 over HTTP or stdio.

Architecture:
  Python ←→ JSON-RPC ←→ HTTP/stdio ←→ TypeScript

The bridge uses a shared message format so that both sides can
understand each other without translation layers.
"""

from .ecosystem_bridge import (
    BridgeConfig,
    BridgeEndpoint,
    BridgeTransport,
    JsonRpcRequest,
    JsonRpcResponse,
    EcosystemBridge,
    EcosystemRegistry,
    EcosystemEntity,
)

from .energy_constants import (
    BridgeType,
    EnergyClass,
    cost_for,
    priority_for,
    BRIDGE_DEFAULT_ENERGY,
    DIALITHIUM_PRIORITY,
    CRYSTAL_BASE_COST,
    LIGHTNING_BURST_LIMIT_MS,
    LIGHT_AMBIENT_TICK_HZ,
    TRILITHIUM_STABILITY_FACTOR,
)

__all__ = [
    "BridgeConfig",
    "BridgeEndpoint",
    "BridgeTransport",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "EcosystemBridge",
    "EcosystemRegistry",
    "EcosystemEntity",
    # Energy constants
    "BridgeType",
    "EnergyClass",
    "cost_for",
    "priority_for",
    "BRIDGE_DEFAULT_ENERGY",
    "DIALITHIUM_PRIORITY",
    "CRYSTAL_BASE_COST",
    "LIGHTNING_BURST_LIMIT_MS",
    "LIGHT_AMBIENT_TICK_HZ",
    "TRILITHIUM_STABILITY_FACTOR",
]
